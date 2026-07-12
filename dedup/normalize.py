"""Normalisation pure des champs d'un événement pour le matching de doublons.

Aucune I/O. Tout est déterministe et sans effet de bord — chaque fonction est
directement testable en isolation.
"""

from __future__ import annotations

import math
import re
import unicodedata
from datetime import date

from models.event import Event

_PUNCT_RE = re.compile(r"[^\w\s]", flags=re.UNICODE)
_WS_RE = re.compile(r"\s+", flags=re.UNICODE)
# Suffixe d'occurrence daté /YYYYMMDD(/) — convention Tokyo Cheapo qui publie
# une page distincte par date pour un même événement (même slug).
_DATE_SUFFIX_RE = re.compile(r"/\d{8}/?$")


def normalize_text(text: str | None) -> str:
    """Normaliser un texte pour la comparaison floue.

    casefold (minuscule agressive) → décomposition NFKD → suppression des
    accents/diacritiques → ponctuation remplacée par des espaces → espaces
    compressés. Les caractères non-latins (ex. japonais) sont préservés.

    >>> normalize_text("  Sumida  RIVER Fireworks!! (2026) ")
    'sumida river fireworks 2026'
    >>> normalize_text("Fête de la Bière")
    'fete de la biere'
    """
    if not text:
        return ""
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    without_accents = "".join(ch for ch in decomposed if not unicodedata.combining(ch))
    no_punct = _PUNCT_RE.sub(" ", without_accents)
    return _WS_RE.sub(" ", no_punct).strip()


def canonical_url(event: Event) -> str:
    """Renvoyer l'URL de l'événement débarrassée de son suffixe d'occurrence daté.

    Deux pages ``/events/{slug}/`` et ``/events/{slug}/20260613/`` du même site
    désignent le même événement (dates d'occurrence différentes) → même URL
    canonique. Le slash final est normalisé pour que la base et une variante
    datée coïncident.

    >>> # .../geisha-ozashiki-odori-asakusa/  et  .../geisha-.../20260613/
    >>> # donnent tous deux  .../geisha-ozashiki-odori-asakusa
    """
    url = (event.url or "").strip()
    url = _DATE_SUFFIX_RE.sub("", url)
    return url.rstrip("/")


def event_venue(event: Event) -> str | None:
    """Renvoyer le nom de lieu d'un événement, quelle que soit sa source.

    Le lieu est éclaté selon la source : ``venue`` (top-level, Hanabi),
    ``attributes.location_name`` (Tokyo Cheapo), ``attributes.venue_name``
    (Time Out Tokyo). On prend le premier non vide.
    """
    candidates = (
        event.venue,
        getattr(event.attributes, "location_name", None),
        getattr(event.attributes, "venue_name", None),
    )
    for candidate in candidates:
        if candidate and candidate.strip():
            return candidate.strip()
    return None


def event_coords(event: Event) -> tuple[float, float] | None:
    """Renvoyer ``(latitude, longitude)`` si les deux sont présentes, sinon None.

    Time Out Tokyo n'a jamais de coordonnées → renvoie toujours None pour cette
    source, ce qui bascule le matching sur le nom de lieu.
    """
    if event.latitude is None or event.longitude is None:
        return None
    return (event.latitude, event.longitude)


def event_date_range(event: Event) -> tuple[date, date] | None:
    """Renvoyer ``(start, end)`` avec ``end = end_date or start_date``.

    Renvoie None si l'événement n'a pas de ``start_date`` : sans date, on ne
    peut pas confirmer la compatibilité temporelle, donc on refuse de fusionner.
    """
    if event.start_date is None:
        return None
    end = event.end_date if event.end_date is not None else event.start_date
    # Garde-fou : une plage inversée (end < start) est ramenée à un point.
    if end < event.start_date:
        end = event.start_date
    return (event.start_date, end)


def dates_compatible(a: Event, b: Event) -> bool:
    """True si les plages de dates des deux événements se chevauchent.

    Exige que les DEUX aient une date. Deux occurrences du même titre à des
    dates disjointes (événement récurrent) ne sont PAS compatibles.
    """
    range_a = event_date_range(a)
    range_b = event_date_range(b)
    if range_a is None or range_b is None:
        return False
    (a_start, a_end), (b_start, b_end) = range_a, range_b
    return a_start <= b_end and b_start <= a_end


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Distance en kilomètres entre deux points géographiques (formule haversine).

    Portage Python de ``frontend/js/utils.js::haversineKm`` (rayon 6371 km).
    """
    radius_km = 6371.0
    d_lat = math.radians(lat2 - lat1)
    d_lon = math.radians(lon2 - lon1)
    a = (
        math.sin(d_lat / 2) ** 2
        + math.cos(math.radians(lat1)) * math.cos(math.radians(lat2)) * math.sin(d_lon / 2) ** 2
    )
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
