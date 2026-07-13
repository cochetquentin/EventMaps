"""Tests du script de backfill des canonical_id."""

from datetime import UTC, date, datetime

from db.store import EventStore
from models.event import Event
from models.identity import make_event_id
from tools.backfill_canonical import backfill

_FUT = date(2099, 7, 25)


def mk(source, title, url, lat, lon, **over) -> Event:
    base = dict(
        id=make_event_id([url, title, source]),
        source=source,
        title=title,
        url=url,
        start_date=_FUT,
        latitude=lat,
        longitude=lon,
        attributes=over.pop("attributes", {}),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(over)
    return Event(**base)


def test_backfill_groups_duplicates(tmp_path):
    db = str(tmp_path / "events.db")
    a = mk("hanabi", "Sumida River Fireworks", "https://h/1", 35.7110, 139.8010, venue="Sumida")
    b = mk(
        "tc",
        "Sumida River Fireworks",
        "https://tc/1",
        35.7120,
        139.8012,
        attributes={"location_name": "Sumida"},
    )
    c = mk("tc", "Distinct Market", "https://tc/2", 35.50, 139.50)
    with EventStore(db) as store:
        store.upsert_events([a, b, c])  # insertion brute, sans dédup

    mapping = backfill(db)

    assert mapping[a.id] == mapping[b.id]
    assert mapping[c.id] == c.id
    with EventStore(db) as store:
        assert len(store.get_events(collapse=True, limit=100)) == 2


def test_backfill_idempotent(tmp_path):
    db = str(tmp_path / "events.db")
    a = mk("hanabi", "Sumida River Fireworks", "https://h/1", 35.7110, 139.8010, venue="Sumida")
    b = mk(
        "tc",
        "Sumida River Fireworks",
        "https://tc/1",
        35.7120,
        139.8012,
        attributes={"location_name": "Sumida"},
    )
    with EventStore(db) as store:
        store.upsert_events([a, b])

    first = backfill(db)
    second = backfill(db)
    assert first == second


def test_backfill_empty_db(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db):
        pass
    assert backfill(db) == {}
