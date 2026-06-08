import json
from datetime import date as _date_cls
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import requests
from bs4 import BeautifulSoup

from scrapers.tokyo_cheapo import (
    TokyoCheapo,
    _clean_whitespace,
    _is_price_text,
    _parse_12h_time,
    _parse_date_range,
    _split_time,
)

FIXTURES_DIR = Path(__file__).parent / "fixtures"


@pytest.fixture
def tc():
    return TokyoCheapo()


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


# --- parse_title ---


def test_parse_title(tc):
    soup = make_soup("<header><h1>Kawaii Flea Market</h1></header>")
    assert tc.parse_title(soup) == "Kawaii Flea Market"


# --- parse_date ---


def test_parse_date_single(tc):
    soup = make_soup("""
    <header>
        <div class="day">May 17</div>
        <div class="date">17</div>
    </header>
    """)
    assert tc.parse_date(soup) == "May 17 17"


def test_parse_date_range(tc):
    soup = make_soup("""
    <header>
        <div class="date">May 3</div>
        <div class="date">May 5</div>
    </header>
    """)
    assert tc.parse_date(soup) == "May 3 - May 5"


def test_parse_date_unconfirmed(tc):
    soup = make_soup("""
    <header>
        <div class="date">Early <div class="month">Apr</div></div>
    </header>
    """)
    assert tc.parse_date(soup) == "Early Apr"


def test_parse_date_unconfirmed_range(tc):
    soup = make_soup("""
    <header>
        <div class="date">Mid <div class="month">May</div> ~ Late <div class="month">May</div></div>
    </header>
    """)
    assert "Mid" in tc.parse_date(soup)
    assert "May" in tc.parse_date(soup)


def test_parse_date_no_date(tc):
    soup = make_soup("<header></header>")
    assert tc.parse_date(soup) == ""


# --- parse_time_and_price ---


def test_parse_time_and_price(tc):
    soup = make_soup("""
    <header>
        <div class="event__attribute">10:00am – 4:00pm</div>
        <div class="event__attribute">Free</div>
    </header>
    """)
    time, price = tc.parse_time_and_price(soup)
    assert time == "10:00am – 4:00pm"
    assert price == "Free"


def test_parse_time_and_price_no_price(tc):
    soup = make_soup("""
    <header>
        <div class="event__attribute">7:30pm – 10:00pm</div>
    </header>
    """)
    time, price = tc.parse_time_and_price(soup)
    assert time == "7:30pm – 10:00pm"
    assert price is None


def test_parse_time_and_price_price_only(tc):
    # Un seul attr qui est un prix → time vide, price rempli
    soup = make_soup("""
    <header>
        <div class="event__attribute">Free</div>
    </header>
    """)
    time, price = tc.parse_time_and_price(soup)
    assert time == ""
    assert price == "Free"


def test_parse_time_and_price_yen_only(tc):
    soup = make_soup("""
    <header>
        <div class="event__attribute">¥3,800\t\t\t – ¥40,000</div>
    </header>
    """)
    time, price = tc.parse_time_and_price(soup)
    assert time == ""
    assert price == "¥3,800 – ¥40,000"


def test_parse_time_and_price_tabs_cleaned(tc):
    soup = make_soup("""
    <header>
        <div class="event__attribute">9:00am – 5:00pm</div>
        <div class="event__attribute">¥1,000\t\t\t – ¥2,500</div>
    </header>
    """)
    time, price = tc.parse_time_and_price(soup)
    assert time == "9:00am – 5:00pm"
    assert price == "¥1,000 – ¥2,500"


def test_parse_time_and_price_empty(tc):
    soup = make_soup("<header></header>")
    time, price = tc.parse_time_and_price(soup)
    assert time == ""
    assert price is None


# --- parse_categories ---


def test_parse_categories(tc):
    soup = make_soup('<article class="event-category-market event-category-food"></article>')
    assert tc.parse_categories(soup) == ["market", "food"]


def test_parse_categories_strips_suffix(tc):
    soup = make_soup('<article class="event-category-sport-2 event-category-film-2"></article>')
    assert tc.parse_categories(soup) == ["sport", "film"]


def test_parse_categories_no_article(tc):
    soup = make_soup("<div></div>")
    assert tc.parse_categories(soup) == []


# --- parse_tags ---


def test_parse_tags(tc):
    soup = make_soup(
        '<article class="event-tag-flea-market-3 event-tag-shopping-4 event-tag-recycling"></article>'
    )
    assert tc.parse_tags(soup) == ["flea-market", "shopping", "recycling"]


def test_parse_tags_no_tags(tc):
    soup = make_soup('<article class="type-event status-publish"></article>')
    assert tc.parse_tags(soup) == []


# --- parse_official_link ---


def test_parse_official_link(tc):
    soup = make_soup("""
    <div class="section--info-box--event__content">
        <div>External link<a href="https://souq.jp/">Official site</a></div>
    </div>
    """)
    assert tc.parse_official_link(soup) == "https://souq.jp/"


def test_parse_official_link_in_next_sibling(tc):
    soup = make_soup("""
    <div class="section--info-box--event__content">
        <div>External link</div>
        <div><a href="https://example.com/">Official site</a></div>
    </div>
    """)
    assert tc.parse_official_link(soup) == "https://example.com/"


def test_parse_official_link_absent(tc):
    soup = make_soup("""
    <div class="section--info-box--event__content">
        <div>Entry</div>
        <div>Free</div>
    </div>
    """)
    assert tc.parse_official_link(soup) is None


def test_parse_official_link_no_infobox(tc):
    soup = make_soup("<div></div>")
    assert tc.parse_official_link(soup) is None


# --- parse_locations ---


def test_parse_locations_multiple(tc):
    data = {
        "lat": "35.7",
        "lng": "139.7",
        "title": "Venue A",
        "locations": [
            ["Venue A", "35.7", "139.7", "Address A"],
            ["Venue B", "35.6", "139.6", "Address B"],
        ],
    }
    soup = make_soup(f"""
    <div async-component="1" component-name="apple-maps">
        <script type="application/json">{json.dumps(data)}</script>
    </div>
    """)
    locs = tc.parse_locations(soup)
    assert len(locs) == 2
    assert locs[0] == {"name": "Venue A", "lat": 35.7, "lng": 139.7, "address": "Address A"}
    assert locs[1] == {"name": "Venue B", "lat": 35.6, "lng": 139.6, "address": "Address B"}


def test_parse_locations_single_fallback(tc):
    data = {
        "lat": "35.729032",
        "lng": "139.719566",
        "title": "Sunshine City",
        "addr": "3 Chome-1 Higashiikebukuro",
    }
    soup = make_soup(f"""
    <div async-component="1" component-name="apple-maps">
        <script type="application/json">{json.dumps(data)}</script>
    </div>
    """)
    locs = tc.parse_locations(soup)
    assert len(locs) == 1
    assert locs[0]["name"] == "Sunshine City"
    assert locs[0]["lat"] == 35.729032
    assert locs[0]["lng"] == 139.719566


def test_parse_locations_no_map(tc):
    soup = make_soup("<div></div>")
    assert tc.parse_locations(soup) == []


def test_parse_locations_html_entity(tc):
    data = {"lat": "35.69", "lng": "139.76", "title": "WeLearn Community 80&#8217;s Café"}
    soup = make_soup(f"""
    <div async-component="1" component-name="apple-maps">
        <script type="application/json">{json.dumps(data)}</script>
    </div>
    """)
    locs = tc.parse_locations(soup)
    assert locs[0]["name"] == "WeLearn Community 80\u2019s Café"


# --- _clean_whitespace ---


def test_clean_whitespace_tabs():
    assert _clean_whitespace("¥3,800\t\t\t\t – ¥40,000") == "¥3,800 – ¥40,000"


def test_clean_whitespace_newlines():
    assert _clean_whitespace("hello\n  world") == "hello world"


def test_clean_whitespace_already_clean():
    assert _clean_whitespace("Free") == "Free"


# --- _is_price_text ---


def test_is_price_free():
    assert _is_price_text("Free") is True


def test_is_price_yen():
    assert _is_price_text("¥1,000") is True


def test_is_price_advance_sales():
    assert _is_price_text("¥500 (advance sales)") is True


def test_is_price_at_the_door():
    assert _is_price_text("¥2,600 (at the door)") is True


def test_is_price_time():
    assert _is_price_text("7:30pm – 10:00pm") is False


def test_is_price_empty():
    assert _is_price_text("") is False


# --- _parse_12h_time ---


def test_parse_12h_time_pm():
    assert _parse_12h_time("7:30pm") == "19:30"


def test_parse_12h_time_am():
    assert _parse_12h_time("6:00am") == "06:00"


def test_parse_12h_time_noon():
    assert _parse_12h_time("12:00pm") == "12:00"


def test_parse_12h_time_midnight():
    assert _parse_12h_time("12:00am") == "00:00"


def test_parse_12h_time_uppercase():
    assert _parse_12h_time("9:30AM") == "09:30"


# --- _split_time ---


def test_split_time_range():
    assert _split_time("7:30pm – 10:00pm") == ("19:30", "22:00")


def test_split_time_am_pm():
    assert _split_time("9:00am – 2:30pm") == ("09:00", "14:30")


def test_split_time_start_only():
    assert _split_time("12:00pm") == ("12:00", "")


def test_split_time_empty():
    assert _split_time("") == ("", "")


# --- _parse_date_range ---


def test_parse_date_range_single_with_weekday():
    assert _parse_date_range("Fri, May 15", year=2026) == ("2026/05/15", "2026/05/15")


def test_parse_date_range_single():
    assert _parse_date_range("May 16", year=2026) == ("2026/05/16", "2026/05/16")


def test_parse_date_range_short_range():
    assert _parse_date_range("May 15 - May 17", year=2026) == ("2026/05/15", "2026/05/17")


def test_parse_date_range_long_range():
    assert _parse_date_range("Mar 27 - Sep 30", year=2026) == ("2026/03/27", "2026/09/30")


def test_parse_date_range_cross_month():
    assert _parse_date_range("May 30 - Jun 2", year=2026) == ("2026/05/30", "2026/06/02")


def test_parse_date_range_fuzzy_single():
    assert _parse_date_range("Mid May", year=2026) == ("2026/05/11", "2026/05/20")


def test_parse_date_range_fuzzy_same_month():
    assert _parse_date_range("Mid ~ Late May", year=2026) == ("2026/05/11", "2026/05/31")


def test_parse_date_range_fuzzy_cross_month():
    assert _parse_date_range("Early Apr ~ Early Jun", year=2026) == ("2026/04/01", "2026/06/10")


def test_parse_date_range_fuzzy_late_month_end():
    # Late Feb → dernier jour de février
    assert _parse_date_range("Late Feb", year=2026) == ("2026/02/21", "2026/02/28")


# ---------------------------------------------------------------------------
# Cross-year date range — BUG-002
# ---------------------------------------------------------------------------


def test_parse_date_range_cross_year_dec_scraping():
    # Scraping en décembre : "Dec 31 - Jan 2" → end passe à l'année suivante
    ref = _date_cls(2026, 12, 5)
    start, end = _parse_date_range("Dec 31 - Jan 2", year=2026, reference=ref)
    assert start == "2026/12/31"
    assert end == "2027/01/02"


def test_parse_date_range_cross_year_jan_scraping():
    # Scraping en janvier : "Dec 31 - Jan 2" → start revient à l'année précédente
    ref = _date_cls(2027, 1, 5)
    start, end = _parse_date_range("Dec 31 - Jan 2", year=2027, reference=ref)
    assert start == "2026/12/31"
    assert end == "2027/01/02"


def test_parse_date_range_cross_year_normal_unaffected():
    # Plage same-year ne doit pas bumper l'année de end
    ref = _date_cls(2026, 5, 1)
    start, end = _parse_date_range("May 15 - Jun 2", year=2026, reference=ref)
    assert start == "2026/05/15"
    assert end == "2026/06/02"


def test_parse_date_range_range_same_month_future_dec_scraping():
    # "Jan 2 - Jan 5" scraping en décembre : les deux dates passent à l'année suivante
    ref = _date_cls(2026, 12, 5)
    start, end = _parse_date_range("Jan 2 - Jan 5", year=2026, reference=ref)
    assert start == "2027/01/02"
    assert end == "2027/01/05"


def test_parse_date_range_ongoing_long_range_unaffected():
    # "Mar 27 - Sep 30" scrapée le 30 sep : plage en cours, pas de bump
    ref = _date_cls(2026, 9, 30)
    start, end = _parse_date_range("Mar 27 - Sep 30", year=2026, reference=ref)
    assert start == "2026/03/27"
    assert end == "2026/09/30"


def test_parse_date_range_fuzzy_cross_year_dec_scraping():
    # "Early Jan" scrapée en décembre → année suivante
    ref = _date_cls(2026, 12, 5)
    start, end = _parse_date_range("Early Jan", year=2026, reference=ref)
    assert start == "2027/01/01"
    assert end == "2027/01/10"


def test_parse_date_range_fuzzy_cross_month_cross_year_dec_scraping():
    # "Late Dec ~ Early Jan" scraping en décembre → start 2026, end 2027
    ref = _date_cls(2026, 12, 5)
    start, end = _parse_date_range("Late Dec ~ Early Jan", year=2026, reference=ref)
    assert start == "2026/12/21"
    assert end == "2027/01/10"


def test_parse_date_range_fuzzy_cross_month_cross_year_jan_scraping():
    # "Late Dec ~ Early Jan" scraping en janvier → start 2026, end 2027
    ref = _date_cls(2027, 1, 5)
    start, end = _parse_date_range("Late Dec ~ Early Jan", year=2027, reference=ref)
    assert start == "2026/12/21"
    assert end == "2027/01/10"


def test_parse_date_range_range_same_month_dec_jan_scraping():
    # "Dec 30 - Dec 31" scraping en janvier → revient à l'année précédente
    ref = _date_cls(2027, 1, 5)
    start, end = _parse_date_range("Dec 30 - Dec 31", year=2027, reference=ref)
    assert start == "2026/12/30"
    assert end == "2026/12/31"


def test_parse_date_range_single_dec_jan_scraping():
    # "Dec 31" scraping en janvier → revient à l'année précédente
    ref = _date_cls(2027, 1, 5)
    start, end = _parse_date_range("Dec 31", year=2027, reference=ref)
    assert start == "2026/12/31"
    assert end == "2026/12/31"


def test_parse_date_range_single_cross_year_dec_scraping():
    # Date unique en janvier scrapée en décembre → année suivante
    ref = _date_cls(2026, 12, 5)
    start, end = _parse_date_range("Jan 2", year=2026, reference=ref)
    assert start == "2027/01/02"
    assert end == "2027/01/02"


def test_parse_date_range_single_normal_unaffected():
    # Date unique dans l'année courante → pas de bump
    ref = _date_cls(2026, 5, 1)
    start, end = _parse_date_range("May 17", year=2026, reference=ref)
    assert start == "2026/05/17"
    assert end == "2026/05/17"


# ---------------------------------------------------------------------------
# Fixture-based contract tests
# ---------------------------------------------------------------------------


def _make_404_http_error() -> requests.HTTPError:
    err = requests.HTTPError()
    err.response = MagicMock()
    err.response.status_code = 404
    return err


# --- get_event_links ---


def test_get_event_links_from_fixture(tc, monkeypatch):
    """Listing fixture contains 2 real event links; excluded links are filtered out."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/listing.html").read_bytes()
    call_count = 0

    def mock_fetch(url, session, timeout=10):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = MagicMock()
            resp.content = html_bytes
            return resp
        raise _make_404_http_error()

    monkeypatch.setattr("scrapers.tokyo_cheapo._fetch", mock_fetch)
    links = tc.get_event_links(max_pages=5)

    assert len(links) == 2
    assert all(link.startswith("https://tokyocheapo.com/events/") for link in links)
    # Excluded patterns must not appear
    excluded_suffixes = ["/events/", "/events/this-week/", "/events/may/", "/events/june/"]
    full_paths = [link.replace("https://tokyocheapo.com", "") for link in links]
    for path in full_paths:
        assert path not in excluded_suffixes


def test_get_event_links_stops_on_empty_page(tc, monkeypatch):
    """Pagination stops when a page returns no event links."""
    empty_html = b"<html><body><a href='/about/'>About</a></body></html>"
    call_count = 0

    def mock_fetch(url, session, timeout=10):
        nonlocal call_count
        call_count += 1
        resp = MagicMock()
        resp.content = empty_html
        return resp

    monkeypatch.setattr("scrapers.tokyo_cheapo._fetch", mock_fetch)
    links = tc.get_event_links(max_pages=5)

    assert links == []
    assert call_count == 1  # stops after first empty page


# --- scrape_event with full fixture ---


def test_scrape_event_full_fixture(tc, monkeypatch):
    """scrape_event returns all expected fields from a complete event page."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/event_full.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)
    # Figer l'horloge JST pour que l'assertion de date soit déterministe quelle
    # que soit la période de l'année où le test tourne.
    fixed_jst = _date_cls(2026, 6, 5)
    monkeypatch.setattr("scrapers.tokyo_cheapo._today_jst", lambda: fixed_jst)

    result = tc.scrape_event("https://tokyocheapo.com/events/kawaii-flea-market-2026/")

    assert result["title"] == "Kawaii Flea Market"
    assert result["start_date"] == "2026/05/17"
    assert result["end_date"] == "2026/05/17"
    assert result["start_time"] == "10:00"
    assert result["end_time"] == "17:00"
    assert result["price"] == "Free"
    assert "flea market" in result["description"].lower()
    assert "market" in result["categories"]
    assert "shopping" in result["categories"]
    assert "flea-market" in result["tags"]
    assert "vintage" in result["tags"]
    assert result["official_link"] == "https://kawaii-market.jp/"
    assert len(result["locations"]) == 1
    loc = result["locations"][0]
    assert loc["name"] == "Yoyogi Park"
    assert abs(loc["lat"] - 35.671660) < 1e-4
    assert abs(loc["lng"] - 139.694692) < 1e-4


# --- scrape_event with missing description (BUG-005 regression) ---


def test_scrape_event_no_description_returns_empty_string(tc, monkeypatch):
    """parse_description returns '' when div.entry-content__text is absent (BUG-005 fix)."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/event_no_description.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)

    result = tc.scrape_event("https://tokyocheapo.com/events/pop-up-market-akihabara/")

    assert result["description"] == ""
    assert result["title"] == "Pop-up Market Akihabara"


# --- scrape_event with multiple locations ---


def test_scrape_event_multi_location_fixture(tc, monkeypatch):
    """scrape_event returns multiple location entries when Apple Maps JSON has locations array."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/event_multi_location.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)

    result = tc.scrape_event("https://tokyocheapo.com/events/tokyo-walking-festival/")

    assert len(result["locations"]) == 2
    names = [loc["name"] for loc in result["locations"]]
    assert "Ueno Park" in names
    assert "Asakusa Temple" in names
    ueno = next(loc for loc in result["locations"] if loc["name"] == "Ueno Park")
    assert abs(ueno["lat"] - 35.714998) < 1e-4


# --- scrape() produces one Event per location ---


def test_scrape_multi_location_creates_two_events(tc, monkeypatch):
    """scrape() yields one Event per location for a multi-location raw event."""
    raw_events = [
        {
            "url": "https://tokyocheapo.com/events/tokyo-walking-festival/",
            "title": "Tokyo Walking Festival",
            "start_date": "2026/05/23",
            "end_date": "2026/05/24",
            "start_time": "09:00",
            "end_time": "16:00",
            "price": "Free",
            "description": "A walking festival.",
            "categories": ["outdoor"],
            "tags": ["walking"],
            "official_link": None,
            "locations": [
                {"name": "Ueno Park", "lat": 35.714998, "lng": 139.773498},
                {"name": "Asakusa Temple", "lat": 35.714765, "lng": 139.796655},
            ],
        }
    ]
    counts = {"links_seen": 1, "events_ok": 1, "errors": []}
    monkeypatch.setattr(tc, "scrape_all", lambda max_pages=10: (raw_events, counts))

    events, report = tc.scrape()

    assert len(events) == 2
    titles = {e.title for e in events}
    assert titles == {"Tokyo Walking Festival"}
    # Each location produces a distinct ID
    ids = {e.id for e in events}
    assert len(ids) == 2
    locs = {e.attributes.location_name for e in events}
    assert locs == {"Ueno Park", "Asakusa Temple"}


# --- ARCH-006 : injection des settings ---


def test_scraper_timeout_matches_settings():
    """_timeout est bien la valeur configurée par settings."""
    tc = TokyoCheapo()
    from config import settings

    assert tc._timeout == settings.scrape_request_timeout_seconds


def test_scraper_max_pages_matches_settings():
    """_max_pages est bien la valeur configurée par settings."""
    tc = TokyoCheapo()
    from config import settings

    assert tc._max_pages == settings.scrape_max_pages_tc


def test_scraper_user_agent_from_settings(monkeypatch):
    """Le User-Agent de la session reflète scrape_user_agent."""
    import config
    from config import Settings

    fake = Settings(scrape_user_agent="TestBot/9.9", _env_file=None)
    monkeypatch.setattr(config, "settings", fake)
    tc2 = TokyoCheapo()
    assert tc2.session.headers["User-Agent"] == "TestBot/9.9"


# ---------------------------------------------------------------------------
# TEST-003 : corpus étendu — fixtures supplémentaires
# ---------------------------------------------------------------------------


def test_scrape_event_cross_year_dates(tc, monkeypatch):
    """Plage Dec 31 - Jan 3 avec référence en janvier → start décalé à l'année précédente."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/event_cross_year.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)
    # Référence : début janvier, l'événement Dec 31 appartient à l'année passée
    fixed_jst = _date_cls(2026, 1, 5)
    monkeypatch.setattr("scrapers.tokyo_cheapo._today_jst", lambda: fixed_jst)

    result = tc.scrape_event("https://tokyocheapo.com/events/tokyo-countdown-party/")

    assert result["start_date"] == "2025/12/31"
    assert result["end_date"] == "2026/01/03"
    assert result["title"] == "Tokyo Countdown Party"
    assert result["price"] == "¥2,500"
    loc = result["locations"][0]
    assert loc["name"] == "Shibuya Crossing"


def test_scrape_event_fuzzy_date(tc, monkeypatch):
    """Date floue 'Early July' → start=premier juillet, end=10 juillet."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/event_fuzzy_date.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)
    fixed_jst = _date_cls(2026, 6, 8)
    monkeypatch.setattr("scrapers.tokyo_cheapo._today_jst", lambda: fixed_jst)

    result = tc.scrape_event("https://tokyocheapo.com/events/tanabata-ueno/")

    assert result["start_date"] == "2026/07/01"
    assert result["end_date"] == "2026/07/10"
    assert result["title"] == "Tanabata Festival Ueno"


def test_scrape_event_missing_optional_fields(tc, monkeypatch):
    """Page sans Apple Maps, sans lien externe et sans prix → valeurs None/vides."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/event_missing_optional.html").read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)
    fixed_jst = _date_cls(2026, 6, 8)
    monkeypatch.setattr("scrapers.tokyo_cheapo._today_jst", lambda: fixed_jst)

    result = tc.scrape_event("https://tokyocheapo.com/events/open-mic-shimokitazawa/")

    assert result["title"] == "Open Mic Night Shimokitazawa"
    assert result["locations"] == []
    assert result["official_link"] is None
    assert result["price"] is None


# ---------------------------------------------------------------------------
# TEST-006 : assertions de contrat et qualité d'extraction
# ---------------------------------------------------------------------------

_FIXTURE_TC_EVENT_FULL = "tc/synthetic/event_full.html"


def test_contract_essential_fields_event_full(tc, monkeypatch):
    """CONTRAT: tc/synthetic/event_full.html — champs essentiels, pas de perte silencieuse."""
    html_bytes = (FIXTURES_DIR / _FIXTURE_TC_EVENT_FULL).read_bytes()
    soup = BeautifulSoup(html_bytes, "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)
    fixed_jst = _date_cls(2026, 6, 5)
    monkeypatch.setattr("scrapers.tokyo_cheapo._today_jst", lambda: fixed_jst)

    result = tc.scrape_event("https://tokyocheapo.com/events/kawaii-flea-market-2026/")
    f = _FIXTURE_TC_EVENT_FULL

    # Ensemble fixe de clés contractuelles peuplées par la fixture
    # (résistant à l'ajout de nouveaux champs optionnels dans le scraper)
    _EXPECTED_KEYS = {
        "url",
        "title",
        "start_date",
        "end_date",
        "start_time",
        "end_time",
        "price",
        "description",
        "categories",
        "tags",
        "official_link",
        "locations",
    }
    manquants = {k for k in _EXPECTED_KEYS if not result.get(k)}
    assert not manquants, f"[{f}] champs contractuels absents : {sorted(manquants)}"


def test_get_event_links_deduplicates_and_excludes(tc, monkeypatch):
    """Listing avec 5 uniques + 1 doublon + liens exclus → 5 liens retournés."""
    html_bytes = (FIXTURES_DIR / "tc/synthetic/listing_rich.html").read_bytes()

    def mock_fetch(url, session, timeout=10):
        resp = MagicMock()
        resp.content = html_bytes
        return resp

    # Deuxième appel : 404 pour stopper la pagination
    call_count = 0

    def mock_fetch_paged(url, session, timeout=10):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = MagicMock()
            resp.content = html_bytes
            return resp
        raise _make_404_http_error()

    monkeypatch.setattr("scrapers.tokyo_cheapo._fetch", mock_fetch_paged)
    links = tc.get_event_links(max_pages=5)

    assert len(links) == 5
    assert all(link.startswith("https://tokyocheapo.com/events/") for link in links)
    # Aucun lien exclu ne doit apparaître
    paths = [link.replace("https://tokyocheapo.com", "") for link in links]
    from scrapers.tokyo_cheapo import _EXCLUDE_LINKS

    for path in paths:
        assert path not in _EXCLUDE_LINKS


# ---------------------------------------------------------------------------
# TEST-003 : corpus réel Tokyo Cheapo
# ---------------------------------------------------------------------------

_REAL_TC_DIR = FIXTURES_DIR / "tc" / "real"
_REAL_TC_EVENTS = sorted(_REAL_TC_DIR.glob("event_*.html")) if _REAL_TC_DIR.exists() else []
_REAL_TC_LISTINGS = sorted(_REAL_TC_DIR.glob("listing_*.html")) if _REAL_TC_DIR.exists() else []

# Champs attendus non vides pour chaque fixture réelle (couverture des sélecteurs par cas)
_TC_FIXTURE_REQUIRED: dict[str, set[str]] = {
    "event_katsushika_iris_festival": {"start_date", "locations"},
    "event_candlelight_concert": {"start_date"},
    "event_dagashiya_class": {"start_date"},
    "event_downtown_highball_festival": {"start_date", "end_date"},
    "event_torigoe_matsuri": {"start_date"},
}
# Fixtures pour lesquelles ≥ 2 lieux sont attendus
_TC_MULTI_LOCATION: set[str] = {"event_katsushika_iris_festival"}
# Fixtures pour lesquelles locations doit être vide (pas de coordonnées Apple Maps)
_TC_NO_LOCATION: set[str] = {"event_candlelight_concert"}


def test_real_corpus_tc_is_not_empty() -> None:
    """Échoue si le corpus réel TC est absent — empêche CI verte sans tests de contrat."""
    assert len(_REAL_TC_EVENTS) > 0, (
        "Corpus réel TC manquant : aucun event_*.html dans tests/fixtures/tc/real/. "
        "Relancer tools/renew_fixtures.py pour reconstituer le corpus."
    )
    assert len(_REAL_TC_LISTINGS) > 0, (
        "Corpus réel TC manquant : aucun listing_*.html dans tests/fixtures/tc/real/."
    )


@pytest.mark.parametrize("fixture", _REAL_TC_EVENTS, ids=lambda f: f.stem)
def test_real_event_parses_title_and_url(tc, monkeypatch, fixture):
    """Chaque capture réelle TC produit au moins un titre et une URL non vides."""
    soup = BeautifulSoup(fixture.read_bytes(), "html.parser")
    monkeypatch.setattr(tc, "get_event_page", lambda url: soup)
    url = f"https://tokyocheapo.com/events/{fixture.stem.removeprefix('event_')}/"

    result = tc.scrape_event(url)

    assert result.get("title"), f"[{fixture.name}] title vide ou absent"
    assert result.get("url"), f"[{fixture.name}] url vide ou absent"
    assert result["url"] == url
    # Assertions de structure : sélecteurs ne doivent pas lever d'exception ni changer de type
    assert isinstance(result.get("description"), str), (
        f"[{fixture.name}] description doit être une str"
    )
    assert isinstance(result.get("locations"), list), (
        f"[{fixture.name}] locations doit être une liste"
    )
    assert isinstance(result.get("categories"), list), (
        f"[{fixture.name}] categories doit être une liste"
    )
    # Assertions spécifiques à chaque fixture selon la variante couverte
    required = _TC_FIXTURE_REQUIRED.get(fixture.stem, set())
    if "start_date" in required:
        assert result.get("start_date"), f"[{fixture.name}] start_date attendue mais absente"
    if "end_date" in required:
        assert result.get("end_date"), (
            f"[{fixture.name}] end_date attendue (fixture multi-jour) mais absente"
        )
    if fixture.stem in _TC_MULTI_LOCATION:
        assert len(result.get("locations", [])) >= 2, (
            f"[{fixture.name}] ≥ 2 lieux attendus pour cette fixture multi-lieu"
        )
    if fixture.stem in _TC_NO_LOCATION:
        assert len(result.get("locations", [])) == 0, (
            f"[{fixture.name}] locations=[] attendu (pas de coordonnées Apple Maps) mais {result.get('locations')}"
        )


@pytest.mark.parametrize("fixture", _REAL_TC_LISTINGS, ids=lambda f: f.stem)
def test_real_listing_extracts_event_links(tc, monkeypatch, fixture):
    """Chaque page de listing réelle TC retourne au moins 5 liens d'événements."""
    html_bytes = fixture.read_bytes()

    call_count = 0

    def mock_fetch(url, session, timeout=10):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = MagicMock()
            resp.content = html_bytes
            return resp
        raise _make_404_http_error()

    monkeypatch.setattr("scrapers.tokyo_cheapo._fetch", mock_fetch)
    links = tc.get_event_links(max_pages=1)

    assert len(links) >= 5, f"[{fixture.name}] seulement {len(links)} liens extraits"
    assert all(link.startswith("https://tokyocheapo.com/events/") for link in links)


def test_real_listing_pagination(tc, monkeypatch):
    """Les deux pages de listing réelles TC sont parcourues et leurs liens cumulés."""
    html_1 = (_REAL_TC_DIR / "listing_1.html").read_bytes()
    html_2 = (_REAL_TC_DIR / "listing_2.html").read_bytes()

    call_count = 0

    def mock_fetch(url, session, timeout=10):
        nonlocal call_count
        call_count += 1
        if call_count == 1:
            resp = MagicMock()
            resp.content = html_1
            return resp
        if call_count == 2:
            resp = MagicMock()
            resp.content = html_2
            return resp
        raise _make_404_http_error()

    monkeypatch.setattr("scrapers.tokyo_cheapo._fetch", mock_fetch)
    links = tc.get_event_links(max_pages=3)

    assert len(links) >= 10, f"Pagination 2 pages : seulement {len(links)} liens (attendu ≥ 10)"
    assert call_count == 3, (
        f"Le scraper devrait faire 3 requêtes (p1, p2, p3→404) mais en a fait {call_count}"
    )
    assert all(link.startswith("https://tokyocheapo.com/events/") for link in links)
