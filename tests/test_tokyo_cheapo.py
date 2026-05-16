import json
import pytest
from bs4 import BeautifulSoup
from scrapers.tokyo_cheapo import (
    TokyoCheapo,
    _clean_whitespace,
    _is_price_text,
    _parse_12h_time,
    _split_time,
    _parse_date_range,
)


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
