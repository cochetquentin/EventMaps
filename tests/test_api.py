from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import app
from db.store import EventStore, _make_id
from models.event import Event

_NOW = datetime(2026, 5, 16, 12, 0, 0, tzinfo=UTC)
_TC_URL = "https://tokyocheapo.com/event/foo"
_HW_URL = "https://hanabi.walkerplus.com/detail/ar0300e001/"


_TC_START = date.today() + timedelta(days=90)  # always in the future
_HW_START = date.today() + timedelta(days=60)  # always in the future, < TC


def make_tc(**kwargs) -> Event:
    defaults = dict(
        source="tc",
        title="Foo Festival",
        url=_TC_URL,
        start_date=_TC_START,
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
        "id", _make_id([defaults["url"], defaults.get("attributes", {}).get("location_name") or ""])
    )
    return Event(**defaults)


def make_hanabi(**kwargs) -> Event:
    defaults = dict(
        source="hanabi",
        title="Sumida Fireworks",
        url=_HW_URL,
        start_date=_HW_START,
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
def db(tmp_path, monkeypatch):
    """Return a populated DB path and patch settings to use it."""
    import config

    db_path = str(tmp_path / "events.db")
    with EventStore(db_path) as store:
        store.upsert_events([make_tc(), make_hanabi()])
    monkeypatch.setattr(config.settings, "db_path", db_path)
    return db_path


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
    hanabi = make_hanabi()
    resp = client.get(f"/events?date={hanabi.start_date.isoformat()}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"


def test_start_to_filters_upper_bound(client):
    # _HW_START = today+60, _TC_START = today+90
    # start_to at today+70 should include hanabi but not tc
    cutoff = (date.today() + timedelta(days=70)).isoformat()
    resp = client.get(f"/events?start_to={cutoff}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"


def test_invalid_start_to_returns_422(client):
    resp = client.get("/events?start_to=not-a-date")
    assert resp.status_code == 422


def test_start_from_and_start_to_combined(client):
    # Window today+50 → today+70 includes hanabi (today+60) but not tc (today+90)
    from_date = (date.today() + timedelta(days=50)).isoformat()
    to_date = (date.today() + timedelta(days=70)).isoformat()
    resp = client.get(f"/events?start_from={from_date}&start_to={to_date}")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"


def test_list_events_pagination(db, monkeypatch):
    with EventStore(db) as store:
        store.upsert_events(
            [
                make_tc(
                    url=f"https://tokyocheapo.com/event/{i}",
                    attributes={
                        "categories": [],
                        "tags": [],
                        "official_link": None,
                        "location_name": f"Loc {i}",
                    },
                )
                for i in range(5)
            ]
        )
    client = TestClient(app)
    resp = client.get("/events?source=tc&limit=3&offset=0")
    assert resp.status_code == 200
    assert len(resp.json()) == 3

    resp2 = client.get("/events?source=tc&limit=3&offset=3")
    assert resp2.status_code == 200
    assert len(resp2.json()) >= 1


def test_list_events_empty_db(tmp_path, monkeypatch):
    import config

    db_path = str(tmp_path / "empty.db")
    EventStore(db_path).close()
    monkeypatch.setattr(config.settings, "db_path", db_path)
    resp = TestClient(app).get("/events")
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
    for field in [
        "id",
        "source",
        "title",
        "url",
        "start_date",
        "latitude",
        "longitude",
        "attributes",
    ]:
        assert field in data


def test_event_shape_hanabi(client):
    event = make_hanabi()
    data = client.get(f"/events/{event.id}").json()
    for field in ["id", "source", "title", "url", "start_date", "latitude", "longitude"]:
        assert field in data


# --- Validation 422 ---


def test_invalid_source_returns_422(client):
    resp = client.get("/events?source=invalid")
    assert resp.status_code == 422


def test_invalid_date_returns_422(client):
    resp = client.get("/events?date=not-a-date")
    assert resp.status_code == 422


def test_limit_zero_returns_422(client):
    resp = client.get("/events?limit=0")
    assert resp.status_code == 422


def test_limit_above_max_returns_422(client):
    resp = client.get("/events?limit=501")
    assert resp.status_code == 422


def test_limit_max_accepted(client):
    resp = client.get("/events?limit=500")
    assert resp.status_code == 200


# --- iCal export ---


def test_ical_returns_vcalendar(client):
    event = make_tc()
    resp = client.get(f"/events/{event.id}.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]
    body = resp.text
    assert "BEGIN:VCALENDAR" in body
    assert "BEGIN:VEVENT" in body
    assert "END:VEVENT" in body
    assert "END:VCALENDAR" in body


def test_ical_has_summary(client):
    event = make_tc()
    resp = client.get(f"/events/{event.id}.ics")
    assert resp.status_code == 200
    assert "SUMMARY:Foo Festival" in resp.text


def test_ical_dtstart_is_date(client):
    event = make_tc()
    resp = client.get(f"/events/{event.id}.ics")
    assert "DTSTART;VALUE=DATE:" in resp.text


def test_ical_dtend_is_day_after(client):
    event = make_tc()
    resp = client.get(f"/events/{event.id}.ics")
    assert "DTEND;VALUE=DATE:" in resp.text


def test_ical_not_found(client):
    resp = client.get("/events/doesnotexist.ics")
    assert resp.status_code == 404


def test_ical_hanabi_has_location(client):
    event = make_hanabi()
    resp = client.get(f"/events/{event.id}.ics")
    assert resp.status_code == 200
    assert "LOCATION" in resp.text


# --- GET /events.ics (liste filtrée) ---


def test_export_ics_returns_vcalendar(client):
    make_tc()
    make_hanabi()
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert "text/calendar" in resp.headers["content-type"]
    body = resp.text
    assert "BEGIN:VCALENDAR" in body
    assert body.count("BEGIN:VEVENT") == 2
    assert "END:VCALENDAR" in body


def test_export_ics_filter_source(client):
    make_tc()
    make_hanabi()
    resp = client.get("/events.ics?source=tc")
    assert resp.status_code == 200
    assert resp.text.count("BEGIN:VEVENT") == 1
    assert "SUMMARY:Foo Festival" in resp.text


def test_export_ics_filter_q(client):
    make_tc()
    make_hanabi()
    resp = client.get("/events.ics?q=Sumida")
    assert resp.status_code == 200
    assert resp.text.count("BEGIN:VEVENT") == 1
    assert "SUMMARY:Sumida Fireworks" in resp.text


def test_export_ics_content_disposition(client):
    resp = client.get("/events.ics")
    assert resp.status_code == 200
    assert resp.headers["content-disposition"] == 'attachment; filename="events.ics"'


def test_export_ics_empty_result(client):
    resp = client.get("/events.ics?q=nonexistentxyz")
    assert resp.status_code == 204
    assert resp.content == b""


# --- Bbox filter ---


def test_bbox_returns_tc_event(client):
    # TC: lat=35.671, lon=139.694 → inside; Hanabi: lat=35.711, lon=139.801 → outside
    bbox = "139.68,35.65,139.71,35.69"
    resp = client.get(f"/events?bbox={bbox}")
    assert resp.status_code == 200
    data = resp.json()
    assert all(e["source"] == "tc" for e in data)


def test_bbox_invalid_format_422(client):
    resp = client.get("/events?bbox=not,a,valid,bbox")
    assert resp.status_code == 422


def test_bbox_wrong_count_422(client):
    resp = client.get("/events?bbox=139.0,35.0,140.0")
    assert resp.status_code == 422


def test_bbox_inverted_range_422(client):
    resp = client.get("/events?bbox=140.0,35.0,139.0,36.0")
    assert resp.status_code == 422


# --- Search q param ---


def test_search_q_matches_title(client):
    resp = client.get("/events?q=Foo")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Foo Festival"


def test_search_q_case_insensitive(client):
    resp = client.get("/events?q=foo")
    assert resp.status_code == 200
    assert len(resp.json()) == 1


def test_search_q_matches_hanabi(client):
    resp = client.get("/events?q=Sumida")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"


def test_search_q_matches_venue(client):
    # make_hanabi has venue="隅田川" — q doit chercher aussi dans venue
    resp = client.get("/events?q=隅田川")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "hanabi"


def test_search_q_matches_location_name(client):
    # make_tc has location_name="Yoyogi Park" dans attributes
    resp = client.get("/events?q=Yoyogi")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "tc"


def test_search_q_no_match_returns_empty(client):
    resp = client.get("/events?q=NOMATCH_XYZ")
    assert resp.status_code == 200
    assert resp.json() == []


def test_search_q_empty_string_returns_all(client):
    resp = client.get("/events?q=")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# --- Category filter ---


def test_category_filter_matches_tc_event(client):
    resp = client.get("/events?category=festival")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["source"] == "tc"


def test_category_filter_excludes_hanabi(client):
    resp = client.get("/events?category=festival")
    assert resp.status_code == 200
    assert all(e["source"] == "tc" for e in resp.json())


def test_category_no_match_returns_empty(client):
    resp = client.get("/events?category=NONEXISTENT")
    assert resp.status_code == 200
    assert resp.json() == []


def test_category_exact_match_only(db, monkeypatch):
    """Un tag nommé 'festival' dans un autre champ ne doit pas créer un faux positif."""
    import config

    monkeypatch.setattr(config.settings, "db_path", db)
    # Créer un TC event dont location_name contient "festival" mais pas dans categories
    with EventStore(db) as store:
        tricky = make_tc(
            url="https://tokyocheapo.com/event/tricky",
            attributes={
                "categories": ["music"],
                "tags": ["festival-related"],
                "official_link": None,
                "location_name": "festival hall",
            },
        )
        store.upsert_events([tricky])
    client_local = TestClient(app)
    resp = client_local.get("/events?category=festival")
    assert resp.status_code == 200
    # Seul le TC event original (categories=["festival"]) doit matcher, pas tricky
    data = resp.json()
    assert all("festival" in (e["attributes"].get("categories") or []) for e in data)


def test_category_empty_string_returns_all(client):
    resp = client.get("/events?category=")
    assert resp.status_code == 200
    assert len(resp.json()) == 2


# --- Combined q + category ---


def test_q_and_category_combined(client):
    resp = client.get("/events?q=Foo&category=festival")
    assert resp.status_code == 200
    data = resp.json()
    assert len(data) == 1
    assert data[0]["title"] == "Foo Festival"


def test_q_and_category_no_overlap_returns_empty(client):
    # q=Sumida matches hanabi, but category=festival doesn't match hanabi (attributes={})
    resp = client.get("/events?q=Sumida&category=festival")
    assert resp.status_code == 200
    assert resp.json() == []
