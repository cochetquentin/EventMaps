"""Tests API du paramètre ?collapse (regroupement des doublons)."""

from datetime import UTC, date, datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from api.app import app
from db.store import EventStore
from models.event import Event
from models.identity import make_event_id

_NOW = datetime(2026, 1, 1, tzinfo=UTC)
_FUT = date.today() + timedelta(days=90)  # toujours dans le futur (filtre upcoming)


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
        created_at=_NOW,
    )
    base.update(over)
    return Event(**base)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    import config

    db_path = str(tmp_path / "events.db")
    # Une paire de doublons (feu d'artifice sur 2 sources) + un événement distinct.
    a = mk("hanabi", "Sumida River Fireworks", "https://h/1", 35.7110, 139.8010, venue="Sumida")
    b = mk(
        "tc",
        "Sumida River Fireworks",
        "https://tc/1",
        35.7120,
        139.8012,
        attributes={"location_name": "Sumida"},
    )
    c = mk(
        "tc",
        "Yoyogi Flea Market",
        "https://tc/2",
        35.671,
        139.694,
        attributes={"location_name": "Yoyogi Park"},
    )
    with EventStore(db_path) as store:
        store.upsert_with_dedup([a, b, c])
    monkeypatch.setattr(config.settings, "db_path", db_path)
    return TestClient(app)


def test_default_returns_all_events(client):
    data = client.get("/events").json()
    assert len(data) == 3


def test_collapse_true_merges_duplicates(client):
    data = client.get("/events?collapse=true").json()
    assert len(data) == 2  # le cluster feu d'artifice + le marché


def test_collapse_false_returns_all(client):
    data = client.get("/events?collapse=false").json()
    assert len(data) == 3


def test_response_exposes_canonical_id(client):
    data = client.get("/events").json()
    fireworks = [e for e in data if e["title"] == "Sumida River Fireworks"]
    assert len(fireworks) == 2
    # Les deux membres partagent le même canonical_id.
    assert fireworks[0]["canonical_id"] == fireworks[1]["canonical_id"]
    # Et il pointe vers un des deux membres du cluster.
    assert fireworks[0]["canonical_id"] in {fireworks[0]["id"], fireworks[1]["id"]}


def test_collapsed_event_keeps_coordinates(client):
    # Le représentant conservé doit avoir des coordonnées (pin sur la carte).
    data = client.get("/events?collapse=true").json()
    fireworks = [e for e in data if e["title"] == "Sumida River Fireworks"]
    assert len(fireworks) == 1
    assert fireworks[0]["latitude"] is not None
