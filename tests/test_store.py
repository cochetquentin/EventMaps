from datetime import date, datetime, timezone

import pytest

from db.store import EventStore, _make_id
from models.event import Event


# --- Fixtures ---

_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
_TC_URL = "https://tokyocheapo.com/event/foo"
_HW_URL = "https://hanabi.walkerplus.com/detail/ar0300e001/"


def make_tc(**kwargs) -> Event:
    defaults = dict(
        id=_make_id([_TC_URL, "Yoyogi Park"]),
        source="tc",
        title="Foo Festival",
        url=_TC_URL,
        start_date=date(2026, 5, 15),
        end_date=date(2026, 5, 15),
        times="10:00-18:00",
        latitude=35.671,
        longitude=139.694,
        price="Free",
        attributes={
            "categories": ["festival", "free"],
            "tags": ["outdoor"],
            "official_link": "https://example.com",
            "location_name": "Yoyogi Park",
        },
        created_at=_NOW,
    )
    defaults.update(kwargs)
    if "id" not in kwargs:
        loc = defaults.get("attributes", {}).get("location_name") or ""
        defaults["id"] = _make_id([defaults["url"], loc])
    return Event(**defaults)


def make_hanabi(**kwargs) -> Event:
    defaults = dict(
        id=_make_id([_HW_URL, "2026/07/25"]),
        source="hanabi",
        title="Sumida River Fireworks",
        url=_HW_URL,
        start_date=date(2026, 7, 25),
        times="19:05-20:30",
        venue="隅田川",
        latitude=35.711,
        longitude=139.801,
        attributes={
            "fireworks_count": "約2万発",
            "fireworks_duration": "90分",
            "expected_crowd": "約95万人",
            "rain_policy": "雨天決行",
            "paid_seating": "あり",
            "paid_seating_details": "S席: ¥5,000",
            "food_stalls": "あり",
            "access": "浅草駅",
            "parking": "なし",
            "official_site": "https://sumidagawa-hanabi.com",
            "contact": "03-1234-5678",
        },
        created_at=_NOW,
    )
    defaults.update(kwargs)
    if "id" not in kwargs:
        # Préserver la logique d'ID basée sur YYYY/MM/DD brut
        sd = defaults.get("start_date")
        if isinstance(sd, date):
            raw_date = sd.strftime("%Y/%m/%d")
        else:
            raw_date = str(sd) if sd else ""
        defaults["id"] = _make_id([defaults["url"], raw_date])
    return Event(**defaults)


# --- _make_id ---

def test_make_id_stable():
    assert _make_id(["https://example.com", "Yoyogi Park"]) == _make_id(["https://example.com", "Yoyogi Park"])
    result = _make_id(["https://example.com", "loc"])
    assert len(result) == 16
    assert result.isalnum()


# --- upsert_events (TC) ---

def test_upsert_tc_inserts_row(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_tc()])
        rows = store._conn.execute("SELECT id, title, latitude FROM events WHERE source='tc'").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Foo Festival"
    assert rows[0][2] == pytest.approx(35.671)


def test_upsert_tc_updates_on_rerun(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_tc()])
        store.upsert_events([make_tc(price="¥500")])
        result = store.get_event(make_tc().id)
    assert result is not None
    assert result.price == "¥500"


def test_upsert_tc_multi_location(tmp_path):
    db = str(tmp_path / "events.db")
    e1 = make_tc(attributes={"categories": [], "tags": [], "official_link": None, "location_name": "Yoyogi Park"})
    e2 = make_tc(
        latitude=35.685, longitude=139.710,
        attributes={"categories": [], "tags": [], "official_link": None, "location_name": "Shinjuku Gyoen"},
    )
    with EventStore(db) as store:
        store.upsert_events([e1, e2])
        rows = store._conn.execute(
            "SELECT id, attributes FROM events WHERE source='tc' ORDER BY id"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    import json
    loc_names = {json.loads(r[1]).get("location_name") for r in rows}
    assert loc_names == {"Yoyogi Park", "Shinjuku Gyoen"}


# --- upsert_events (Hanabi) ---

def test_upsert_hanabi_inserts_row(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_hanabi()])
        rows = store._conn.execute("SELECT title, start_date FROM events WHERE source='hanabi'").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "Sumida River Fireworks"
    assert rows[0][1] == "2026-07-25"


def test_upsert_hanabi_multiday(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([
            make_hanabi(start_date=date(2026, 7, 25)),
            make_hanabi(start_date=date(2026, 7, 26)),
        ])
        rows = store._conn.execute(
            "SELECT id, start_date FROM events WHERE source='hanabi' ORDER BY start_date"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert {r[1] for r in rows} == {"2026-07-25", "2026-07-26"}


def test_upsert_hanabi_updates_on_rerun(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_hanabi()])
        updated = make_hanabi()
        updated.attributes["expected_crowd"] = "約100万人"
        store.upsert_events([updated])
        result = store.get_event(make_hanabi().id)
    assert result is not None
    assert result.attributes["expected_crowd"] == "約100万人"


# --- Query ---

def test_get_events_all(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_tc(), make_hanabi()])
        results = store.get_events(upcoming=False)
    assert len(results) == 2
    sources = {e.source for e in results}
    assert sources == {"tc", "hanabi"}


def test_get_events_by_source(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_tc(), make_hanabi()])
        tc_only = store.get_events(source="tc", upcoming=False)
        hw_only = store.get_events(source="hanabi", upcoming=False)
    assert len(tc_only) == 1 and tc_only[0].source == "tc"
    assert len(hw_only) == 1 and hw_only[0].source == "hanabi"


def test_get_event_by_id(tmp_path):
    db = str(tmp_path / "events.db")
    event = make_tc()
    with EventStore(db) as store:
        store.upsert_events([event])
        result = store.get_event(event.id)
    assert result is not None
    assert result.title == "Foo Festival"
    assert result.source == "tc"


def test_get_event_not_found(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        result = store.get_event("nonexistent")
    assert result is None


# --- Scrape jobs ---

def test_start_finish_job(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        job_id = store.start_job("tc")
        last = store.get_last_job()
        assert last is not None
        assert last["status"] == "running"
        store.finish_job(job_id, 42)
        last = store.get_last_job()
        assert last["status"] == "done"
        assert last["events_scraped"] == 42


def test_fail_job(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        job_id = store.start_job("hanabi")
        store.fail_job(job_id, "timeout")
        last = store.get_last_job("hanabi")
        assert last is not None
        assert last["status"] == "failed"
        assert last["error"] == "timeout"


def test_get_last_job_none(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        assert store.get_last_job() is None


def test_get_last_job_by_source(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.start_job("tc")
        store.start_job("hanabi")
        last_tc = store.get_last_job("tc")
        last_hanabi = store.get_last_job("hanabi")
    assert last_tc["source"] == "tc"
    assert last_hanabi["source"] == "hanabi"


# --- Context manager ---

def test_context_manager(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_events([make_tc()])
    with pytest.raises(Exception):
        store._conn.execute("SELECT 1")


# --- Migration ---

def test_migration_from_old_schema(tmp_path):
    """Vérifie que les vieilles tables tokyo_cheapo et hanabi sont migrées automatiquement."""
    import json
    import sqlite3

    db = str(tmp_path / "events.db")
    conn = sqlite3.connect(db)
    conn.execute("PRAGMA journal_mode=WAL")

    # Créer les vieilles tables
    conn.execute("""
        CREATE TABLE tokyo_cheapo (
            id TEXT PRIMARY KEY, title TEXT, start_date TEXT, end_date TEXT,
            start_time TEXT, end_time TEXT, price TEXT, categories TEXT, tags TEXT,
            official_link TEXT, url TEXT NOT NULL, location_name TEXT,
            lat REAL, lng REAL, scraped_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO tokyo_cheapo VALUES (
            'abc123', 'Old TC Event', '2026/05/15', '2026/05/15',
            '10:00', '18:00', 'Free', '["festival"]', '["outdoor"]',
            'https://example.com', 'https://tokyocheapo.com/event/old', 'Yoyogi Park',
            35.671, 139.694, '2026-05-01T00:00:00+00:00'
        )
    """)

    conn.execute("""
        CREATE TABLE hanabi (
            id TEXT PRIMARY KEY, title TEXT, fireworks_count TEXT,
            fireworks_duration TEXT, expected_crowd TEXT, start_time TEXT, end_time TEXT,
            rain_policy TEXT, paid_seating TEXT, paid_seating_details TEXT,
            food_stalls TEXT, notes TEXT, venue TEXT, access TEXT, parking TEXT,
            official_site TEXT, official_x TEXT, url TEXT NOT NULL,
            lat REAL, lng REAL, date TEXT, contact TEXT, contact2 TEXT,
            scraped_at TEXT NOT NULL
        )
    """)
    conn.execute("""
        INSERT INTO hanabi VALUES (
            'def456', 'Old Hanabi', '約1万発', NULL, NULL, '19:00', '20:30',
            NULL, NULL, NULL, NULL, NULL, '隅田川', NULL, NULL, NULL, NULL,
            'https://hanabi.walkerplus.com/detail/ar0300e001/',
            35.711, 139.801, '2026/07/25', NULL, NULL,
            '2026-05-01T00:00:00+00:00'
        )
    """)
    conn.commit()
    conn.close()

    # Ouvrir via EventStore → déclenche la migration
    with EventStore(db) as store:
        events = store.get_events(upcoming=False)
        tc = next(e for e in events if e.source == "tc")
        hw = next(e for e in events if e.source == "hanabi")

    # Vérifier que les données sont bien migrées
    assert tc.id == "abc123"
    assert tc.title == "Old TC Event"
    assert str(tc.start_date) == "2026-05-15"
    assert tc.times == "10:00-18:00"
    assert tc.attributes["categories"] == ["festival"]
    assert tc.attributes["location_name"] == "Yoyogi Park"
    assert tc.venue is None

    assert hw.id == "def456"
    assert hw.title == "Old Hanabi"
    assert str(hw.start_date) == "2026-07-25"
    assert hw.venue == "隅田川"
    assert hw.attributes["fireworks_count"] == "約1万発"

    # Vérifier que les vieilles tables ont été supprimées
    with EventStore(db) as store:
        tables = {r[0] for r in store._conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        ).fetchall()}
    assert "tokyo_cheapo" not in tables
    assert "hanabi" not in tables


# --- Upcoming filter ---

def test_upcoming_excludes_past(tmp_path):
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    past = make_tc(start_date=today - timedelta(days=10), end_date=today - timedelta(days=5))
    future = make_hanabi(start_date=today + timedelta(days=10))
    with EventStore(db) as store:
        store.upsert_events([past, future])
        results = store.get_events()
    assert len(results) == 1
    assert results[0].source == "hanabi"


def test_upcoming_keeps_ongoing(tmp_path):
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    ongoing = make_tc(start_date=today - timedelta(days=2), end_date=today + timedelta(days=2))
    with EventStore(db) as store:
        store.upsert_events([ongoing])
        results = store.get_events()
    assert len(results) == 1


def test_upcoming_false_returns_all(tmp_path):
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    past = make_tc(start_date=today - timedelta(days=30), end_date=today - timedelta(days=25))
    with EventStore(db) as store:
        store.upsert_events([past])
        results = store.get_events(upcoming=False)
    assert len(results) == 1


def test_date_param_overrides_upcoming(tmp_path):
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    past = make_tc(start_date=today - timedelta(days=10), end_date=today - timedelta(days=10))
    with EventStore(db) as store:
        store.upsert_events([past])
        date_str = (today - timedelta(days=10)).isoformat()
        results = store.get_events(date=date_str)
    assert len(results) == 1


def test_start_from_returns_past_events(tmp_path):
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    past = make_tc(start_date=today - timedelta(days=10), end_date=today - timedelta(days=5))
    future = make_hanabi(start_date=today + timedelta(days=5))
    with EventStore(db) as store:
        store.upsert_events([past, future])
        start_from = (today - timedelta(days=15)).isoformat()
        results = store.get_events(start_from=start_from)
    assert len(results) == 2


def test_start_from_overrides_upcoming(tmp_path):
    """start_from disables the JST-today default when provided."""
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    past = make_tc(start_date=today - timedelta(days=10), end_date=today - timedelta(days=5))
    with EventStore(db) as store:
        store.upsert_events([past])
        # Without start_from, upcoming=True filters past event out
        assert store.get_events() == []
        # With start_from in the past, event is included
        results = store.get_events(start_from=(today - timedelta(days=15)).isoformat())
    assert len(results) == 1


def test_start_to_alone_upper_bound(tmp_path):
    """start_to alone applies upper bound and disables the upcoming default."""
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    near = make_tc(start_date=today + timedelta(days=3), end_date=None)
    far = make_hanabi(start_date=today + timedelta(days=30))
    with EventStore(db) as store:
        store.upsert_events([near, far])
        results = store.get_events(start_to=(today + timedelta(days=10)).isoformat())
    assert len(results) == 1
    assert results[0].source == "tc"


def test_start_from_and_start_to_range(tmp_path):
    """Both bounds together return only events within the window."""
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    inside = make_tc(start_date=today + timedelta(days=5), end_date=None)
    before = make_tc(
        url="https://tokyocheapo.com/event/before",
        start_date=today - timedelta(days=5),
        end_date=None,
        attributes={"categories": [], "tags": [], "official_link": None, "location_name": "Before"},
    )
    after = make_hanabi(start_date=today + timedelta(days=20))
    with EventStore(db) as store:
        store.upsert_events([inside, before, after])
        results = store.get_events(
            start_from=(today + timedelta(days=1)).isoformat(),
            start_to=(today + timedelta(days=10)).isoformat(),
        )
    assert len(results) == 1
    assert results[0].source == "tc"
    assert results[0].start_date == today + timedelta(days=5)


def test_start_to_includes_multiday_spanning_range(tmp_path):
    """Multi-day event starting before start_from but ending after is included."""
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    spanning = make_tc(
        start_date=today - timedelta(days=2),
        end_date=today + timedelta(days=5),
    )
    with EventStore(db) as store:
        store.upsert_events([spanning])
        results = store.get_events(
            start_from=today.isoformat(),
            start_to=(today + timedelta(days=10)).isoformat(),
        )
    assert len(results) == 1


def test_start_to_suppresses_upcoming(tmp_path):
    """start_to alone disables the default upcoming filter."""
    from datetime import timedelta
    db = str(tmp_path / "events.db")
    today = date.today()
    soon = make_tc(start_date=today + timedelta(days=2), end_date=None)
    later = make_hanabi(start_date=today + timedelta(days=30))
    with EventStore(db) as store:
        store.upsert_events([soon, later])
        results = store.get_events(start_to=(today + timedelta(days=5)).isoformat())
    assert len(results) == 1
    assert results[0].source == "tc"


# --- Bbox filter ---

def test_bbox_filters_by_coords(tmp_path):
    db = str(tmp_path / "events.db")
    # TC: lat=35.671, lon=139.694 → inside
    # Hanabi: lat=35.711, lon=139.801 → outside
    bbox = (139.68, 35.65, 139.71, 35.69)
    with EventStore(db) as store:
        store.upsert_events([make_tc(), make_hanabi()])
        results = store.get_events(bbox=bbox, upcoming=False)
    assert len(results) == 1
    assert results[0].source == "tc"


def test_bbox_excludes_null_coords(tmp_path):
    db = str(tmp_path / "events.db")
    no_coords = make_tc(latitude=None, longitude=None)
    bbox = (139.0, 35.0, 140.0, 36.0)
    with EventStore(db) as store:
        store.upsert_events([no_coords])
        results = store.get_events(bbox=bbox, upcoming=False)
    assert len(results) == 0


def test_no_bbox_includes_null_coords(tmp_path):
    db = str(tmp_path / "events.db")
    no_coords = make_tc(latitude=None, longitude=None)
    with EventStore(db) as store:
        store.upsert_events([no_coords])
        results = store.get_events(upcoming=False)
    assert len(results) == 1


def test_bbox_combined_with_source(tmp_path):
    db = str(tmp_path / "events.db")
    bbox = (139.68, 35.65, 139.71, 35.69)
    with EventStore(db) as store:
        store.upsert_events([make_tc(), make_hanabi()])
        results = store.get_events(source="tc", bbox=bbox, upcoming=False)
    assert len(results) == 1
    assert results[0].source == "tc"


def test_event_attributes_not_shared():
    e1 = make_tc(attributes={})
    e2 = make_tc(attributes={})
    e1.attributes["foo"] = "bar"
    assert "foo" not in e2.attributes
