"""Tests for the empty-scrape CRITICAL alert (Phase 2.6)."""
import pytest
from unittest.mock import patch

from scrapers.tokyo_cheapo import TokyoCheapo
from scrapers.hanabi_walker import HanabiWalker

_EMPTY_COUNTS = {"links_seen": 0, "events_ok": 0, "errors": []}


def test_tokyo_cheapo_critical_on_zero_events(caplog):
    """TokyoCheapo.scrape() must log CRITICAL when 0 events are returned."""
    with patch.object(TokyoCheapo, "scrape_all", return_value=([], _EMPTY_COUNTS)):
        with caplog.at_level("CRITICAL", logger="scrapers.tokyo_cheapo"):
            events, report = TokyoCheapo().scrape()
    assert events == []
    assert any("0 events" in r.message for r in caplog.records if r.levelname == "CRITICAL")


def test_hanabi_walker_critical_on_zero_events(caplog):
    """HanabiWalker.scrape() must log CRITICAL when 0 events are returned."""
    with patch.object(HanabiWalker, "scrape_all", return_value=([], _EMPTY_COUNTS)):
        with caplog.at_level("CRITICAL", logger="scrapers.hanabi_walker"):
            events, report = HanabiWalker().scrape()
    assert events == []
    assert any("0 events" in r.message for r in caplog.records if r.levelname == "CRITICAL")


def test_tokyo_cheapo_no_alert_when_events_returned():
    """No CRITICAL log when events are actually returned."""
    import logging
    import io
    from datetime import datetime, timezone

    raw_event = {
        "url": "https://example.com",
        "title": "Test",
        "start_date": "2026-06-01",
        "end_date": None,
        "start_time": None,
        "end_time": None,
        "price": None,
        "categories": [],
        "tags": [],
        "official_link": None,
        "locations": [{"name": "", "lat": None, "lng": None}],
    }
    counts = {"links_seen": 1, "events_ok": 1, "errors": []}
    with patch.object(TokyoCheapo, "scrape_all", return_value=([raw_event], counts)):
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.CRITICAL)
        logging.getLogger("scrapers.tokyo_cheapo").addHandler(handler)
        try:
            events, report = TokyoCheapo().scrape()
            assert len(events) == 1
            assert "CRITICAL" not in stream.getvalue()
        finally:
            logging.getLogger("scrapers.tokyo_cheapo").removeHandler(handler)
