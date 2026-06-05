from unittest.mock import MagicMock, patch

import pytest
from bs4 import BeautifulSoup

from scrapers.hanabi_walker import (
    HanabiWalker,
    _extract_dates,
    _extract_time,
    _parse_slash_dates,
    _split_paid_seating,
)


def make_soup(html: str) -> BeautifulSoup:
    return BeautifulSoup(html, "html.parser")


@pytest.fixture
def hw():
    return HanabiWalker()


# ---------------------------------------------------------------------------
# _extract_time
# ---------------------------------------------------------------------------

def test_extract_time_range():
    assert _extract_time("19:30～21:00(予定)開場 16:00") == ("19:30", "21:00")


def test_extract_time_range_wide_tilde():
    assert _extract_time("19:30〜20:30") == ("19:30", "20:30")


def test_extract_time_start_only():
    assert _extract_time("花火は19:30～開場は17:30～") == ("19:30", None)


def test_extract_time_no_time():
    assert _extract_time("未定") == (None, None)


def test_extract_time_prefix_text():
    assert _extract_time("花火打ち上げ20:20～20:50") == ("20:20", "20:50")


# ---------------------------------------------------------------------------
# _split_paid_seating
# ---------------------------------------------------------------------------

def test_split_paid_seating_ari_with_details():
    flag, details = _split_paid_seating("あり自由席4400円、VIP席1万円")
    assert flag == "あり"
    assert details == "自由席4400円、VIP席1万円"


def test_split_paid_seating_nashi():
    flag, details = _split_paid_seating("なし")
    assert flag == "なし"
    assert details is None


def test_split_paid_seating_ari_no_details():
    flag, details = _split_paid_seating("あり")
    assert flag == "あり"
    assert details is None


def test_split_paid_seating_unknown():
    flag, details = _split_paid_seating("非公開")
    assert flag == "非公開"
    assert details is None


# ---------------------------------------------------------------------------
# _parse_slash_dates
# ---------------------------------------------------------------------------

def test_parse_slash_dates_simple_list():
    result = _parse_slash_dates("2026年4/4・5・11・27、5/16・30、6/13")
    assert result == [
        "2026/04/04", "2026/04/05", "2026/04/11", "2026/04/27",
        "2026/05/16", "2026/05/30",
        "2026/06/13",
    ]


def test_parse_slash_dates_range():
    result = _parse_slash_dates("2026年9/19～22")
    assert result == ["2026/09/19", "2026/09/20", "2026/09/21", "2026/09/22"]


def test_parse_slash_dates_multi_year():
    result = _parse_slash_dates("2026年11/21・22、2027年3/20・21")
    assert "2026/11/21" in result
    assert "2026/11/22" in result
    assert "2027/03/20" in result
    assert "2027/03/21" in result


def test_parse_slash_dates_with_weekday_markers():
    result = _parse_slash_dates("2026年5/30(土)、6/27(土)・7/18(土)・19(日)")
    assert "2026/05/30" in result
    assert "2026/06/27" in result
    assert "2026/07/18" in result
    assert "2026/07/19" in result


def test_parse_slash_dates_no_false_capture_on_two_digit_month():
    # '、10/10' ne doit pas capturer '1' comme jour du mois précédent
    result = _parse_slash_dates("2026年8/1・29、10/10・11")
    assert "2026/08/01" in result
    assert "2026/08/29" in result
    assert "2026/10/10" in result
    assert "2026/10/11" in result
    assert "2026/08/10" not in result  # '1' de '10' ne doit pas être capturé


# ---------------------------------------------------------------------------
# _extract_dates
# ---------------------------------------------------------------------------

def test_extract_dates_single():
    assert _extract_dates("2026年5月23日(土)") == ["2026/05/23"]


def test_extract_dates_with_trailing_text():
    assert _extract_dates("2026年5月17日(日)横田基地フェスティバルは16日(土)、17日(日)") == [
        "2026/05/16", "2026/05/17"
    ]


def test_extract_dates_dot_list():
    result = _extract_dates("2026年7月25日(土)まつりは7月25日(土)・26日(日)")
    assert result == ["2026/07/25", "2026/07/26"]


def test_extract_dates_range():
    result = _extract_dates("2026年8月1日(土)～17日(月)")
    assert result[0] == "2026/08/01"
    assert result[-1] == "2026/08/17"
    assert len(result) == 17


def test_extract_dates_slash_format_dispatches():
    result = _extract_dates("2026年4/4・5・11")
    assert result == ["2026/04/04", "2026/04/05", "2026/04/11"]


def test_extract_dates_holiday_marker():
    assert _extract_dates("2026年8月11日(祝)") == ["2026/08/11"]


def test_extract_dates_no_date_fallback():
    assert _extract_dates("未定") == []


def test_extract_dates_natural_language_unparseable():
    assert _extract_dates("春頃開催予定") == []


# ---------------------------------------------------------------------------
# HanabiWalker.parse_coordinates
# ---------------------------------------------------------------------------

def test_parse_coordinates(hw):
    soup = make_soup("""
    <div class="map_canvas">
        <iframe src="https://www.google.com/maps/embed/v1/place?key=XXX&q=36.439054,140.012547&center=36.439054,140.012547"></iframe>
    </div>
    """)
    lat, lng = hw.parse_coordinates(soup)
    assert lat == 36.439054
    assert lng == 140.012547


def test_parse_coordinates_no_map_canvas(hw):
    soup = make_soup("<div></div>")
    assert hw.parse_coordinates(soup) == (None, None)


def test_parse_coordinates_no_iframe(hw):
    soup = make_soup('<div class="map_canvas"></div>')
    assert hw.parse_coordinates(soup) == (None, None)


def test_parse_coordinates_no_q_param(hw):
    soup = make_soup("""
    <div class="map_canvas">
        <iframe src="https://www.google.com/maps/embed/v1/place?key=XXX"></iframe>
    </div>
    """)
    assert hw.parse_coordinates(soup) == (None, None)


# ---------------------------------------------------------------------------
# HanabiWalker.parse_event_table
# ---------------------------------------------------------------------------

def _make_table_html(rows: dict) -> str:
    """Construit une <table class='s_table'> à partir d'un dict {th: td_html}."""
    rows_html = "".join(
        f"<tr><th>{th}</th><td>{td}</td></tr>" for th, td in rows.items()
    )
    return f"<table class='s_table'>{rows_html}</table>"


def test_parse_event_table_basic_fields(hw):
    soup = make_soup(_make_table_html({
        "大会名": "第54回 真岡市夏祭大花火大会",
        "打ち上げ数": "約1万5000発",
        "会場": "真岡市役所東側五行川沿い",
    }))
    result = hw.parse_event_table(soup)
    assert result["title"] == "第54回 真岡市夏祭大花火大会"
    assert result["fireworks_count"] == "約1万5000発"
    assert result["venue"] == "真岡市役所東側五行川沿い"


def test_parse_event_table_date_returns_list(hw):
    soup = make_soup(_make_table_html({"開催期間": "2026年7月25日(土)"}))
    result = hw.parse_event_table(soup)
    assert result["dates"] == ["2026/07/25"]


def test_parse_event_table_time_split(hw):
    soup = make_soup(_make_table_html({"開催時間": "19:30～21:00(予定)開場16:00"}))
    result = hw.parse_event_table(soup)
    assert result["start_time"] == "19:30"
    assert result["end_time"] == "21:00"


def test_parse_event_table_paid_seating_split(hw):
    soup = make_soup(_make_table_html({"有料席": "あり自由席4400円"}))
    result = hw.parse_event_table(soup)
    assert result["paid_seating"] == "あり"
    assert result["paid_seating_details"] == "自由席4400円"


def test_parse_event_table_link_fields(hw):
    soup = make_soup(_make_table_html({
        "公式サイト": '<a href="https://example.com/">公式サイトはこちら</a>',
        "公式X": '<a href="https://x.com/example">公式Xはこちら</a>',
    }))
    result = hw.parse_event_table(soup)
    assert result["official_site"] == "https://example.com/"
    assert result["official_x"] == "https://x.com/example"


def test_parse_event_table_link_field_absent(hw):
    soup = make_soup(_make_table_html({"公式サイト": "なし"}))
    result = hw.parse_event_table(soup)
    assert result["official_site"] is None


def test_parse_event_table_access_strips_map_link(hw):
    soup = make_soup(_make_table_html({
        "会場アクセス": '【電車】最寄り駅から徒歩10分<a href="/map">MAP</a>',
    }))
    result = hw.parse_event_table(soup)
    assert "MAP" not in result["access"]
    assert "徒歩10分" in result["access"]


def test_parse_event_table_ignores_unknown_keys(hw):
    soup = make_soup(_make_table_html({"未知のフィールド": "値"}))
    result = hw.parse_event_table(soup)
    assert result == {}


# ---------------------------------------------------------------------------
# HanabiWalker.get_event_links
# ---------------------------------------------------------------------------

def _mock_response(html: str, status: int = 200) -> MagicMock:
    r = MagicMock()
    r.status_code = status
    r.content = html.encode()
    r.raise_for_status = MagicMock()
    return r


def test_get_event_links_collects_and_deduplicates(hw):
    page1 = _mock_response("""
        <a href="/detail/ar0300e001/">A</a>
        <a href="/detail/ar0300e002/">B</a>
        <a href="/detail/ar0300e001/">A</a>
    """)
    page2 = _mock_response('<a href="/other/">X</a>')  # ≤1 lien /detail/ → stop

    hw.session.get = MagicMock(side_effect=[page1, page2])
    links = hw.get_event_links()

    assert links == ["/detail/ar0300e001/", "/detail/ar0300e002/"]


def test_get_event_links_stops_on_404(hw):
    page1 = _mock_response("""
        <a href="/detail/ar0300e001/">A</a>
        <a href="/detail/ar0300e002/">B</a>
    """)
    page2 = _mock_response("", status=404)

    hw.session.get = MagicMock(side_effect=[page1, page2])
    links = hw.get_event_links()

    assert len(links) == 2


# ---------------------------------------------------------------------------
# HanabiWalker.scrape_event
# ---------------------------------------------------------------------------

def test_scrape_event(hw):
    data_html = _make_table_html({
        "大会名": "花火大会",
        "開催期間": "2026年8月1日(土)",
        "開催時間": "19:30～20:30",
        "会場": "海浜公園",
        "有料席": "なし",
    })
    map_html = """
    <div class="map_canvas">
        <iframe src="https://www.google.com/maps/embed/v1/place?key=X&q=35.6,139.7"></iframe>
    </div>
    """

    hw.get_data_page = MagicMock(return_value=make_soup(data_html))
    hw.get_map_page = MagicMock(return_value=make_soup(map_html))

    event = hw.scrape_event("/detail/ar0300e001/")

    assert event["title"] == "花火大会"
    assert event["dates"] == ["2026/08/01"]
    assert event["start_time"] == "19:30"
    assert event["end_time"] == "20:30"
    assert event["lat"] == 35.6
    assert event["lng"] == 139.7
    assert event["url"] == "https://hanabi.walkerplus.com/detail/ar0300e001/"


# ---------------------------------------------------------------------------
# HanabiWalker.scrape_all
# ---------------------------------------------------------------------------

def test_scrape_all_explodes_multiday(hw):
    hw.get_event_links = MagicMock(return_value=["/detail/ar0300e001/"])
    hw.scrape_event = MagicMock(return_value={
        "title": "花火大会",
        "dates": ["2026/08/01", "2026/08/02"],
        "venue": "海浜公園",
    })

    events, counts = hw.scrape_all()

    assert len(events) == 2
    assert events[0]["date"] == "2026/08/01"
    assert events[1]["date"] == "2026/08/02"
    assert "dates" not in events[0]
    assert counts["links_seen"] == 1
    assert counts["events_ok"] == 2  # 2 date-exploded rows


def test_scrape_all_skips_errors(hw):
    hw.get_event_links = MagicMock(return_value=["/detail/ok/", "/detail/bad/"])
    hw.scrape_event = MagicMock(side_effect=[
        {"title": "OK", "dates": ["2026/08/01"]},
        RuntimeError("timeout"),
    ])

    events, counts = hw.scrape_all()

    assert len(events) == 1
    assert events[0]["title"] == "OK"
    assert counts["links_seen"] == 2
    assert len(counts["errors"]) == 1
    assert counts["errors"][0]["url"] == "/detail/bad/"


def test_scrape_all_skips_unparseable_dates(hw):
    hw.get_event_links = MagicMock(return_value=["/detail/ar0300e001/"])
    hw.scrape_event = MagicMock(return_value={
        "title": "花火大会",
        "dates": [],  # _extract_dates retourne [] pour "未定" après le fix BUG-004
        "venue": "海浜公園",
    })

    events, counts = hw.scrape_all()

    assert len(events) == 0
    assert counts["events_skipped"] == 1
    assert counts["links_seen"] == 1


# ---------------------------------------------------------------------------
# Tests basés sur fixtures HTML (TEST-004)
# ---------------------------------------------------------------------------

import os

FIXTURES_DIR = os.path.join(os.path.dirname(__file__), "fixtures")


def _load_fixture(name: str) -> BeautifulSoup:
    with open(os.path.join(FIXTURES_DIR, name), encoding="utf-8") as f:
        return BeautifulSoup(f.read(), "html.parser")


def test_get_event_links_from_fixture(hw):
    soup = _load_fixture("hanabi_listing.html")
    # Simuler la réponse HTTP avec le contenu de la fixture
    with open(os.path.join(FIXTURES_DIR, "hanabi_listing.html"), "rb") as f:
        content = f.read()

    page1 = MagicMock()
    page1.content = content
    page1.raise_for_status = MagicMock()
    page1.status_code = 200

    page2 = MagicMock()
    page2.raise_for_status.side_effect = Exception("404")
    page2.status_code = 404

    from requests import HTTPError
    http_err = HTTPError(response=MagicMock(status_code=404))
    page2.raise_for_status.side_effect = http_err

    hw.session.get = MagicMock(side_effect=[page1, http_err])

    with patch("scrapers.hanabi_walker._fetch", side_effect=[page1, http_err]):
        links = hw.get_event_links()

    assert "/detail/ar0300e001/" in links
    assert "/detail/ar0300e002/" in links
    assert "/detail/ar0300e003/" in links
    assert len(links) == 3


def test_parse_event_table_from_fixture(hw):
    soup = _load_fixture("hanabi_event_data.html")
    result = hw.parse_event_table(soup)

    assert result["title"] == "第54回 真岡市夏祭大花火大会"
    assert result["dates"] == ["2026/08/01"]
    assert result["start_time"] == "19:30"
    assert result["end_time"] == "21:00"
    assert result["fireworks_count"] == "約1万5000発"
    assert result["venue"] == "真岡市役所東側五行川沿い"
    assert result["paid_seating"] == "あり"
    assert result["paid_seating_details"] == "自由席4400円、VIP席1万円"
    assert result["official_site"] == "https://www.moka-kanko.jp/"
    assert "MAP" not in result["access"]
    assert "徒歩15分" in result["access"]


def test_parse_coordinates_from_fixture(hw):
    soup = _load_fixture("hanabi_event_map.html")
    lat, lng = hw.parse_coordinates(soup)

    assert lat == pytest.approx(36.439054)
    assert lng == pytest.approx(140.012547)
