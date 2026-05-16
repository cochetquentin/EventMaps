import json

import pytest

from store import EventStore, _make_id


# --- Fixtures ---

TC_EVENT = {
    "url": "https://tokyocheapo.com/event/foo",
    "title": "Foo Festival",
    "start_date": "2026/05/15",
    "end_date": "2026/05/15",
    "start_time": "10:00",
    "end_time": "18:00",
    "price": "Free",
    "categories": ["festival", "free"],
    "tags": ["outdoor"],
    "official_link": "https://example.com",
    "location_name": "Yoyogi Park",
    "lat": 35.671,
    "lng": 139.694,
}

HANABI_EVENT = {
    "url": "https://hanabi.walkerplus.com/detail/ar0300e001/",
    "title": "Sumida River Fireworks",
    "fireworks_count": "約2万発",
    "fireworks_duration": "90分",
    "expected_crowd": "約95万人",
    "start_time": "19:05",
    "end_time": "20:30",
    "rain_policy": "雨天決行",
    "paid_seating": "あり",
    "paid_seating_details": "S席: ¥5,000",
    "food_stalls": "あり",
    "notes": "",
    "venue": "隅田川",
    "access": "浅草駅",
    "parking": "なし",
    "official_site": "https://sumidagawa-hanabi.com",
    "official_x": None,
    "lat": 35.711,
    "lng": 139.801,
    "date": "2026/07/25",
    "contact": "03-1234-5678",
    "contact2": "",
}


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
        store.upsert_tokyo_cheapo([TC_EVENT])
        rows = store._conn.execute("SELECT * FROM tokyo_cheapo").fetchall()
    assert len(rows) == 1
    row = rows[0]
    assert row[1] == "Foo Festival"
    assert row[11] == "Yoyogi Park"
    assert row[12] == pytest.approx(35.671)


def test_upsert_tc_updates_on_rerun(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([TC_EVENT])
        updated = {**TC_EVENT, "price": "¥500"}
        store.upsert_tokyo_cheapo([updated])
        rows = store._conn.execute("SELECT * FROM tokyo_cheapo").fetchall()
    assert len(rows) == 1
    assert rows[0][6] == "¥500"


def test_upsert_tc_multi_location(tmp_path):
    db = str(tmp_path / "events.db")
    loc2 = {**TC_EVENT, "location_name": "Shinjuku Gyoen", "lat": 35.685, "lng": 139.710}
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([TC_EVENT, loc2])
        rows = store._conn.execute("SELECT id, location_name FROM tokyo_cheapo ORDER BY location_name").fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert {r[1] for r in rows} == {"Yoyogi Park", "Shinjuku Gyoen"}


# --- Hanabi ---

def test_upsert_hanabi_inserts_row(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_hanabi([HANABI_EVENT])
        rows = store._conn.execute("SELECT * FROM hanabi").fetchall()
    assert len(rows) == 1
    assert rows[0][1] == "Sumida River Fireworks"
    assert rows[0][20] == "2026/07/25"


def test_upsert_hanabi_multiday(tmp_path):
    db = str(tmp_path / "events.db")
    day2 = {**HANABI_EVENT, "date": "2026/07/26"}
    with EventStore(db) as store:
        store.upsert_hanabi([HANABI_EVENT, day2])
        rows = store._conn.execute("SELECT id, date FROM hanabi ORDER BY date").fetchall()
    assert len(rows) == 2
    assert rows[0][0] != rows[1][0]
    assert {r[1] for r in rows} == {"2026/07/25", "2026/07/26"}


def test_upsert_hanabi_updates_on_rerun(tmp_path):
    db = str(tmp_path / "events.db")
    with EventStore(db) as store:
        store.upsert_hanabi([HANABI_EVENT])
        updated = {**HANABI_EVENT, "expected_crowd": "約100万人"}
        store.upsert_hanabi([updated])
        rows = store._conn.execute("SELECT expected_crowd FROM hanabi").fetchall()
    assert len(rows) == 1
    assert rows[0][0] == "約100万人"


# --- CSV export ---

def test_export_tc_csv_roundtrip(tmp_path):
    db = str(tmp_path / "events.db")
    out = str(tmp_path / "out.csv")
    with EventStore(db) as store:
        store.upsert_tokyo_cheapo([TC_EVENT])
        store.export_tokyo_cheapo_csv(out)

    import csv
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
        store.upsert_hanabi([HANABI_EVENT])
        store.export_hanabi_csv(out)

    import csv
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
        store.upsert_tokyo_cheapo([TC_EVENT])
    # Connection is closed — accessing it should fail
    with pytest.raises(Exception):
        store._conn.execute("SELECT 1")
