"""Tests des normalisations pures utilisées par la déduplication."""

from datetime import UTC, date, datetime

import pytest

from dedup.normalize import (
    dates_compatible,
    event_coords,
    event_date_range,
    event_venue,
    haversine_km,
    normalize_text,
)
from models.event import Event
from models.identity import make_event_id


def mk(source="tc", **over) -> Event:
    """Fabrique minimale d'Event, tous champs surchargables via kwargs."""
    url = over.pop("url", f"https://{source}.example/x")
    title = over.pop("title", "Event")
    base = dict(
        id=over.pop("id", None) or make_event_id([url, title, source]),
        source=source,
        title=title,
        url=url,
        start_date=None,
        end_date=None,
        times=None,
        venue=None,
        latitude=None,
        longitude=None,
        price=None,
        attributes=over.pop("attributes", {}),
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    base.update(over)
    return Event(**base)


# --- normalize_text ---


@pytest.mark.parametrize(
    "raw,expected",
    [
        ("  Sumida  RIVER Fireworks!! (2026) ", "sumida river fireworks 2026"),
        ("Fête de la Bière", "fete de la biere"),
        ("Café—Concert: Jazz & Blues", "cafe concert jazz blues"),
        ("ALL CAPS", "all caps"),
        (None, ""),
        ("", ""),
        ("   ", ""),
        ("!!!", ""),
    ],
)
def test_normalize_text(raw, expected):
    assert normalize_text(raw) == expected


def test_normalize_text_preserves_japanese():
    # Les caractères non-latins ne sont pas supprimés (pas d'accent à retirer).
    assert normalize_text("隅田川 花火") == "隅田川 花火"


def test_normalize_text_idempotent():
    once = normalize_text("Fête—Été 2026!")
    assert normalize_text(once) == once


# --- event_venue ---


def test_event_venue_tokyo_cheapo_uses_location_name():
    e = mk("tc", attributes={"location_name": "Yoyogi Park"})
    assert event_venue(e) == "Yoyogi Park"


def test_event_venue_hanabi_uses_top_level_venue():
    e = mk("hanabi", venue="隅田川", attributes={})
    assert event_venue(e) == "隅田川"


def test_event_venue_timeout_uses_venue_name():
    e = mk("tot", attributes={"venue_name": "Blue Note Tokyo"})
    assert event_venue(e) == "Blue Note Tokyo"


def test_event_venue_prefers_top_level_over_attributes():
    e = mk("tc", venue="Top Venue", attributes={"location_name": "Attr Venue"})
    assert event_venue(e) == "Top Venue"


def test_event_venue_none_when_all_empty():
    assert event_venue(mk("tc", venue="   ", attributes={"location_name": ""})) is None
    assert event_venue(mk("hanabi", attributes={})) is None


# --- event_coords ---


def test_event_coords_present():
    assert event_coords(mk("tc", latitude=35.6, longitude=139.7)) == (35.6, 139.7)


@pytest.mark.parametrize(
    "lat,lon",
    [(None, 139.7), (35.6, None), (None, None)],
)
def test_event_coords_missing_returns_none(lat, lon):
    assert event_coords(mk("tot", latitude=lat, longitude=lon)) is None


def test_event_coords_accepts_zero():
    # 0.0 est une coordonnée valide, ne doit pas être confondu avec None.
    assert event_coords(mk("tc", latitude=0.0, longitude=0.0)) == (0.0, 0.0)


# --- event_date_range ---


def test_event_date_range_start_only():
    assert event_date_range(mk("tc", start_date=date(2026, 7, 25))) == (
        date(2026, 7, 25),
        date(2026, 7, 25),
    )


def test_event_date_range_start_and_end():
    e = mk("tc", start_date=date(2026, 7, 25), end_date=date(2026, 7, 27))
    assert event_date_range(e) == (date(2026, 7, 25), date(2026, 7, 27))


def test_event_date_range_no_start_returns_none():
    assert event_date_range(mk("tot", start_date=None)) is None


def test_event_date_range_inverted_is_clamped():
    e = mk("tc", start_date=date(2026, 7, 25), end_date=date(2026, 7, 20))
    assert event_date_range(e) == (date(2026, 7, 25), date(2026, 7, 25))


# --- dates_compatible ---


def test_dates_compatible_same_day():
    a = mk(start_date=date(2026, 7, 25))
    b = mk(start_date=date(2026, 7, 25))
    assert dates_compatible(a, b) is True


def test_dates_compatible_overlapping_ranges():
    a = mk(start_date=date(2026, 7, 20), end_date=date(2026, 7, 26))
    b = mk(start_date=date(2026, 7, 25), end_date=date(2026, 7, 30))
    assert dates_compatible(a, b) is True


def test_dates_compatible_touching_boundary():
    a = mk(start_date=date(2026, 7, 20), end_date=date(2026, 7, 25))
    b = mk(start_date=date(2026, 7, 25), end_date=date(2026, 7, 30))
    assert dates_compatible(a, b) is True


def test_dates_incompatible_disjoint():
    a = mk(start_date=date(2026, 7, 10))
    b = mk(start_date=date(2026, 8, 14))
    assert dates_compatible(a, b) is False


def test_dates_incompatible_when_one_missing():
    a = mk(start_date=date(2026, 7, 25))
    b = mk(start_date=None)
    assert dates_compatible(a, b) is False
    assert dates_compatible(b, a) is False


# --- haversine_km ---


def test_haversine_zero_for_same_point():
    assert haversine_km(35.681, 139.767, 35.681, 139.767) == pytest.approx(0.0, abs=1e-9)


def test_haversine_symmetric():
    d1 = haversine_km(35.681, 139.767, 35.690, 139.700)
    d2 = haversine_km(35.690, 139.700, 35.681, 139.767)
    assert d1 == pytest.approx(d2, rel=1e-12)


def test_haversine_known_distance():
    # Tokyo Station (35.681,139.767) → Shinjuku Station (35.690,139.700) ≈ 6.1 km.
    d = haversine_km(35.681, 139.767, 35.690, 139.700)
    assert d == pytest.approx(6.1, abs=0.4)


def test_haversine_small_distance_sub_km():
    # ~150 m d'écart doit rester bien en dessous du kilomètre.
    d = haversine_km(35.7110, 139.8010, 35.7120, 139.8012)
    assert 0.0 < d < 0.3
