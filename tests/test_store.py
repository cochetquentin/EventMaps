import csv
from datetime import datetime, timezone

import pytest

from db.store import EventStore, _make_id
from models.event import HanabiEvent, TokyoCheapoEvent


# --- Fixtures ---

_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
_TC_URL = "https://tokyocheapo.com/event/foo"
_HW_URL = "https://hanabi.walkerplus.com/detail/ar0300e001/"


def make_tc(**kwargs) -> TokyoCheapoEvent:
    defaults = dict(
        id=_make_id([_TC_URL, "Yoyogi Park"]),
        scraped_at=_NOW,
        title="Foo Festival",
        url=_TC_URL,
        start_date="2026/05/15",
        end_date="2026/05/15",
        start_time="10:00",
        end_time="18:00",
        price="Free",
        categories=["festival", "free"],
        tags=["outdoor"],
        official_link="https://example.com",
        location_name="Yoyogi Park",
        lat=35.671,
        lng=139.694,
    )
    defaults.update(kwargs)
    if "id" not in kwargs:
        defaults["id"] = _make_id([defaults["url"], defaults.get("location_name") or ""])
    return TokyoCheapoEvent(**defaults)


def make_hanabi(**kwargs) -> HanabiEvent:
    defaults = dict(
        id=_make_id([_HW_URL, "2026/07/25"]),
        scraped_at=_NOW,
        title="Sumida River Fireworks",
        url=_HW_URL,
        start_date="2026/07/25",
        start_time="19:05",
        end_time="20:30",
        lat=35.711,
        lng=139.801,
        fireworks_count="約2万発",
        fireworks_duration="90分",
        expected_crowd="約95万人",
        rain_policy="雨天決行",
        paid_seating="あり",
        paid_seating_details="S席: ¥5,000",
        food_stalls="あり",
        venue="隅田川",
        access="浅草駅",
        parking="なし",
        official_site="https://sumidagawa-hanabi.com",
        contact="03-1234-5678",
    )
    defaults.update(kwargs)
    if "id" not in kwargs:
        defaults["id"] = _make_id([defaults["url"], defaults.get("start_date") or ""])
    return HanabiEvent(**defaults)


# --- _make_id ---

def test_make_id_stable():
    assert _make_id(["https://example.com", "Yoyogi Park"]) == _make_id(["https://example.com", "Yoyogi Park"])
    result = _make_id(["https://example.com", "loc"])
    assert len(result) == 16
    assert result.isalnum()


# --- TokyoCheapo ---

def test_upsert_tc_inserts_row(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([make_tc()])
        rows = store._conn.execute("SELECT * FROM tokyo_cheapo").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Foo Festival"
    assert rows[0][11] == "Yoyogi Park"
    assert rows[0][12] == pytest.approx(35.671)


def test_upsert_tc_updates_on_rerun(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([make_tc()])
        store.upsert_tokyo_cheapo([make_tc(price="¥500")])
        rows = store._conn.execute("SELECT * FROM tokyo_cheapo").fetchall()
    assert len(rows) == 1
    assert rows[0][6] == "¥500"


def test_upsert_tc_multi_location(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([
            make_tc(location_name="Yoyogi Park"),
            make_tc(location_name="Shinjuku Gyoen", lat=35.685, lng=139.710),
        ])
        rows = store._conn.execute(
            "SELECT id, location_name FROM tokyo_cheapo ORDER BY location_name"
        ).fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert {r[1] for r in rows} == {"Yoyogi Park", "Shinjuku Gyoen"}


# --- Hanabi ---

def test_upsert_hanabi_inserts_row(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_hanabi([make_hanabi()])
        rows = store._conn.execute("SELECT * FROM hanabi").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Sumida River Fireworks"
    assert rows[0][20] == "2026/07/25"


def test_upsert_hanabi_multiday(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_hanabi([
            make_hanabi(start_date="2026/07/25"),
            make_hanabi(start_date="2026/07/26"),
        ])
        rows = store._conn.execute("SELECT id, date FROM hanabi ORDER BY date").fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert {r[1] for r in rows} == {"2026/07/25", "2026/07/26"}


def test_upsert_hanabi_updates_on_rerun(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_hanabi([make_hanabi()])
        store.upsert_hanabi([make_hanabi(expected_crowd="約100万人")])
        rows = store._conn.execute("SELECT expected_crowd FROM hanabi").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "約100万人"


# --- Query ---

def test_get_events_all(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([make_tc()])
        store.upsert_hanabi([make_hanabi()])
        results = store.get_events()
    assert len(results) == 2
    sources = {e.source for e in results}
    assert sources == {"tc", "hanabi"}


def test_get_events_by_source(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([make_tc()])
        store.upsert_hanabi([make_hanabi()])
        tc_only = store.get_events(source="tc")
        hw_only = store.get_events(source="hanabi")
    assert len(tc_only) == 1 and tc_only[0].source == "tc"
    assert len(hw_only) == 1 and hw_only[0].source == "hanabi"


def test_get_event_by_id(tmp_path):
    db = str(tmp_path / "events.db")
    event = make_tc()
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([event])
        result = store.get_event(event.id)
    assert result is not None
    assert result.title == "Foo Festival"
    assert result.source == "tc"


def test_get_event_not_found(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        result = store.get_event("nonexistent")
    assert result is None


# --- CSV export ---

def test_export_tc_csv_roundtrip(tmp_path):
    db = str(tmp_path / "events.db")
    out = str(tmp_path / "out.csv")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([make_tc()])
        store.export_tokyo_cheapo_csv(out)

    with open(out, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["title"] == "Foo Festival"
    assert rows[0]["categories"] == "festival, free"
    assert rows[0]["location_name"] == "Yoyogi Park"


def test_export_hanabi_csv_roundtrip(tmp_path):
    db = str(tmp_path / "events.db")
    out = str(tmp_path / "out.csv")
    with EventStore(db) as store:
        store.upsert_hanabi([make_hanabi()])
        store.export_hanabi_csv(out)

    with open(out, encoding="utf-8-sig") as f:
        rows = list(csv.DictReader(f))
    assert len(rows) == 1
    assert rows[0]["title"] == "Sumida River Fireworks"
    assert rows[0]["date"] == "2026/07/25"
    assert rows[0]["paid_seating"] == "あり"


# --- Context manager ---

def test_context_manager(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([make_tc()])
    with pytest.raises(Exception):
        store._conn.execute("SELECT 1")
