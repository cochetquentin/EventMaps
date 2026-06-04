"""Tests for POST /scrape authentication and GET /scrape/config."""

import pytest
from fastapi.testclient import TestClient
from unittest.mock import patch

from api.app import app


@pytest.fixture()
def db(tmp_path, monkeypatch):
    import config
    from db.store import EventStore

    db_path = str(tmp_path / "events.db")
    with EventStore(db_path):
        pass
    monkeypatch.setattr(config.settings, "db_path", db_path)
    return db_path


@pytest.fixture()
def client(db):
    return TestClient(app)


@pytest.fixture()
def client_with_token(db, monkeypatch):
    import config
    monkeypatch.setattr(config.settings, "scrape_token", "secret")
    return TestClient(app)


# ── GET /scrape/config ────────────────────────────────────────────────────────

def test_scrape_config_public_when_no_token(client):
    resp = client.get("/scrape/config")
    assert resp.status_code == 200
    assert resp.json() == {"public": True}


def test_scrape_config_not_public_when_token_set(client_with_token):
    resp = client_with_token.get("/scrape/config")
    assert resp.status_code == 200
    assert resp.json() == {"public": False}


# ── POST /scrape — mode sans token ────────────────────────────────────────────

def test_scrape_without_token_config_succeeds(client):
    with patch("api.routes.scrape._do_scrape"):
        resp = client.post("/scrape")
    assert resp.status_code == 200
    assert resp.json()["status"] in ("started", "already_running")


# ── POST /scrape — mode avec token requis ────────────────────────────────────

def test_scrape_without_header_returns_403(client_with_token):
    resp = client_with_token.post("/scrape")
    assert resp.status_code == 403


def test_scrape_with_wrong_token_returns_403(client_with_token):
    resp = client_with_token.post("/scrape", headers={"Authorization": "Bearer wrong"})
    assert resp.status_code == 403


def test_scrape_with_malformed_auth_returns_403(client_with_token):
    resp = client_with_token.post("/scrape", headers={"Authorization": "secret"})
    assert resp.status_code == 403


def test_scrape_with_correct_token_succeeds(client_with_token):
    with patch("api.routes.scrape._do_scrape"):
        resp = client_with_token.post("/scrape", headers={"Authorization": "Bearer secret"})
    assert resp.status_code == 200
    assert resp.json()["status"] in ("started", "already_running")


# ── GET /scrape/status — toujours public ────────────────────────────────────

def test_scrape_status_public_without_token(client_with_token):
    resp = client_with_token.get("/scrape/status")
    assert resp.status_code == 200
