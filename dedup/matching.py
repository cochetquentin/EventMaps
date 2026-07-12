"""Décision de doublon entre deux événements — logique ET conservatrice.

Deux événements sont déclarés doublons SEULEMENT si les trois portes passent :

1. Dates compatibles (chevauchement des plages) — cf. décision produit.
2. Titre très proche (``token_set_ratio`` >= ``TITLE_MIN_RATIO``).
3. Lieu confirmé, par AU MOINS un des deux canaux :
   - géographique : coordonnées présentes des deux côtés ET distance
     <= ``GEO_MAX_KM`` ;
   - textuel : noms de lieu présents des deux côtés ET similarité
     >= ``VENUE_MIN_RATIO`` (couvre Time Out Tokyo qui n'a pas de GPS).

Toute donnée manquante fait échouer sa porte → pas de fusion. On préfère
laisser passer un doublon que de fusionner deux événements distincts.
"""

from __future__ import annotations

from dataclasses import dataclass

from rapidfuzz import fuzz

from dedup.normalize import (
    dates_compatible,
    event_coords,
    event_venue,
    haversine_km,
    normalize_text,
)
from models.event import Event

# Seuils centralisés — réglables et couverts par les tests.
TITLE_MIN_RATIO = 90.0
"""Similarité minimale des titres normalisés (0-100) pour un doublon."""

GEO_MAX_KM = 0.75
"""Distance maximale (km) entre coordonnées pour confirmer un même lieu."""

VENUE_MIN_RATIO = 88.0
"""Similarité minimale des noms de lieu normalisés (0-100) pour confirmer un même lieu."""


@dataclass(frozen=True)
class PairVerdict:
    """Résultat détaillé d'une comparaison de paire — traçable et loggable."""

    is_duplicate: bool
    dates_compatible: bool
    title_score: float
    geo_km: float | None
    venue_score: float | None
    location_confirmed: bool
    reasons: tuple[str, ...]


def _title_similarity(a: Event, b: Event) -> float:
    norm_a = normalize_text(a.title)
    norm_b = normalize_text(b.title)
    if not norm_a or not norm_b:
        return 0.0
    return float(fuzz.token_set_ratio(norm_a, norm_b))


def _geo_distance_km(a: Event, b: Event) -> float | None:
    coords_a = event_coords(a)
    coords_b = event_coords(b)
    if coords_a is None or coords_b is None:
        return None
    return haversine_km(coords_a[0], coords_a[1], coords_b[0], coords_b[1])


def _venue_similarity(a: Event, b: Event) -> float | None:
    norm_a = normalize_text(event_venue(a))
    norm_b = normalize_text(event_venue(b))
    if not norm_a or not norm_b:
        return None
    return float(fuzz.token_set_ratio(norm_a, norm_b))


def classify_pair(a: Event, b: Event) -> PairVerdict:
    """Évaluer si ``a`` et ``b`` sont des doublons et renvoyer le détail."""
    reasons: list[str] = []

    date_ok = dates_compatible(a, b)
    if not date_ok:
        reasons.append("dates incompatibles ou manquantes")

    title_score = _title_similarity(a, b)
    title_ok = title_score >= TITLE_MIN_RATIO
    if not title_ok:
        reasons.append(f"titres trop différents ({title_score:.0f} < {TITLE_MIN_RATIO:.0f})")

    geo_km = _geo_distance_km(a, b)
    geo_ok = geo_km is not None and geo_km <= GEO_MAX_KM

    venue_score = _venue_similarity(a, b)
    venue_ok = venue_score is not None and venue_score >= VENUE_MIN_RATIO

    location_confirmed = geo_ok or venue_ok
    if not location_confirmed:
        reasons.append("lieu non confirmé (ni géo proche, ni nom de lieu concordant)")

    is_dup = date_ok and title_ok and location_confirmed
    if is_dup:
        channel = "géo" if geo_ok else "lieu"
        reasons.append(f"doublon confirmé (titre {title_score:.0f}, {channel})")

    return PairVerdict(
        is_duplicate=is_dup,
        dates_compatible=date_ok,
        title_score=title_score,
        geo_km=geo_km,
        venue_score=venue_score,
        location_confirmed=location_confirmed,
        reasons=tuple(reasons),
    )


def is_duplicate(a: Event, b: Event) -> bool:
    """Raccourci booléen de :func:`classify_pair`."""
    return classify_pair(a, b).is_duplicate
