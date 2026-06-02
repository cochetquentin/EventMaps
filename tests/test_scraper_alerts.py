"""Tests for the empty-scrape CRITICAL alert (Phase 2.6)."""
import pytest
from unittest.mock import patch

from scrapers.tokyo_cheapo import TokyoCheapo
from scrapers.hanabi_walker import HanabiWalker


def test_tokyo_cheapo_critical_on_zero_events(caplog):
    """TokyoCheapo.scrape() must log CRITICAL when 0 events are returned."""
    with patch.object(TokyoCheapo, "scrape_all", return_value=[]):
        with caplog.at_level("CRITICAL", logger="scrapers.tokyo_cheapo"):
            result = TokyoCheapo().scrape()
    assert result == []
    assert any("0 events" in r.message for r in caplog.records if r.levelname == "CRITICAL")


def test_hanabi_walker_critical_on_zero_events(caplog):
    """HanabiWalker.scrape() must log CRITICAL when 0 events are returned."""
    with patch.object(HanabiWalker, "scrape_all", return_value=[]):
        with caplog.at_level("CRITICAL", logger="scrapers.hanabi_walker"):
            result = HanabiWalker().scrape()
    assert result == []
    assert any("0 events" in r.message for r in caplog.records if r.levelname == "CRITICAL")


def test_tokyo_cheapo_no_alert_when_events_returned():
    """No CRITICAL log when events are actually returned."""
    from datetime import datetime, timezone, date
    from models.event import Event
    from db.store import _make_id

    dummy = Event(
        id=_make_id(["https://example.com", ""]),
        source="tc",
        title="Test",
        url="https://example.com",
        start_date=date(2026, 6, 1),
        attributes={},
        created_at=datetime.now(timezone.utc),
    )
    with patch.object(TokyoCheapo, "scrape_all", return_value=[{
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
    }]):
        import logging
        import io
        stream = io.StringIO()
        handler = logging.StreamHandler(stream)
        handler.setLevel(logging.CRITICAL)
        logging.getLogger("scrapers.tokyo_cheapo").addHandler(handler)
        try:
            result = TokyoCheapo().scrape()
            assert len(result) == 1
            assert "CRITICAL" not in stream.getvalue()
        finally:
            logging.getLogger("scrapers.tokyo_cheapo").removeHandler(handler)
