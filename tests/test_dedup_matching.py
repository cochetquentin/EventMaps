"""Tests de la décision de doublon — l'anti-faux-positif du système.

Chaque test isole une porte (dates, titre, lieu) pour prouver qu'elle est
bien requise, et que toute donnée manquante empêche la fusion.
"""

from datetime import UTC, date, datetime

from dedup.matching import (
    GEO_MAX_KM,
    TITLE_MIN_RATIO,
    VENUE_MIN_RATIO,
    classify_pair,
    is_duplicate,
    same_source_same_event,
)
from models.event import Event
from models.identity import make_event_id


def mk(source="tc", **over) -> Event:
    url = over.pop("url", f"https://{source}.example/x")
    title = over.pop("title", "Event")
    base = dict(
        id=over.pop("id", None) or make_event_id([url, title, source]),
        source=source,
        title=title,
        url=url,
        start_date=date(2026, 7, 25),
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


# --- Cas positifs (vrais doublons) ---


def test_duplicate_via_geo_channel():
    # Titres proches, même date, coords à ~110 m → doublon confirmé par la géo.
    a = mk("hanabi", title="Sumida River Fireworks Festival", latitude=35.7110, longitude=139.8010)
    b = mk("tc", title="Sumida River Fireworks", latitude=35.7120, longitude=139.8012)
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is True
    assert verdict.geo_km is not None and verdict.geo_km <= GEO_MAX_KM


def test_duplicate_via_venue_channel_when_no_coords():
    # Time Out Tokyo n'a pas de coords : la confirmation passe par le nom de lieu.
    a = mk(
        "tc",
        title="Blue Note Jazz Night",
        latitude=35.66,
        longitude=139.71,
        attributes={"location_name": "Blue Note Tokyo"},
    )
    b = mk(
        "tot",
        title="Jazz Night at Blue Note",
        latitude=None,
        longitude=None,
        attributes={"venue_name": "Blue Note Tokyo"},
    )
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is True
    assert verdict.geo_km is None
    assert verdict.venue_score is not None and verdict.venue_score >= VENUE_MIN_RATIO


def test_duplicate_reordered_title_tokens():
    # token_set_ratio gère le réordonnancement des mots.
    a = mk("tc", title="Fireworks Festival Sumida River", latitude=35.71, longitude=139.80)
    b = mk("hanabi", title="Sumida River Fireworks Festival", latitude=35.71, longitude=139.80)
    assert is_duplicate(a, b) is True


def test_duplicate_multiday_overlap():
    a = mk(
        "tc",
        title="Design Festa",
        start_date=date(2026, 7, 20),
        end_date=date(2026, 7, 22),
        latitude=35.63,
        longitude=139.79,
    )
    b = mk(
        "tot",
        title="Design Festa",
        start_date=date(2026, 7, 22),
        end_date=date(2026, 7, 24),
        latitude=35.63,
        longitude=139.79,
    )
    assert is_duplicate(a, b) is True


# --- Cas négatifs (NE DOIT PAS fusionner) ---


def test_not_duplicate_different_dates_same_title_and_place():
    # Événement récurrent : même titre, même lieu, mais dates disjointes.
    a = mk("tc", title="Jazz Night", start_date=date(2026, 7, 10), latitude=35.66, longitude=139.71)
    b = mk(
        "tot", title="Jazz Night", start_date=date(2026, 8, 14), latitude=35.66, longitude=139.71
    )
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is False
    assert verdict.dates_compatible is False


def test_not_duplicate_far_apart():
    # Même titre/date mais 6 km d'écart et pas de nom de lieu concordant.
    a = mk("tc", title="Summer Festival", latitude=35.681, longitude=139.767)
    b = mk("hanabi", title="Summer Festival", latitude=35.690, longitude=139.700)
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is False
    assert verdict.location_confirmed is False


def test_not_duplicate_different_titles():
    a = mk("tc", title="Yoyogi Flea Market", latitude=35.671, longitude=139.694)
    b = mk("hanabi", title="Sumida River Fireworks", latitude=35.671, longitude=139.694)
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is False
    assert verdict.title_score < TITLE_MIN_RATIO


def test_not_duplicate_when_dates_missing():
    a = mk("tc", title="Mystery Event", start_date=None, latitude=35.66, longitude=139.71)
    b = mk("tc", title="Mystery Event", start_date=None, latitude=35.66, longitude=139.71)
    assert is_duplicate(a, b) is False


def test_not_duplicate_no_location_signal_at_all():
    # Titre identique, dates OK, mais aucune coord et aucun nom de lieu des deux côtés.
    a = mk("tot", title="Secret Show", latitude=None, longitude=None)
    b = mk("tot", title="Secret Show", latitude=None, longitude=None)
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is False
    assert verdict.geo_km is None
    assert verdict.venue_score is None


def test_not_duplicate_close_geo_but_empty_titles():
    a = mk("tc", title="", latitude=35.66, longitude=139.71)
    b = mk("tc", title="", latitude=35.66, longitude=139.71)
    verdict = classify_pair(a, b)
    assert verdict.title_score == 0.0
    assert verdict.is_duplicate is False


# --- same_source_same_event (identité intra-source par URL) ---

_TC_BASE = "https://tokyocheapo.com/events/geisha-ozashiki-odori-asakusa/"
_TC_DATED = "https://tokyocheapo.com/events/geisha-ozashiki-odori-asakusa/20260613/"
_ASAKUSA = "Asakusa Culture and Tourism Center"


def test_same_source_same_event_merges_dated_variants_despite_disjoint_dates():
    # Le cas réel : même page événement, deux occurrences d'un jour DISJOINTES.
    url_0704 = "https://tokyocheapo.com/events/geisha-ozashiki-odori-asakusa/20260704/"
    url_0711 = "https://tokyocheapo.com/events/geisha-ozashiki-odori-asakusa/20260711/"
    a = mk(
        "tc",
        title="Geisha Dances (Ozashiki Odori) in Asakusa",
        url=url_0704,
        start_date=date(2026, 7, 4),
        end_date=date(2026, 7, 4),
        latitude=35.710689,
        longitude=139.79659,
        attributes={"location_name": _ASAKUSA},
    )
    b = mk(
        "tc",
        title="Geisha Dances (Ozashiki Odori) in Asakusa",
        url=url_0711,
        start_date=date(2026, 7, 11),
        end_date=date(2026, 7, 11),
        latitude=35.710689,
        longitude=139.79659,
        attributes={"location_name": _ASAKUSA},
    )
    # La règle floue les rejette (dates disjointes)...
    assert is_duplicate(a, b) is False
    # ...mais l'identité intra-source les fusionne.
    assert same_source_same_event(a, b) is True


def test_same_source_same_event_requires_same_source():
    a = mk("tc", url=_TC_BASE, latitude=35.71, longitude=139.79)
    b = mk("hanabi", url=_TC_BASE, latitude=35.71, longitude=139.79)
    assert same_source_same_event(a, b) is False


def test_same_source_same_event_requires_same_canonical_url():
    a = mk("tc", url="https://tokyocheapo.com/events/slug-a/", latitude=35.71, longitude=139.79)
    b = mk("tc", url="https://tokyocheapo.com/events/slug-b/", latitude=35.71, longitude=139.79)
    assert same_source_same_event(a, b) is False


def test_same_source_same_event_requires_same_location():
    # Même URL de base mais lieux distincts (multi-lieux) → conservés séparés.
    a = mk(
        "tc",
        url=_TC_BASE,
        latitude=35.10,
        longitude=139.10,
        attributes={"location_name": "Venue A"},
    )
    b = mk(
        "tc",
        url=_TC_DATED,
        latitude=36.90,
        longitude=140.90,
        attributes={"location_name": "Venue B"},
    )
    assert same_source_same_event(a, b) is False


def test_same_source_same_event_confirmed_by_venue_without_coords():
    a = mk(
        "tc", url=_TC_BASE, latitude=None, longitude=None, attributes={"location_name": _ASAKUSA}
    )
    b = mk(
        "tc", url=_TC_DATED, latitude=None, longitude=None, attributes={"location_name": _ASAKUSA}
    )
    assert same_source_same_event(a, b) is True


# --- Traçabilité du verdict ---


def test_verdict_carries_reasons():
    a = mk("tc", title="A", latitude=35.0, longitude=139.0)
    b = mk("tc", title="B", latitude=36.0, longitude=140.0)
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is False
    assert verdict.reasons  # au moins une raison expliquant le rejet


def test_verdict_positive_reason_mentions_channel():
    a = mk("tc", title="Sumida Fireworks", latitude=35.711, longitude=139.801)
    b = mk("hanabi", title="Sumida Fireworks", latitude=35.711, longitude=139.801)
    verdict = classify_pair(a, b)
    assert verdict.is_duplicate is True
    assert any("doublon confirmé" in r for r in verdict.reasons)
