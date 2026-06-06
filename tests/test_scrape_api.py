"""Tests for POST /scrape authentication and GET /scrape/config."""

from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient

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


def _reset_limiter():
    from api.limiter import limiter

    limiter._limiter.storage.reset()


@pytest.fixture()
def client(db):
    _reset_limiter()
    return TestClient(app)


@pytest.fixture()
def client_with_token(db, monkeypatch):
    import config

    monkeypatch.setattr(config.settings, "scrape_token", "secret")
    _reset_limiter()
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
    body = resp.json()
    assert body["status"] in ("started", "already_running")
    if body["status"] == "started":
        assert isinstance(body.get("job_id"), int)
        assert body["job_id"] > 0


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


# ── POST /scrape retourne job_id ──────────────────────────────────────────────


def test_trigger_scrape_returns_job_id(client):
    with patch("api.routes.scrape._do_scrape"):
        resp = client.post("/scrape")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] == "started"
    assert isinstance(body["job_id"], int)
    assert body["job_id"] > 0


# ── GET /scrape/status?job_id= ────────────────────────────────────────────────


def test_scrape_status_by_job_id(client):
    with patch("api.routes.scrape._do_scrape"):
        post_resp = client.post("/scrape")
    job_id = post_resp.json()["job_id"]
    resp = client.get(f"/scrape/status?job_id={job_id}")
    assert resp.status_code == 200
    body = resp.json()
    assert body["id"] == job_id
    assert body["status"] == "running"


def test_scrape_status_job_id_not_found(client):
    resp = client.get("/scrape/status?job_id=99999")
    assert resp.status_code == 404
    assert resp.json()["detail"] == "Job not found"


def test_scrape_status_no_job_id_backwards_compat(client):
    with patch("api.routes.scrape._do_scrape"):
        client.post("/scrape")
    resp = client.get("/scrape/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "running"


def test_scrape_status_job_id_overrides_source(client):
    with patch("api.routes.scrape._do_scrape"):
        post_resp = client.post("/scrape?source=tc")
    job_id = post_resp.json()["job_id"]
    # Passer une source différente ne doit pas affecter le résultat quand job_id est fourni
    resp = client.get(f"/scrape/status?job_id={job_id}&source=hanabi")
    assert resp.status_code == 200
    assert resp.json()["id"] == job_id
