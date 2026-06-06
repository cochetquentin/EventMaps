"""Tests for ARCH-007 — structured logging in _do_scrape()."""

from unittest.mock import patch

from scrapers.base import ScrapeReport
from scrapers.hanabi_walker import HanabiWalker
from scrapers.timeout_tokyo import TimeoutTokyo
from scrapers.tokyo_cheapo import TokyoCheapo


def _make_report(source, links=5, ok=5, errors=0):
    return ScrapeReport(
        source=source,
        links_seen=links,
        events_ok=ok,
        errors=[{"url": f"u{i}", "reason": "fail"} for i in range(errors)],
    )


def _start_job(db_path, source):
    from db.store import EventStore

    with EventStore(db_path) as store:
        return store.start_job(source)


def test_scrape_done_log_contains_structured_fields(tmp_path, monkeypatch, caplog):
    """Final log line includes source=, job_id=, events=, links=, errors=, duration=."""
    import api.routes.scrape as m
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    report = _make_report("tc")

    job_id = _start_job(db_path, "tc")
    with patch.object(TokyoCheapo, "scrape", return_value=([], report)):
        with caplog.at_level("INFO", logger="api.routes.scrape"):
            m._do_scrape(job_id, "tc", "ar0300")

    done = [r for r in caplog.records if "scrape_done" in r.message]
    assert done, "Expected a scrape_done log line"
    msg = done[0].message
    assert "source=tc" in msg
    assert "job_id=" in msg
    assert "duration=" in msg


def test_per_scraper_timing_logged(tmp_path, monkeypatch, caplog):
    """A per-scraper INFO line with duration= is emitted right after .scrape()."""
    import api.routes.scrape as m
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    report = _make_report("tc")

    job_id = _start_job(db_path, "tc")
    with patch.object(TokyoCheapo, "scrape", return_value=([], report)):
        with caplog.at_level("INFO", logger="api.routes.scrape"):
            m._do_scrape(job_id, "tc", "ar0300")

    scraper_lines = [
        r for r in caplog.records if "scraper" in r.message and "source=tc" in r.message
    ]
    assert scraper_lines, "Expected a per-scraper timing log line"
    assert "duration=" in scraper_lines[0].message


def test_job_id_consistent_across_log_lines(tmp_path, monkeypatch, caplog):
    """All log lines for a single job share the same job_id= value."""
    import api.routes.scrape as m
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    tc_report = _make_report("tc")
    hw_report = _make_report("hanabi")
    tot_report = _make_report("tot")

    job_id = _start_job(db_path, "all")
    with (
        patch.object(TokyoCheapo, "scrape", return_value=([], tc_report)),
        patch.object(HanabiWalker, "scrape", return_value=([], hw_report)),
        patch.object(TimeoutTokyo, "scrape", return_value=([], tot_report)),
    ):
        with caplog.at_level("INFO", logger="api.routes.scrape"):
            m._do_scrape(job_id, "all", "ar0300")

    job_ids = set()
    for r in caplog.records:
        for part in r.message.split():
            if part.startswith("job_id="):
                job_ids.add(part)

    assert len(job_ids) == 1, f"Expected single job_id across all log lines, got {job_ids}"


def test_scrape_fail_log_contains_job_id(tmp_path, monkeypatch, caplog):
    """ERROR log on threshold breach includes job_id=."""
    import api.routes.scrape as m
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    monkeypatch.setattr(config.settings, "scrape_error_threshold", 0.5)
    bad_report = _make_report("tc", links=10, ok=1, errors=9)

    job_id = _start_job(db_path, "tc")
    with patch.object(TokyoCheapo, "scrape", return_value=([], bad_report)):
        with caplog.at_level("ERROR", logger="api.routes.scrape"):
            m._do_scrape(job_id, "tc", "ar0300")

    error_lines = [r for r in caplog.records if r.levelname == "ERROR"]
    assert error_lines, "Expected an ERROR log line on threshold breach"
    assert "job_id=" in error_lines[0].message


def test_scrape_done_duration_is_numeric(tmp_path, monkeypatch, caplog):
    """The duration= value in the final log line is a non-negative float."""
    import api.routes.scrape as m
    import config

    db_path = str(tmp_path / "events.db")
    monkeypatch.setattr(config.settings, "db_path", db_path)
    report = _make_report("tc")

    job_id = _start_job(db_path, "tc")
    with patch.object(TokyoCheapo, "scrape", return_value=([], report)):
        with caplog.at_level("INFO", logger="api.routes.scrape"):
            m._do_scrape(job_id, "tc", "ar0300")

    done = next(r for r in caplog.records if "scrape_done" in r.message)
    duration_part = next(p for p in done.message.split() if p.startswith("duration="))
    value_str = duration_part.split("=", 1)[1].rstrip("s")
    assert float(value_str) >= 0.0
