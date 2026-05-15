import json
import pytest
from bs4 import BeautifulSoup
from scrapers.tokyo_cheapo import TokyoCheapo


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
    soup = make_soup('<article class="event-tag-flea-market-3 event-tag-shopping-4 event-tag-recycling"></article>')
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
    data = {"lat": "35.729032", "lng": "139.719566", "title": "Sunshine City", "addr": "3 Chome-1 Higashiikebukuro"}
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
