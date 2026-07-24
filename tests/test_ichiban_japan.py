"""Tests for the Ichiban Japan scraper (source='ij')."""

from __future__ import annotations

import logging
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from bs4 import BeautifulSoup

from models.attributes import IchibanJapanAttributes
from scrapers.ichiban_japan import (
    IchibanJapan,
    _article_is_current_or_future,
    _clean,
    _coords_from_url_string,
    _dates_from_lines,
    _parse_fr_dates,
    _slugify,
    _strip_credit,
    _strip_parenthetical,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures" / "ij" / "synthetic"


def load(name: str) -> BeautifulSoup:
    return BeautifulSoup((FIXTURES_DIR / name).read_text(encoding="utf-8"), "html.parser")


@pytest.fixture
def ij():
    scraper = IchibanJapan()
    scraper._throttle_s = 0  # no politeness sleep in tests
    # Fixed reference date before the fixtures' May 2026 events so the default
    # upcoming-only filter keeps them all; individual tests override as needed.
    scraper._today = date(2026, 1, 1)
    return scraper


# ── Pure helpers ──────────────────────────────────────────────────────────────


@pytest.mark.parametrize(
    "text,expected",
    [
        ("1er mai 2026", (date(2026, 5, 1), None)),
        ("5 mai 2026", (date(2026, 5, 5), None)),
        ("5 février 2026", (date(2026, 2, 5), None)),  # accent stripped for matching
        ("1er août 2026", (date(2026, 8, 1), None)),
        ("2-3 mai 2026", (date(2026, 5, 2), date(2026, 5, 3))),
        ("2 et 3 mai 2026", (date(2026, 5, 2), date(2026, 5, 3))),
        ("Du 3 au 5 mai 2026", (date(2026, 5, 3), date(2026, 5, 5))),
        ("Du 3 mai au 5 mai 2026", (date(2026, 5, 3), date(2026, 5, 5))),
        ("Du 25 mai au 14 juin 2026", (date(2026, 5, 25), date(2026, 6, 14))),
        ("jusqu'au 6 mai 2026", (None, date(2026, 5, 6))),
        ("Du 29 avril au 6 mai 2026", (date(2026, 4, 29), date(2026, 5, 6))),
        # cross-year with single trailing year → start rolls back
        ("Du 30 décembre au 2 janvier 2026", (date(2025, 12, 30), date(2026, 1, 2))),
        # cross-year with both years explicit
        ("Du 30 décembre 2025 au 2 janvier 2026", (date(2025, 12, 30), date(2026, 1, 2))),
        ("pas de date ici", (None, None)),
        ("", (None, None)),
    ],
)
def test_parse_fr_dates(text, expected):
    assert _parse_fr_dates(text, 2026) == expected


def test_parse_fr_dates_uses_fallback_year_when_absent():
    assert _parse_fr_dates("5 mai", 2030) == (date(2030, 5, 5), None)


def test_parse_fr_dates_ignores_invalid_day():
    assert _parse_fr_dates("32 mai 2026", 2026) == (None, None)


@pytest.mark.parametrize(
    "url,expected",
    [
        # precise place (!3d!4d) preferred over map centre (@)
        (
            "https://www.google.com/maps/place/X/@35.1,139.2,17z/data=!8m2!3d35.9!4d139.8",
            (35.9, 139.8),
        ),
        # only the @ centre available
        ("https://www.google.com/maps/place/X/@35.1,139.2,17z", (35.1, 139.2)),
        # google maps place link with no coordinates in the URL
        ("https://www.google.com/maps/place//data=!4m2!3m1!1s0x60", None),
        # not a maps URL at all
        ("https://example.com/foo", None),
    ],
)
def test_coords_from_url_string(url, expected):
    assert _coords_from_url_string(url) == expected


def test_slugify():
    assert _slugify("Fukagawa Ryujin Reitaisai") == "fukagawa-ryujin-reitaisai"
    assert _slugify("Craft Gyoza Fes 2026 !") == "craft-gyoza-fes-2026"
    assert _slugify("Fête de l'Été") == "fete-de-l-ete"


def test_strip_credit():
    assert _strip_credit("Le temple en fête. © Ichiban Japan") == "Le temple en fête."
    assert _strip_credit("Sans crédit") == "Sans crédit"


def test_strip_parenthetical():
    assert _strip_parenthetical("Sanja Matsuri (15-17 mai 2026)") == "Sanja Matsuri"
    assert _strip_parenthetical("Sans parenthèse") == "Sans parenthèse"


def test_clean_collapses_and_handles_nbsp():
    assert _clean("  a\xa0 b  ") == "a b"
    assert _clean(None) == ""


def test_dates_from_lines_picks_line_between_name_and_lieu():
    lines = [
        "Haru no Taisai",
        "Du 3 au 5 mai 2026",
        "Lieu : sanctuaire (Harajuku)",
        "Site officiel",
    ]
    assert _dates_from_lines(lines, "Haru no Taisai") == "Du 3 au 5 mai 2026"


# ── Short-link resolution (mocked network) ────────────────────────────────────


def test_coords_from_maps_url_full_url_no_network(ij):
    ij.session.get = MagicMock()  # would raise if called
    coords = ij._coords_from_maps_url("https://www.google.com/maps/place/X/data=!8m2!3d1.1!4d2.2")
    assert coords == (1.1, 2.2)
    ij.session.get.assert_not_called()


def test_coords_from_maps_url_none_and_non_maps(ij):
    assert ij._coords_from_maps_url(None) == (None, None)
    assert ij._coords_from_maps_url("https://site.example/lieu") == (None, None)


def test_resolve_short_link_parses_coords_and_caches(ij):
    resp = MagicMock()
    resp.url = "https://www.google.com/maps/place/Meiji/@1.0,2.0,17z/data=!8m2!3d1.5!4d2.5"
    ij.session.get = MagicMock(return_value=resp)

    assert ij._coords_from_maps_url("https://maps.app.goo.gl/abc") == (1.5, 2.5)
    # second lookup is served from cache — no extra network call
    assert ij._coords_from_maps_url("https://maps.app.goo.gl/abc") == (1.5, 2.5)
    assert ij.session.get.call_count == 1


def test_resolve_short_link_network_failure_returns_none(ij):
    ij.session.get = MagicMock(side_effect=requests.RequestException("boom"))
    assert ij._coords_from_maps_url("https://maps.app.goo.gl/xyz") == (None, None)


# ── Level 1: article discovery ────────────────────────────────────────────────


def test_get_article_links_from_fixture(ij, monkeypatch):
    listing = load("listing.html")
    empty = BeautifulSoup("<html><body></body></html>", "html.parser")
    calls = {"n": 0}

    def fake_get_page(url):
        calls["n"] += 1
        return listing if calls["n"] == 1 else empty

    monkeypatch.setattr(ij, "get_page", fake_get_page)
    links = ij.get_article_links(max_pages=3)

    assert links == [
        "https://ichiban-japan.com/festivals-tokyo-mai-2026/",
        "https://ichiban-japan.com/expositions-tokyo-mai-2026/",
        "https://ichiban-japan.com/marches-aux-puces-tokyo/",  # relative href joined
    ]


# ── Level 2: article → events ─────────────────────────────────────────────────


@pytest.fixture
def article_events(ij, monkeypatch):
    article = load("article_full.html")
    monkeypatch.setattr(ij, "get_page", lambda url: article)
    # Resolve the maps.app.goo.gl short link (event B) to a URL carrying coords.
    monkeypatch.setattr(
        ij,
        "_resolve_short",
        lambda href: (
            "https://www.google.com/maps/place/Meiji/@35.67,139.69,17z/data=!8m2!3d35.6763976!4d139.6993259"
        ),
    )
    return ij.scrape_article("https://ichiban-japan.com/festivals-tokyo-mai-2026/")


def test_scrape_article_full_fixture_skips_non_event_heading(article_events):
    # 5 events (3 standalone + 2 grouped under one heading); the "Nos coups de cœur"
    # heading (no "Lieu :") is not an event.
    assert len(article_events) == 5
    assert [e["name"] for e in article_events] == [
        "Fukagawa Ryujin Reitaisai",
        "Haru no Taisai",
        "Craft Gyoza Fes 2026",
        "Senso-ji Setsubun-e",
        "Zojo-ji Setsubun-e",
    ]


def test_scrape_article_grouped_section_yields_one_event_per_lieu(article_events):
    # Regression: a single section heading ("Les festivals pour Setsubun") covers two
    # events — each "Lieu :" paragraph must become its own event, not be collapsed.
    g1, g2 = article_events[3], article_events[4]
    assert g1["name"] == "Senso-ji Setsubun-e"
    assert g1["start_date"] == date(2026, 5, 3)
    assert g1["venue_name"] == "temple Senso-ji"
    assert g1["neighbourhood"] == "Asakusa"
    assert (g1["latitude"], g1["longitude"]) == (35.7147651, 139.7966553)
    assert g2["name"] == "Zojo-ji Setsubun-e"
    assert g2["start_date"] == date(2026, 5, 3)
    assert g2["venue_name"] == "temple Zojo-ji"
    assert g2["neighbourhood"] == "Shiba"
    assert g2["latitude"] is None and g2["longitude"] is None  # maps URL without coords


def test_scrape_article_event_a_nominal(article_events):
    a = article_events[0]
    assert a["start_date"] == date(2026, 5, 1)
    assert a["end_date"] is None
    assert a["venue_name"] == "temple Fukagawa Fudo-do"
    assert a["neighbourhood"] == "Monzen-Nakacho"
    assert a["official_link"] == "https://www.fukagawafudou.gr.jp/event/index.html"
    # precise !3d!4d coords, not the @ map centre
    assert (a["latitude"], a["longitude"]) == (35.6728891, 139.7983222)
    assert "Ryujin" in a["description"]
    assert a["image_url"].endswith("temple.jpg")
    assert a["image_caption"] == "Le temple Fukagawa Fudo-do en fête."  # credit stripped
    assert a["url"].endswith("#fukagawa-ryujin-reitaisai")
    assert a["zone"] == "Tokyo"
    assert a["article_title"] == "Les festivals à Tokyo en mai 2026"


def test_scrape_article_event_b_br_in_strong_and_short_link(article_events):
    b = article_events[1]
    assert b["name"] == "Haru no Taisai"  # <br> inside <strong> handled
    assert b["start_date"] == date(2026, 5, 3)
    assert b["end_date"] == date(2026, 5, 5)
    assert b["venue_name"] == "sanctuaire Meiji-jingu"
    assert b["neighbourhood"] == "Harajuku"
    assert b["official_link"] == "https://www.meijijingu.or.jp/spring_taisai/"  # "Site officiel"
    assert (b["latitude"], b["longitude"]) == (35.6763976, 139.6993259)  # from resolved short link
    assert b["image_url"] is None


def test_scrape_article_event_c_lieux_plural_no_coords(article_events):
    c = article_events[2]
    assert c["start_date"] is None  # "jusqu'au 6 mai 2026" → end only
    assert c["end_date"] == date(2026, 5, 6)
    assert c["venue_name"] == "place A"  # first venue link of "Lieux :"
    assert c["neighbourhood"] is None
    assert c["official_link"] == "https://craftgyoza.example/"  # last link
    assert c["latitude"] is None and c["longitude"] is None


def test_scrape_article_without_entry_content_raises(ij, monkeypatch):
    soup = BeautifulSoup("<html><body><p>rien</p></body></html>", "html.parser")
    monkeypatch.setattr(ij, "get_page", lambda url: soup)
    with pytest.raises(ValueError, match="entry-content"):
        ij.scrape_article("https://ichiban-japan.com/x/")


# ── scrape(): canonical Event models ──────────────────────────────────────────


def test_scrape_builds_canonical_events(ij, monkeypatch):
    article = load("article_full.html")
    url = "https://ichiban-japan.com/festivals-tokyo-mai-2026/"
    monkeypatch.setattr(ij, "get_article_links", lambda max_pages=None: [url])
    monkeypatch.setattr(ij, "get_page", lambda u: article)
    monkeypatch.setattr(ij, "_resolve_short", lambda href: None)

    events, report = ij.scrape()

    assert report.source == "ij"
    assert report.links_seen == 1  # one article
    assert report.events_ok == 5
    assert len(events) == 5
    assert all(e.source == "ij" for e in events)
    assert len({e.id for e in events}) == 5  # distinct ids via #anchor urls
    assert all(isinstance(e.attributes, IchibanJapanAttributes) for e in events)

    a, b, c = events[0], events[1], events[2]
    assert a.start_date == date(2026, 5, 1) and a.end_date is None  # single day
    assert b.start_date == date(2026, 5, 3) and b.end_date == date(2026, 5, 5)  # range
    # "jusqu'au": start anchored to end, end collapsed to None (single day)
    assert c.start_date == date(2026, 5, 6) and c.end_date is None
    assert a.venue == "temple Fukagawa Fudo-do"  # top-level venue (used by dedup + popups)
    assert a.attributes.dates_text == "1er mai 2026"


def test_scrape_id_is_stable(ij, monkeypatch):
    article = load("article_full.html")
    url = "https://ichiban-japan.com/festivals-tokyo-mai-2026/"
    monkeypatch.setattr(ij, "get_article_links", lambda max_pages=None: [url])
    monkeypatch.setattr(ij, "get_page", lambda u: article)
    monkeypatch.setattr(ij, "_resolve_short", lambda href: None)

    ids1 = [e.id for e in ij.scrape()[0]]
    ids2 = [e.id for e in ij.scrape()[0]]
    assert ids1 == ids2


def test_scrape_zero_events_logs_critical(ij, monkeypatch, caplog):
    monkeypatch.setattr(ij, "get_article_links", lambda max_pages=None: [])
    with caplog.at_level(logging.CRITICAL):
        events, report = ij.scrape()
    assert events == []
    assert report.links_seen == 0
    assert any("0 events" in r.message for r in caplog.records)


_EMPTY_ARTICLE_HTML = (
    "<html><body><div class='entry-content'><p>rien d'événementiel</p></div></body></html>"
)


def test_scrape_all_empty_non_dated_article_is_not_an_error(ij, monkeypatch):
    # A non-dated page (special/guide) with no "Lieu :" is benign, not an error.
    empty = BeautifulSoup(_EMPTY_ARTICLE_HTML, "html.parser")
    url = "https://ichiban-japan.com/triennale-setouchi-2025/"
    monkeypatch.setattr(ij, "get_article_links", lambda max_pages=None: [url])
    monkeypatch.setattr(ij, "get_page", lambda u: empty)

    events, report = ij.scrape()
    assert events == []
    assert report.errors == []


def test_scrape_all_empty_dated_month_article_is_an_error(ij, monkeypatch):
    # A dated monthly article with zero events signals a parser failure → error.
    empty = BeautifulSoup(_EMPTY_ARTICLE_HTML, "html.parser")
    url = "https://ichiban-japan.com/festivals-tokyo-janvier-2026/"
    monkeypatch.setattr(ij, "get_article_links", lambda max_pages=None: [url])
    monkeypatch.setattr(ij, "get_page", lambda u: empty)

    events, report = ij.scrape()
    assert events == []
    assert len(report.errors) == 1
    assert report.errors[0]["reason"] == "no events parsed"


# ── Filtres « à venir » : articles de mois passés + événements passés ──────────


def test_article_is_current_or_future():
    today = date(2026, 7, 1)
    base = "https://ichiban-japan.com/"
    # mois passés → False
    assert _article_is_current_or_future(f"{base}festivals-tokyo-mars-2026/", today) is False
    assert _article_is_current_or_future(f"{base}expositions-tokyo-decembre-2025/", today) is False
    assert _article_is_current_or_future(f"{base}festivals-tokyo-juin-2026/", today) is False
    # mois courant / futur → True
    assert _article_is_current_or_future(f"{base}festivals-tokyo-juillet-2026/", today) is True
    assert _article_is_current_or_future(f"{base}expositions-tokyo-aout-2026/", today) is True
    assert _article_is_current_or_future(f"{base}festivals-tokyo-janvier-2027/", today) is True
    # pages spéciales / evergreen (pas de mois dans le slug) → toujours True
    assert _article_is_current_or_future(f"{base}marches-aux-puces-tokyo/", today) is True
    assert _article_is_current_or_future(f"{base}festivals-ete-tohoku/", today) is True
    assert _article_is_current_or_future(f"{base}yuki-matsuri/", today) is True


def test_scrape_skips_past_month_articles(ij, monkeypatch):
    ij._today = date(2026, 7, 1)
    article = load("article_full.html")
    requested: list[str] = []

    def fake_get_page(url):
        requested.append(url)
        return article

    monkeypatch.setattr(ij, "get_page", fake_get_page)
    monkeypatch.setattr(ij, "_resolve_short", lambda href: None)
    monkeypatch.setattr(
        ij,
        "get_article_links",
        lambda max_pages=None: [
            "https://ichiban-japan.com/festivals-tokyo-mars-2026/",  # passé → ignoré
            "https://ichiban-japan.com/festivals-tokyo-juillet-2026/",  # courant → récupéré
            "https://ichiban-japan.com/marches-aux-puces-tokyo/",  # spécial → récupéré
        ],
    )
    events, report = ij.scrape()

    assert "https://ichiban-japan.com/festivals-tokyo-mars-2026/" not in requested
    assert "https://ichiban-japan.com/festivals-tokyo-juillet-2026/" in requested
    assert "https://ichiban-japan.com/marches-aux-puces-tokyo/" in requested
    assert report.links_seen == 2  # seuls les 2 articles non-passés sont comptés


def test_scrape_filters_past_events(ij, monkeypatch):
    ij._today = date(2026, 5, 4)  # au milieu des événements de la fixture
    article = load("article_full.html")
    monkeypatch.setattr(ij, "get_page", lambda u: article)
    monkeypatch.setattr(ij, "_resolve_short", lambda href: None)
    monkeypatch.setattr(
        ij,
        "get_article_links",
        lambda max_pages=None: ["https://ichiban-japan.com/festivals-tokyo-mai-2026/"],
    )

    events, report = ij.scrape()
    titles = {e.title for e in events}
    # Gardés : Haru no Taisai (3-5 mai, en cours) et Craft Gyoza (jusqu'au 6 mai).
    assert titles == {"Haru no Taisai", "Craft Gyoza Fes 2026"}
    # Le rapport compte tous les événements parsés (santé du parseur), pas seulement les à venir.
    assert report.events_ok == 5


def test_scrape_upcoming_only_false_returns_all(ij, monkeypatch):
    ij._today = date(2026, 5, 4)
    article = load("article_full.html")
    monkeypatch.setattr(ij, "get_page", lambda u: article)
    monkeypatch.setattr(ij, "_resolve_short", lambda href: None)
    monkeypatch.setattr(
        ij,
        "get_article_links",
        lambda max_pages=None: ["https://ichiban-japan.com/festivals-tokyo-mai-2026/"],
    )
    events, _ = ij.scrape(upcoming_only=False)
    assert len(events) == 5  # aucun filtrage par date
