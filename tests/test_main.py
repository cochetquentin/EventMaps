"""Tests for main.py CLI — commandes tc, hanabi, all (output db et csv)."""
import argparse
import sys
from unittest.mock import patch, call

import pytest

from db.store import EventStore
from scrapers.base import ScrapeReport
from scrapers.tokyo_cheapo import TokyoCheapo
from scrapers.hanabi_walker import HanabiWalker
import main
from main import cmd_tc, cmd_hanabi, cmd_all, _write_events_csv

from tests.test_store import make_tc, make_hanabi


_TC_REPORT = ScrapeReport(source="tc", links_seen=1, events_ok=1)
_HW_REPORT = ScrapeReport(source="hanabi", links_seen=1, events_ok=1)


# ── helpers ───────────────────────────────────────────────────────────────────

def _db_args(tmp_path, source="tc", region="ar0300"):
    ns = argparse.Namespace(output="db", db=str(tmp_path / "events.db"), source=source)
    if source in ("hanabi", "all"):
        ns.region = region
    return ns


def _csv_args(tmp_path, source="tc", region="ar0300"):
    ns = argparse.Namespace(output="csv", db=str(tmp_path / "events.db"), source=source)
    if source in ("hanabi", "all"):
        ns.region = region
    return ns


def _no_reconfigure(monkeypatch):
    """Neutralise sys.stdout.reconfigure pour que capsys fonctionne."""
    monkeypatch.setattr(sys.stdout, "reconfigure", lambda **kw: None, raising=False)


# ── cmd_tc ───────────────────────────────────────────────────────────────────

def test_cmd_tc_db(tmp_path):
    event = make_tc()
    with patch.object(TokyoCheapo, "scrape", return_value=([event], _TC_REPORT)):
        cmd_tc(_db_args(tmp_path))

    with EventStore(str(tmp_path / "events.db")) as store:
        rows = store.get_events(upcoming=False)
    assert len(rows) == 1
    assert rows[0].id == event.id


def test_cmd_tc_csv(tmp_path, monkeypatch, capsys):
    _no_reconfigure(monkeypatch)
    event = make_tc()
    with patch.object(TokyoCheapo, "scrape", return_value=([event], _TC_REPORT)):
        cmd_tc(_csv_args(tmp_path))

    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines[0].startswith("id,source,title")
    assert len(lines) == 2  # header + 1 event
    assert "Foo Festival" in lines[1]


# ── cmd_hanabi ────────────────────────────────────────────────────────────────

def test_cmd_hanabi_db(tmp_path):
    event = make_hanabi()
    with patch.object(HanabiWalker, "scrape", return_value=([event], _HW_REPORT)):
        cmd_hanabi(_db_args(tmp_path, source="hanabi"))

    with EventStore(str(tmp_path / "events.db")) as store:
        rows = store.get_events(upcoming=False)
    assert len(rows) == 1
    assert rows[0].id == event.id


def test_cmd_hanabi_csv(tmp_path, monkeypatch, capsys):
    _no_reconfigure(monkeypatch)
    event = make_hanabi()
    with patch.object(HanabiWalker, "scrape", return_value=([event], _HW_REPORT)):
        cmd_hanabi(_csv_args(tmp_path, source="hanabi"))

    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines[0].startswith("id,source,title")
    assert len(lines) == 2
    assert "Sumida River Fireworks" in lines[1]


def test_cmd_hanabi_region_forwarded(tmp_path):
    """--region doit être transmis à HanabiWalker.__init__."""
    event = make_hanabi()
    with patch.object(HanabiWalker, "__init__", return_value=None) as mock_init, \
         patch.object(HanabiWalker, "scrape", return_value=([event], _HW_REPORT)):
        cmd_hanabi(_db_args(tmp_path, source="hanabi", region="ar9999"))

    mock_init.assert_called_once_with(region="ar9999")


# ── cmd_all ───────────────────────────────────────────────────────────────────

def test_cmd_all_db(tmp_path):
    tc_event = make_tc()
    hw_event = make_hanabi()
    with patch.object(TokyoCheapo, "scrape", return_value=([tc_event], _TC_REPORT)), \
         patch.object(HanabiWalker, "scrape", return_value=([hw_event], _HW_REPORT)):
        cmd_all(_db_args(tmp_path, source="all"))

    with EventStore(str(tmp_path / "events.db")) as store:
        rows = store.get_events(upcoming=False)
    assert len(rows) == 2
    ids = {r.id for r in rows}
    assert tc_event.id in ids
    assert hw_event.id in ids


def test_cmd_all_csv(tmp_path, monkeypatch, capsys):
    _no_reconfigure(monkeypatch)
    tc_event = make_tc()
    hw_event = make_hanabi()
    with patch.object(TokyoCheapo, "scrape", return_value=([tc_event], _TC_REPORT)), \
         patch.object(HanabiWalker, "scrape", return_value=([hw_event], _HW_REPORT)):
        cmd_all(_csv_args(tmp_path, source="all"))

    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip()]
    assert lines[0].startswith("id,source,title")
    assert len(lines) == 3  # header + 2 events


def test_cmd_all_region_forwarded(tmp_path):
    tc_event = make_tc()
    hw_event = make_hanabi()
    with patch.object(TokyoCheapo, "scrape", return_value=([tc_event], _TC_REPORT)), \
         patch.object(HanabiWalker, "__init__", return_value=None) as mock_init, \
         patch.object(HanabiWalker, "scrape", return_value=([hw_event], _HW_REPORT)):
        cmd_all(_db_args(tmp_path, source="all", region="ar9999"))

    mock_init.assert_called_once_with(region="ar9999")


# ── _write_events_csv ─────────────────────────────────────────────────────────

def test_csv_header_only(monkeypatch, capsys):
    """Liste vide → seulement le header (13 colonnes)."""
    _no_reconfigure(monkeypatch)
    _write_events_csv([])

    out = capsys.readouterr().out
    lines = [l for l in out.splitlines() if l.strip()]
    assert len(lines) == 1
    cols = lines[0].split(",")
    assert len(cols) == 13
    assert cols[0] == "id"
    assert cols[-1] == "created_at"


# ── main() dispatch ───────────────────────────────────────────────────────────

def test_main_dispatch_tc(tmp_path, monkeypatch):
    """main() avec argv=['tc'] doit appeler cmd_tc sans erreur."""
    monkeypatch.setattr(
        sys, "argv", ["scrape", "--output", "db", "--db", str(tmp_path / "e.db"), "tc"]
    )
    event = make_tc()
    with patch.object(TokyoCheapo, "scrape", return_value=([event], _TC_REPORT)):
        main.main()

    with EventStore(str(tmp_path / "e.db")) as store:
        rows = store.get_events(upcoming=False)
    assert len(rows) == 1
