import pytest
from datetime import date, datetime, timezone
from fastapi.testclient import TestClient

from api.app import app
from db.store import EventStore, _make_id
from models.event import Event

_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=timezone.utc)
_TC_URL = "https://tokyocheapo.com/event/foo"
_HW_URL = "https://hanabi.walkerplus.com/detail/ar0300e001/"


def make_tc(**kwargs) -> Event:
    defaults = dict(
        source="tc",
        title="Foo Festival",
        url=_TC_URL,
        start_date=date(2026, 5, 15),
        latitude=35.671,
        longitude=139.694,
        attributes={
            "categories": ["festival"],
            "tags": [],
            "official_link": None,
            "location_name": "Yoyogi Park",
        },
        created_at=_NOW,
    )
    defaults.update(kwargs)
    defaults.setdefault(
        "id",
        _make_id([defaults["url"], defaults.get("attributes", {}).get("location_name") or ""])
    )
    return Event(**defaults)


def make_hanabi(**kwargs) -> Event:
    defaults = dict(
        source="hanabi",
        title="Sumida Fireworks",
        url=_HW_URL,
        start_date=date(2026, 7, 25),
        venue="隅田川",
        latitude=35.711,
        longitude=139.801,
        attributes={},
        created_at=_NOW,
    )
    defaults.update(kwargs)
    sd = defaults.get("start_date")
    raw_date = sd.strftime("%Y/%m/%d") if isinstance(sd, date) else str(sd) if sd else ""
    defaults.setdefault("id", _make_id([defaults["url"], raw_date]))
    return Event(**defaults)


@pytest.fixture()
def db(tmp_path):
    """Return a populated DB path and patch the route to use it."""
    import api.routes.events as route_module
    db_path = str(tmp_path / "events.db")
    with EventStore(db_path) as store:
        store.upsert_events([make_tc(), make_hanabi()])
    original = route_module.DB_PATH
    route_module.DB_PATH = db_path
    yield db_path
    route_module.DB_PATH = original


@pytest.fixture()
def client(db):
    return TestClient(app)


# --- GET /events ---

def test_list_events_returns_both_sources(client):
    resp = client.get("/events")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 2
    sources = {e["source"] for e in data}
    assert sources == {"tc", "hanabi"}


def test_list_events_filter_tc(client):
    resp = client.get("/events?source=tc")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "tc"
    assert data[0]["title"] == "Foo Festival"


def test_list_events_filter_hanabi(client):
    resp = client.get("/events?source=hanabi")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"
    assert data[0]["title"] == "Sumida Fireworks"


def test_list_events_filter_by_date(client):
    resp = client.get("/events?date=2026-07-25")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"


def test_list_events_pagination(db):
    import api.routes.events as route_module
    with EventStore(db) as store:
        store.upsert_events([
            make_tc(
                url=f"https://tokyocheapo.com/event/{i}",
                attributes={"categories": [], "tags": [], "official_link": None, "location_name": f"Loc {i}"},
            )
            for i in range(5)
        ])
    client = TestClient(app)
    resp = client.get("/events?source=tc&limit=3&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    resp2 = client.get("/events?source=tc&limit=3&offset=3")
    assert resp2.status_code == 200
    assert len(resp2.json()) >= 1


def test_list_events_empty_db(tmp_path):
    import api.routes.events as route_module
    db_path = str(tmp_path / "empty.db")
    EventStore(db_path).close()
    original = route_module.DB_PATH
    route_module.DB_PATH = db_path
    resp = TestClient(app).get("/events")
    route_module.DB_PATH = original
    assert resp.status_code == 200
    assert resp.json() == []


# --- GET /events/{id} ---

def test_get_event_tc(client):
    event = make_tc()
    resp = client.get(f"/events/{event.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["id"] == event.id
    assert data["source"] == "tc"
    assert data["title"] == "Foo Festival"
    assert data["attributes"]["categories"] == ["festival"]


def test_get_event_hanabi(client):
    event = make_hanabi()
    resp = client.get(f"/events/{event.id}")
    assert resp.status_code == 200
    data = resp.json()
    assert data["source"] == "hanabi"
    assert data["title"] == "Sumida Fireworks"


def test_get_event_not_found(client):
    resp = client.get("/events/doesnotexist")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Event not found"


def test_event_shape_tc(client):
    event = make_tc()
    data = client.get(f"/events/{event.id}").json()
    for field in ["id", "source", "title", "url", "start_date", "latitude", "longitude", "attributes"]:
        assert field in data


def test_event_shape_hanabi(client):
    event = make_hanabi()
    data = client.get(f"/events/{event.id}").json()
    for field in ["id", "source", "title", "url", "start_date", "latitude", "longitude"]:
        assert field in data
