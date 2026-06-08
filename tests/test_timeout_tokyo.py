"""Tests for the Time Out Tokyo scraper (source='tot')."""

from __future__ import annotations

import io
import logging
from pathlib import Path

import pytest
from bs4 import BeautifulSoup

from scrapers.timeout_tokyo import (
    TimeoutTokyo,
    _format_price,
    _is_event_href,
    _listing_paths,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tot():
    return TimeoutTokyo()


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# ── _is_event_href ────────────────────────────────────────────────────────────


def test_is_event_href_valid():
    assert _is_event_href("/tokyo/art/grand-van-gogh-exhibition") is True
    assert _is_event_href("/tokyo/things-to-do/hanabi-matsuri") is True
    assert _is_event_href("/tokyo/music/summer-sonic-2026") is True


def test_is_event_href_excludes_non_event_categories():
    assert _is_event_href("/tokyo/restaurants/some-ramen-place") is False
    assert _is_event_href("/tokyo/bars-and-clubs/some-bar") is False
    assert _is_event_href("/tokyo/hotels/some-hotel") is False
    assert _is_event_href("/tokyo/shopping/some-store") is False


def test_is_event_href_excludes_news():
    assert _is_event_href("/tokyo/news/3-spectacular-festivals-060326") is False


def test_is_event_href_excludes_things_to_do_listings():
    assert _is_event_href("/tokyo/things-to-do/things-to-do-this-week-in-tokyo") is False
    assert _is_event_href("/tokyo/things-to-do/things-to-do-in-tokyo-today") is False


def test_is_event_href_excludes_best_pages():
    assert _is_event_href("/tokyo/things-to-do/best-restaurants-in-tokyo") is False


def test_is_event_href_excludes_short_paths():
    assert _is_event_href("/tokyo/") is False
    assert _is_event_href("/tokyo/art/") is False  # Only 2 segments when stripped
    assert _is_event_href("/tokyo") is False


def test_is_event_href_excludes_non_tokyo():
    assert _is_event_href("/london/art/some-event") is False
    assert _is_event_href("https://www.timeout.com/tokyo/art/event") is False


# ── _format_price ─────────────────────────────────────────────────────────────


def test_format_price_free():
    assert _format_price(0.0) == "Free"
    assert _format_price(0, "JPY") == "Free"


def test_format_price_jpy():
    assert _format_price(2800.0, "JPY") == "¥2,800"
    assert _format_price(1000, "JPY") == "¥1,000"


def test_format_price_other_currency():
    assert _format_price(15.0, "USD") == "15.0 USD"


# ── _listing_paths ────────────────────────────────────────────────────────────


def test_listing_paths_returns_static_plus_monthly():
    paths = _listing_paths(max_pages=4)
    assert "/tokyo/things-to-do/things-to-do-this-week-in-tokyo" in paths
    assert "/tokyo/things-to-do/things-to-do-in-tokyo-this-weekend" in paths
    assert len(paths) == 4  # 2 static + 2 monthly


def test_listing_paths_zero_pages():
    paths = _listing_paths(max_pages=0)
    assert len(paths) == 0


def test_listing_paths_one_page():
    paths = _listing_paths(max_pages=1)
    assert len(paths) == 1
    assert "/tokyo/things-to-do/things-to-do-this-week-in-tokyo" in paths


# ── get_event_links ───────────────────────────────────────────────────────────


def test_get_event_links_extracts_and_deduplicates(tot, monkeypatch):
    html_bytes = (FIXTURES_DIR / "tot/real/listing.html").read_bytes()

    def fake_fetch(url, session, timeout):
        import requests

        r = requests.Response()
        r.status_code = 200
        r._content = html_bytes
        return r

    monkeypatch.setattr("scrapers.timeout_tokyo._fetch", fake_fetch)
    monkeypatch.setattr(
        "scrapers.timeout_tokyo._listing_paths",
        lambda n: ["/tokyo/things-to-do/things-to-do-this-week-in-tokyo"],
    )

    links = tot.get_event_links(max_pages=1)

    # Real listing page contains multiple event links (deduplicated)
    assert len(links) > 0
    assert all(link.startswith("https://www.timeout.com/tokyo/") for link in links)
    # News articles and navigation excluded
    assert not any("/news/" in link for link in links)
    assert not any("things-to-do-this-week" in link for link in links)


# ── _parse_zone_location ──────────────────────────────────────────────────────


def test_parse_zone_location_extracts_coords(tot):
    html = """
    <html><body>
    <div data-component="maps" data-zone-location-info="{&quot;address1&quot;:&quot;1-2 Ueno Koen&quot;,&quot;zones&quot;:[{&quot;latitude&quot;:35.7134,&quot;longitude&quot;:139.7716,&quot;name&quot;:&quot;Ueno Museum&quot;}]}"></div>
    </body></html>
    """
    soup = make_soup(html)
    lat, lng = tot._parse_zone_location(soup)
    assert lat == pytest.approx(35.7134)
    assert lng == pytest.approx(139.7716)


def test_parse_zone_location_returns_none_when_absent(tot):
    soup = make_soup("<html><body><p>no map here</p></body></html>")
    lat, lng = tot._parse_zone_location(soup)
    assert lat is None
    assert lng is None


def test_parse_zone_location_returns_none_when_zones_empty(tot):
    html = """
    <html><body>
    <div data-component="maps" data-zone-location-info="{&quot;zones&quot;:[]}"></div>
    </body></html>
    """
    soup = make_soup(html)
    lat, lng = tot._parse_zone_location(soup)
    assert lat is None
    assert lng is None


# ── _parse_json_ld ────────────────────────────────────────────────────────────


def test_parse_json_ld_finds_theater_event(tot):
    """Real fixture uses Review wrapping a TheaterEvent in itemReviewed."""
    html_bytes = (FIXTURES_DIR / "tot/real/event_full.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    ld = tot._parse_json_ld(soup)
    assert ld is not None
    assert ld["@type"] == "TheaterEvent"
    assert "Bunkyo" in ld["name"]


def test_parse_json_ld_finds_event_inside_review_wrapper(tot):
    """Time Out Tokyo wraps event data in Review.itemReviewed — must be surfaced."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Review","headline":"Test",
     "itemReviewed":{"@type":"MusicEvent","name":"Jazz Night",
       "startDate":"2026-07-01T20:00:00+09:00"}}
    </script>
    </head><body></body></html>
    """
    soup = make_soup(html)
    ld = tot._parse_json_ld(soup)
    assert ld is not None
    assert ld["@type"] == "MusicEvent"
    assert ld["name"] == "Jazz Night"


def test_parse_json_ld_returns_none_for_news_article(tot):
    html_bytes = (FIXTURES_DIR / "tot/real/event_news_article.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    ld = tot._parse_json_ld(soup)
    assert ld is None  # NewsArticle is not an Event type


def test_parse_json_ld_returns_none_when_no_script(tot):
    soup = make_soup("<html><body><h1>No scripts here</h1></body></html>")
    assert tot._parse_json_ld(soup) is None


def test_is_news_article_true(tot):
    html_bytes = (FIXTURES_DIR / "tot/real/event_news_article.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    assert tot._is_news_article(soup) is True


def test_is_news_article_false_for_event(tot):
    html_bytes = (FIXTURES_DIR / "tot/real/event_full.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    assert tot._is_news_article(soup) is False


# ── scrape_event ──────────────────────────────────────────────────────────────


def test_scrape_event_full_from_fixture(tot, monkeypatch):
    html_bytes = (FIXTURES_DIR / "tot/real/event_full.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/art/grand-van-gogh-exhibition")

    # Real page: Bunkyo Hydrangea Matsuri — pipe-separated suffix stripped
    assert result["title"] == "Bunkyo Hydrangea Matsuri"
    assert result["start_date"] == "2026-06-06"
    assert result["end_date"] == "2026-06-14"
    assert result["times"] == "10:00"
    assert result["price"] == "Free"
    assert result["venue_name"] == "Hakusan Shrine"
    assert "Bunkyo" in result["venue_address"] or "Hakusan" in result["venue_address"]
    assert result["image_url"] is not None
    assert result["latitude"] == pytest.approx(35.722227)
    assert result["longitude"] == pytest.approx(139.750933)


def test_scrape_event_raises_without_json_ld(tot, monkeypatch):
    """Any page without Event JSON-LD is rejected (venue/restaurant pages)."""
    html_bytes = (FIXTURES_DIR / "tot/synthetic/event_no_jsonld.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    with pytest.raises(ValueError, match="No Event JSON-LD"):
        tot.scrape_event("https://www.timeout.com/tokyo/things-to-do/oi-racecourse-flea-market")


def test_scrape_event_raises_on_news_article(tot, monkeypatch):
    html_bytes = (FIXTURES_DIR / "tot/real/event_news_article.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    with pytest.raises(ValueError, match="news article"):
        tot.scrape_event("https://www.timeout.com/tokyo/news/festivals-060326")


def test_scrape_event_raises_on_no_title(tot, monkeypatch):
    soup = make_soup("<html><body><p>No title here</p></body></html>")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    with pytest.raises(ValueError):
        tot.scrape_event("https://www.timeout.com/tokyo/art/unknown")


def test_scrape_event_no_coordinates_returns_none(tot, monkeypatch):
    """Event with valid JSON-LD but no data-zone-location-info → lat/lon = None."""
    html_bytes = (FIXTURES_DIR / "tot/synthetic/event_no_coordinates.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/things-to-do/no-coords")

    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["title"] == "No Coordinates Festival"
    assert result["start_date"] == "2026-08-01"


def test_scrape_event_incomplete_data_returns_none_fields(tot, monkeypatch):
    """Event JSON-LD with only name → all optional fields return None."""
    html_bytes = (FIXTURES_DIR / "tot/synthetic/event_incomplete_data.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/things-to-do/minimal")

    assert result["title"] == "Minimal Incomplete Event"
    assert result["start_date"] is None
    assert result["end_date"] is None
    assert result["times"] is None
    assert result["price"] is None
    assert result["venue_name"] is None
    assert result["venue_address"] is None
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["image_url"] is None
    assert result["categories"] == []
    assert result["description"] is None


# ── scrape_all ────────────────────────────────────────────────────────────────


def test_scrape_all_counts(tot, monkeypatch):
    urls = [
        "https://www.timeout.com/tokyo/art/event-a",
        "https://www.timeout.com/tokyo/music/event-b",
        "https://www.timeout.com/tokyo/news/article-c",
    ]
    monkeypatch.setattr(tot, "get_event_links", lambda max_pages=None: urls)

    good_event = {
        "url": urls[0],
        "title": "Event A",
        "start_date": "2026-07-01",
        "end_date": None,
        "times": "10:00",
        "price": "Free",
        "venue_name": "Venue A",
        "venue_address": "Tokyo",
        "categories": ["art"],
        "description": "Desc",
        "image_url": None,
    }

    def fake_scrape_event(url):
        if url == urls[0]:
            return {**good_event, "url": url}
        if url == urls[1]:
            return {**good_event, "url": url, "title": "Event B"}
        raise ValueError("news article")

    monkeypatch.setattr(tot, "scrape_event", fake_scrape_event)

    events, counts = tot.scrape_all()

    assert counts["links_seen"] == 3
    assert counts["events_ok"] == 2
    assert len(counts["errors"]) == 1
    assert counts["errors"][0]["url"] == urls[2]


# ── scrape ────────────────────────────────────────────────────────────────────


def test_scrape_returns_events_and_report(tot, monkeypatch):
    raw_events = [
        {
            "url": "https://www.timeout.com/tokyo/art/event-a",
            "title": "Event A",
            "start_date": "2026-07-15",
            "end_date": "2026-07-20",
            "times": "09:00",
            "price": "¥1,500",
            "venue_name": "Tokyo Museum",
            "venue_address": "1-1 Ueno, Taito, Tokyo",
            "categories": ["art", "culture"],
            "description": "A great art show.",
            "image_url": "https://media.timeout.com/img/event-a.jpg",
            "latitude": 35.7134,
            "longitude": 139.7716,
        }
    ]
    counts = {"links_seen": 1, "events_ok": 1, "errors": []}
    monkeypatch.setattr(tot, "scrape_all", lambda max_pages=None: (raw_events, counts))

    events, report = tot.scrape()

    assert len(events) == 1
    ev = events[0]
    assert ev.source == "tot"
    assert ev.title == "Event A"
    assert ev.start_date is not None
    assert ev.end_date is not None
    assert ev.latitude == pytest.approx(35.7134)
    assert ev.longitude == pytest.approx(139.7716)
    assert ev.price == "¥1,500"
    assert ev.venue == "Tokyo Museum"
    assert ev.attributes.venue_name == "Tokyo Museum"
    assert "art" in ev.attributes.categories

    assert report.source == "tot"
    assert report.links_seen == 1
    assert report.events_ok == 1


def test_scrape_critical_on_zero_events(tot, monkeypatch, caplog):
    monkeypatch.setattr(
        tot,
        "scrape_all",
        lambda max_pages=None: ([], {"links_seen": 0, "events_ok": 0, "errors": []}),
    )
    with caplog.at_level("CRITICAL", logger="scrapers.timeout_tokyo"):
        events, report = tot.scrape()
    assert events == []
    assert any("0 events" in r.message for r in caplog.records if r.levelname == "CRITICAL")


def test_scrape_no_critical_when_events_returned(tot, monkeypatch):
    raw_events = [
        {
            "url": "https://www.timeout.com/tokyo/art/event-a",
            "title": "Event A",
            "start_date": None,
            "end_date": None,
            "times": None,
            "price": None,
            "venue_name": None,
            "venue_address": None,
            "categories": [],
            "description": None,
            "image_url": None,
        }
    ]
    counts = {"links_seen": 1, "events_ok": 1, "errors": []}
    monkeypatch.setattr(tot, "scrape_all", lambda max_pages=None: (raw_events, counts))

    stream = io.StringIO()
    handler = logging.StreamHandler(stream)
    handler.setLevel(logging.CRITICAL)
    logging.getLogger("scrapers.timeout_tokyo").addHandler(handler)
    try:
        events, report = tot.scrape()
        assert len(events) == 1
        assert "CRITICAL" not in stream.getvalue()
    finally:
        logging.getLogger("scrapers.timeout_tokyo").removeHandler(handler)


# ── Event model integration ───────────────────────────────────────────────────


def test_event_model_accepts_tot_source():
    """Event model correctly validates tot source and attributes."""
    from datetime import datetime

    from models.event import Event

    ev = Event(
        id="abcdef1234567890",
        source="tot",
        title="Test Event",
        url="https://www.timeout.com/tokyo/art/test-event",
        start_date=None,
        end_date=None,
        times=None,
        venue="Test Venue",
        latitude=None,
        longitude=None,
        price="Free",
        attributes={
            "categories": ["art"],
            "venue_name": "Test Venue",
            "venue_address": "Tokyo",
            "image_url": None,
            "description": None,
        },
        created_at=datetime(2026, 6, 1, 12, 0, 0),
    )
    assert ev.source == "tot"
    assert ev.attributes.categories == ["art"]
    assert ev.attributes.venue_name == "Test Venue"


# ── Date parsing ──────────────────────────────────────────────────────────────


def test_scrape_event_date_parsing_from_iso8601(tot, monkeypatch):
    """Dates with timezone offset are parsed correctly."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"TheaterEvent","name":"Night Show",
     "startDate":"2026-08-10T19:30:00+09:00","endDate":"2026-08-10T22:00:00+09:00",
     "location":{"@type":"Place","name":"Tokyo Theater","address":{"streetAddress":"1-1 Ginza","addressLocality":"Chuo"}}}
    </script>
    </head><body><h1>Night Show</h1></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/theater/night-show")

    assert result["start_date"] == "2026-08-10"
    # end_date should be None because same day as start_date
    assert result["end_date"] is None
    # Same-day end time is appended: "19:30-22:00"
    assert result["times"] == "19:30-22:00"


def test_scrape_event_end_date_different_day(tot, monkeypatch):
    """Multi-day events keep end_date when it differs from start_date."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Festival","name":"Summer Fest",
     "startDate":"2026-08-01T10:00:00+09:00","endDate":"2026-08-31T22:00:00+09:00",
     "location":{"@type":"Place","name":"Yoyogi Park"}}
    </script>
    </head><body><h1>Summer Fest</h1></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/music/summer-fest")

    assert result["start_date"] == "2026-08-01"
    assert result["end_date"] == "2026-08-31"


def test_scrape_event_free_price(tot, monkeypatch):
    """Price of 0 is formatted as 'Free'."""
    html = """
    <html><head>
    <script type="application/ld+json">
    {"@context":"https://schema.org","@type":"Event","name":"Free Outdoor Concert",
     "offers":{"@type":"Offer","price":"0","priceCurrency":"JPY"},
     "location":{"@type":"Place","name":"Hibiya Park"}}
    </script>
    </head><body><h1>Free Outdoor Concert</h1></body></html>
    """
    soup = BeautifulSoup(html, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/music/free-concert")

    assert result["price"] == "Free"


# ── TEST-006 : assertions de contrat et qualité d'extraction ──────────────────

_FIXTURE_TOT_LISTING = "tot/real/listing.html"
_FIXTURE_TOT_EVENT_FULL = "tot/real/event_full.html"


def test_contract_listing_rate_real(tot, monkeypatch):
    """CONTRAT: tot/real/listing.html — ≥ 10 liens extraits (sélecteur cassé → échoue)."""
    import requests as _requests

    html_bytes = (FIXTURES_DIR / _FIXTURE_TOT_LISTING).read_bytes()

    def fake_fetch(url, session, timeout):
        r = _requests.Response()
        r.status_code = 200
        r._content = html_bytes
        return r

    monkeypatch.setattr("scrapers.timeout_tokyo._fetch", fake_fetch)
    monkeypatch.setattr(
        "scrapers.timeout_tokyo._listing_paths",
        lambda n: ["/tokyo/things-to-do/things-to-do-this-week-in-tokyo"],
    )

    links = tot.get_event_links(max_pages=1)

    # Baseline capturée : 31 liens. Seuil à 25 (≈80%) pour détecter une perte
    # significative sans bloquer les améliorations marginales du filtre.
    assert len(links) >= 25, (
        f"[{_FIXTURE_TOT_LISTING}] {len(links)} liens extraits"
        " — sélecteur probablement cassé (baseline : 31, seuil : 25)"
    )


def test_contract_essential_fields_real_event_full(tot, monkeypatch):
    """CONTRAT: tot/real/event_full.html — champs essentiels non-vides, pas de perte silencieuse."""
    html_bytes = (FIXTURES_DIR / _FIXTURE_TOT_EVENT_FULL).read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tot, "get_event_page", lambda url: soup)

    result = tot.scrape_event("https://www.timeout.com/tokyo/art/bunkyo-matsuri")
    f = _FIXTURE_TOT_EVENT_FULL

    assert result["title"], f"[{f}] title est vide"
    assert result["start_date"], f"[{f}] start_date est vide"
    assert result["venue_name"], f"[{f}] venue_name est vide"
    assert result["url"], f"[{f}] url est vide"
    # Pas de perte silencieuse : fixture réelle peuple 13/13 champs, tolérance 1
    renseignes = [k for k, v in result.items() if v is not None and v != "" and v != []]
    assert len(renseignes) >= 12, (
        f"[{f}] trop de champs vides — {len(renseignes)}/{len(result)} renseignés"
        f" (attendu ≥ 12 sur 13)"
    )
