"""Tests de la persistance de la déduplication (colonne canonical_id, collapse,
dédup cross-batch, migration, backfill)."""

import sqlite3
from datetime import UTC, date, datetime

from db.migrations import init_schema
from db.store import EventStore
from models.event import Event
from models.identity import make_event_id

# Dates loin dans le futur : robustes au filtre `upcoming` (basé sur l'horloge réelle).
_FUT = date(2099, 7, 25)


def mk(source="tc", **over) -> Event:
    url = over.pop("url", f"https://{source}.example/{over.get('title', 'x')}")
    title = over.pop("title", "Event")
    base = dict(
        id=over.pop("id", None) or make_event_id([url, title, source]),
        source=source,
        title=title,
        url=url,
        start_date=_FUT,
        end_date=None,
        times=None,
        venue=None,
        latitude=None,
        longitude=None,
        price=None,
        attributes=over.pop("attributes", {}),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(over)
    return Event(**base)


def _fireworks_pair():
    a = mk(
        "hanabi",
        title="Sumida River Fireworks",
        latitude=35.7110,
        longitude=139.8010,
        venue="Sumida",
    )
    b = mk(
        "tc",
        title="Sumida River Fireworks",
        latitude=35.7120,
        longitude=139.8012,
        attributes={"location_name": "Sumida"},
    )
    return a, b


# --- Colonne canonical_id : round-trip ---


def test_canonical_id_column_roundtrips(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        e = mk("tc", title="Solo", latitude=35.6, longitude=139.7)
        e.canonical_id = "abc123"
        store.upsert_events([e])
        read = store.get_event(e.id)
    assert read is not None
    assert read.canonical_id == "abc123"


def test_canonical_id_defaults_none(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        e = mk("tc", title="Solo", latitude=35.6, longitude=139.7)
        store.upsert_events([e])
        read = store.get_event(e.id)
    assert read is not None
    assert read.canonical_id is None


# --- upsert_with_dedup (même lot) ---


def test_upsert_with_dedup_merges_pair(tmp_path):
    db = str(tmp_path / "events.db")
    a, b = _fireworks_pair()
    c = mk("tc", title="Yoyogi Flea Market", latitude=35.671, longitude=139.694)
    with EventStore(db) as store:
        mapping = store.upsert_with_dedup([a, b, c])
        collapsed = store.get_events(collapse=True, limit=100)
        full = store.get_events(collapse=False, limit=100)
    assert mapping[a.id] == mapping[b.id]
    assert mapping[c.id] == c.id
    assert len(collapsed) == 2  # le cluster + l'événement distinct
    assert len(full) == 3


def test_upsert_with_dedup_sets_canonical_on_rows(tmp_path):
    db = str(tmp_path / "events.db")
    a, b = _fireworks_pair()
    with EventStore(db) as store:
        store.upsert_with_dedup([a, b])
        ra, rb = store.get_event(a.id), store.get_event(b.id)
    assert ra.canonical_id == rb.canonical_id
    assert ra.canonical_id in {a.id, b.id}


# --- upsert_with_dedup (cross-batch : doublon d'un scrape antérieur) ---


def test_dedup_cross_batch_updates_existing_row(tmp_path):
    db = str(tmp_path / "events.db")
    a, b = _fireworks_pair()
    with EventStore(db) as store:
        # Scrape 1 : seulement A, seul dans son cluster.
        store.upsert_with_dedup([a])
        assert store.get_event(a.id).canonical_id == a.id
        # Scrape 2 : B arrive (autre source), doublon de A déjà en base.
        store.upsert_with_dedup([b])
        ra, rb = store.get_event(a.id), store.get_event(b.id)
        collapsed = store.get_events(collapse=True, limit=100)
    assert ra.canonical_id == rb.canonical_id  # A a été rattaché au même cluster
    assert len(collapsed) == 1


def test_dedup_cross_batch_keeps_distinct_events_separate(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        a = mk("tc", title="Alpha Fest", latitude=35.10, longitude=139.10)
        store.upsert_with_dedup([a])
        b = mk("hanabi", title="Beta Fest", latitude=36.90, longitude=140.90)
        store.upsert_with_dedup([b])
        collapsed = store.get_events(collapse=True, limit=100)
    assert len(collapsed) == 2


# --- set_canonical_ids ---


def test_set_canonical_ids_updates(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        a = mk("tc", title="A", latitude=35.1, longitude=139.1)
        b = mk("tc", title="B", latitude=35.2, longitude=139.2)
        store.upsert_events([a, b])
        store.set_canonical_ids({b.id: a.id})
        assert store.get_event(b.id).canonical_id == a.id
        assert store.get_event(a.id).canonical_id is None


def test_set_canonical_ids_empty_is_noop(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.set_canonical_ids({})  # ne doit pas lever


# --- recompute_canonical (backfill) ---


def test_recompute_canonical_backfills(tmp_path):
    db = str(tmp_path / "events.db")
    a, b = _fireworks_pair()
    c = mk("tc", title="Unrelated Market", latitude=35.50, longitude=139.50)
    with EventStore(db) as store:
        # Insertion SANS dédup (comme une vieille base).
        store.upsert_events([a, b, c])
        assert store.get_event(a.id).canonical_id is None
        mapping = store.recompute_canonical()
        collapsed = store.get_events(collapse=True, limit=100)
    assert mapping[a.id] == mapping[b.id]
    assert len(collapsed) == 2


# --- collapse : sémantique NULL ---


def test_collapse_treats_null_as_canonical(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        # Lignes jamais dédupliquées (canonical_id NULL) : toutes visibles en collapse.
        a = mk("tc", title="A", latitude=35.1, longitude=139.1)
        b = mk("hanabi", title="B", latitude=36.9, longitude=140.9)
        store.upsert_events([a, b])
        collapsed = store.get_events(collapse=True, limit=100)
    assert len(collapsed) == 2


# --- Migration d'une base pré-existante (sans canonical_id) ---

_OLD_EVENTS_DDL = """
CREATE TABLE events (
    id TEXT PRIMARY KEY, source TEXT NOT NULL, title TEXT NOT NULL, url TEXT NOT NULL,
    start_date TEXT, end_date TEXT, times TEXT, venue TEXT, latitude REAL, longitude REAL,
    price TEXT, attributes TEXT, created_at TEXT NOT NULL
)
"""


def test_migration_adds_canonical_column_to_legacy_db(tmp_path):
    db = str(tmp_path / "legacy.db")
    conn = sqlite3.connect(db)
    conn.execute(_OLD_EVENTS_DDL)
    conn.execute(
        "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)",
        (
            "id1",
            "tc",
            "Legacy Event",
            "https://x",
            "2099-07-25",
            None,
            None,
            None,
            35.6,
            139.7,
            None,
            "{}",
            "2026-01-01T00:00:00+00:00",
        ),
    )
    conn.commit()
    conn.close()

    # init_schema doit ajouter la colonne sans perdre la ligne existante.
    conn = init_schema(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    assert "canonical_id" in cols
    row = conn.execute("SELECT canonical_id FROM events WHERE id='id1'").fetchone()
    conn.close()
    assert row[0] is None

    # Et le store relit correctement la ligne migrée.
    with EventStore(db) as store:
        e = store.get_event("id1")
    assert e is not None and e.title == "Legacy Event" and e.canonical_id is None


def test_init_schema_idempotent(tmp_path):
    db = str(tmp_path / "events.db")
    init_schema(db).close()
    # Réouvrir ne doit pas lever malgré l'ALTER déjà appliqué.
    conn = init_schema(db)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(events)").fetchall()}
    conn.close()
    assert "canonical_id" in cols
