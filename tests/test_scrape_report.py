"""Tests for ScrapeReport, partial error detection and threshold-based job failure."""

from datetime import UTC, date, datetime
from unittest.mock import patch

import pytest

from db.store import EventStore, _make_id
from models.event import Event
from scrapers.base import ScrapeReport
from scrapers.hanabi_walker import HanabiWalker
from scrapers.timeout_tokyo import TimeoutTokyo
from scrapers.tokyo_cheapo import TokyoCheapo

# ── ScrapeReport unit tests ──────────────────────────────────────────────────


def test_scrape_report_error_rate_zero_links():
    report = ScrapeReport(source="tc", links_seen=0)
    assert report.error_rate == 0.0


def test_scrape_report_error_rate_no_errors():
    report = ScrapeReport(source="tc", links_seen=10, events_ok=10)
    assert report.error_rate == 0.0


def test_scrape_report_error_rate_all_errors():
    errors = [{"url": f"url{i}", "reason": "fail"} for i in range(10)]
    report = ScrapeReport(source="tc", links_seen=10, events_ok=0, errors=errors)
    assert report.error_rate == 1.0


def test_scrape_report_error_rate_partial():
    errors = [{"url": "url1", "reason": "fail"}, {"url": "url2", "reason": "fail"}]
    report = ScrapeReport(source="tc", links_seen=10, events_ok=8, errors=errors)
    assert report.error_rate == pytest.approx(0.2)


def test_scrape_report_includes_skipped_in_rate():
    errors = [{"url": "url1", "reason": "fail"}]
    report = ScrapeReport(source="tc", links_seen=10, events_ok=7, events_skipped=2, errors=errors)
    # (2 skipped + 1 error) / 10 links = 0.3
    assert report.error_rate == pytest.approx(0.3)


# ── Scraper partial error collection ────────────────────────────────────────


def test_tokyo_cheapo_scrape_all_counts_errors():
    """scrape_all() must record failing URLs in the errors list."""
    tc = TokyoCheapo.__new__(TokyoCheapo)

    def fake_get_links(max_pages=10):
        return ["url_ok", "url_fail"]

    def fake_scrape_event(url):
        if url == "url_fail":
            raise ValueError("parse error")
        return {
            "url": url,
            "title": "Test",
            "start_date": "2026-06-01",
            "end_date": None,
            "start_time": None,
            "end_time": None,
            "price": None,
            "categories": [],
            "tags": [],
            "official_link": None,
            "locations": [],
        }

    tc.get_event_links = fake_get_links
    tc.scrape_event = fake_scrape_event

    raw_events, counts = tc.scrape_all()
    assert counts["links_seen"] == 2
    assert counts["events_ok"] == 1
    assert len(counts["errors"]) == 1
    assert counts["errors"][0]["url"] == "url_fail"
    assert "parse error" in counts["errors"][0]["reason"]


def test_hanabi_walker_scrape_all_counts_errors():
    """HanabiWalker.scrape_all() must record failing paths in the errors list."""
    hw = HanabiWalker.__new__(HanabiWalker)

    def fake_get_links(max_pages=20):
        return ["/detail/ok/", "/detail/fail/"]

    def fake_scrape_event(path):
        if path == "/detail/fail/":
            raise RuntimeError("connection error")
        return {
            "url": "https://hanabi.walkerplus.com/detail/ok/",
            "dates": ["2026/08/01"],
            "title": "Test Hanabi",
            "lat": 35.0,
            "lng": 139.0,
        }

    hw.get_event_links = fake_get_links
    hw.scrape_event = fake_scrape_event

    raw_events, counts = hw.scrape_all()
    assert counts["links_seen"] == 2
    assert len(counts["errors"]) == 1
    assert counts["errors"][0]["url"] == "/detail/fail/"


def test_tokyo_cheapo_scrape_returns_tuple():
    """scrape() must return (list[Event], ScrapeReport)."""
    raw_event = {
        "url": "https://tokyocheapo.com/events/test",
        "title": "Test",
        "start_date": "2026-06-01",
        "end_date": None,
        "start_time": None,
        "end_time": None,
        "price": None,
        "categories": [],
        "tags": [],
        "official_link": None,
        "locations": [{"name": "Park", "lat": 35.0, "lng": 139.0}],
    }
    counts = {"links_seen": 1, "events_ok": 1, "errors": []}

    with patch.object(TokyoCheapo, "scrape_all", return_value=([raw_event], counts)):
        events, report = TokyoCheapo().scrape()

    assert isinstance(events, list)
    assert isinstance(report, ScrapeReport)
    assert report.source == "tc"
    assert report.links_seen == 1
    assert report.events_ok == 1
    assert report.error_rate == 0.0


# ── _do_scrape error threshold ───────────────────────────────────────────────


def _make_event():
    return Event(
        id=_make_id(["https://example.com", ""]),
        source="tc",
        title="Test",
        url="https://example.com",
        start_date=date(2026, 6, 1),
        attributes={},
        created_at=datetime.now(UTC),
    )


def test_do_scrape_fails_job_on_high_error_rate(tmp_path, monkeypatch):
    """_do_scrape() must call fail_job when error_rate > threshold."""
    import api.routes.scrape as scrape_module
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)

    # 8 errors / 10 links = 80% error rate → above threshold
    bad_report = ScrapeReport(
        source="tc",
        links_seen=10,
        events_ok=2,
        errors=[{"url": f"url{i}", "reason": "fail"} for i in range(8)],
    )

    with patch.object(TokyoCheapo, "scrape", return_value=([_make_event()], bad_report)):
        scrape_module._do_scrape("tc", "ar0300")

    with EventStore(db_path) as store:
        job = store.get_last_job("tc")

    assert job is not None
    assert job["status"] == "failed"
    assert "error rate" in job["error"].lower()
    assert "exceeded threshold" in job["error"]


def test_do_scrape_finishes_job_on_low_error_rate(tmp_path, monkeypatch):
    """_do_scrape() must call finish_job when error_rate <= threshold."""
    import api.routes.scrape as scrape_module
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)

    # 1 error / 10 links = 10% → below threshold
    good_report = ScrapeReport(
        source="tc",
        links_seen=10,
        events_ok=9,
        errors=[{"url": "url_bad", "reason": "fail"}],
    )

    with patch.object(TokyoCheapo, "scrape", return_value=([_make_event()], good_report)):
        scrape_module._do_scrape("tc", "ar0300")

    with EventStore(db_path) as store:
        job = store.get_last_job("tc")

    assert job is not None
    assert job["status"] == "done"
    assert job["links_seen"] == 10
    assert job["events_ok"] == 9
    assert job["error_count"] == 1


def test_do_scrape_zero_links_does_not_fail(tmp_path, monkeypatch):
    """_do_scrape() must not fail the job when links_seen == 0 (source empty)."""
    import api.routes.scrape as scrape_module
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)

    empty_report = ScrapeReport(source="tc", links_seen=0, events_ok=0)

    with patch.object(TokyoCheapo, "scrape", return_value=([], empty_report)):
        scrape_module._do_scrape("tc", "ar0300")

    with EventStore(db_path) as store:
        job = store.get_last_job("tc")

    # No links → no error rate calculation → job should succeed (CRITICAL logged by scraper)
    assert job is not None
    assert job["status"] == "done"


def test_do_scrape_persists_metrics_on_failed_job(tmp_path, monkeypatch):
    """Metrics must be stored even when fail_job is called (threshold exceeded)."""
    import api.routes.scrape as scrape_module
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)

    bad_report = ScrapeReport(
        source="tc",
        links_seen=10,
        events_ok=2,
        errors=[{"url": f"url{i}", "reason": "fail"} for i in range(8)],
    )

    with patch.object(TokyoCheapo, "scrape", return_value=([_make_event()], bad_report)):
        scrape_module._do_scrape("tc", "ar0300")

    with EventStore(db_path) as store:
        job = store.get_last_job("tc")

    assert job["status"] == "failed"
    assert job["links_seen"] == 10
    assert job["events_ok"] == 2
    assert job["error_count"] == 8


def test_do_scrape_all_fails_if_one_source_broken(tmp_path, monkeypatch):
    """source=all must fail if one source exceeds threshold, even if the other is healthy."""
    import api.routes.scrape as scrape_module
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)

    # TC: 100 links, 0 errors → 0% error rate (healthy)
    tc_report = ScrapeReport(source="tc", links_seen=100, events_ok=100)
    # Hanabi: 10 links, 10 errors → 100% error rate (broken)
    hanabi_report = ScrapeReport(
        source="hanabi",
        links_seen=10,
        events_ok=0,
        errors=[{"url": f"/detail/{i}/", "reason": "fail"} for i in range(10)],
    )

    tot_report = ScrapeReport(source="tot", links_seen=0, events_ok=0)
    with (
        patch.object(TokyoCheapo, "scrape", return_value=([_make_event()], tc_report)),
        patch.object(HanabiWalker, "scrape", return_value=([], hanabi_report)),
        patch.object(TimeoutTokyo, "scrape", return_value=([], tot_report)),
    ):
        scrape_module._do_scrape("all", "ar0300")

    with EventStore(db_path) as store:
        job = store.get_last_job("all")

    assert job["status"] == "failed"
    assert "hanabi" in job["error"]


# ── GET /scrape/status returns metric columns ────────────────────────────────


def test_scrape_status_exposes_metric_columns(tmp_path, monkeypatch):
    """GET /scrape/status must include links_seen, events_ok, events_skipped, error_count."""
    from fastapi.testclient import TestClient

    import api.routes.scrape as scrape_module
    import config
    from api.app import app

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)

    good_report = ScrapeReport(
        source="tc",
        links_seen=5,
        events_ok=5,
    )

    with patch.object(TokyoCheapo, "scrape", return_value=([_make_event()], good_report)):
        scrape_module._do_scrape("tc", "ar0300")

    client = TestClient(app)
    resp = client.get("/scrape/status?source=tc")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "done"
    assert data["links_seen"] == 5
    assert data["events_ok"] == 5
    assert data["events_skipped"] == 0
    assert data["error_count"] == 0
