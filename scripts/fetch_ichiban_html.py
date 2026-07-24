"""Collecte du HTML brut des pages « événements » d'ichiban-japan.com.

Ce n'est PAS un scraper : aucun parsing, aucune extraction. On télécharge les pages
telles quelles pour accumuler de la matière brute et concevoir, plus tard, un scraper
robuste de ce site.

Usage :
    uv run python scripts/fetch_ichiban_html.py

Les fichiers sont écrits dans data/html/ichiban-japan/<slug>.html (data/ est gitignoré).
Le script est idempotent : un slug déjà téléchargé est sauté, ce qui permet de le
relancer au fil des mois sans re-télécharger l'existant.
"""

from __future__ import annotations

import logging
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(message)s")
logger = logging.getLogger("fetch_ichiban")

BASE_URL = "https://ichiban-japan.com"
OUTPUT_DIR = Path("data/html/ichiban-japan")

# Slugs de mois SANS accent : WordPress retire les accents des slugs
# (août -> aout, février -> fevrier, décembre -> decembre).
MONTHS = [
    "janvier",
    "fevrier",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "aout",
    "septembre",
    "octobre",
    "novembre",
    "decembre",
]
YEAR = 2026

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/125.0.0.0 Safari/537.36"
)
TIMEOUT = 15
THROTTLE_S = 1.0
MAX_ATTEMPTS = 3


def build_slugs() -> list[str]:
    """Construit la liste ordonnée des slugs à tenter.

    Ordre : festivals + expositions 2026 mois par mois, puis marchés aux puces,
    puis festivals d'été Tohoku.
    """
    slugs: list[str] = []
    for month in MONTHS:
        slugs.append(f"festivals-tokyo-{month}-{YEAR}")
        slugs.append(f"expositions-tokyo-{month}-{YEAR}")
    slugs.append("marches-aux-puces-tokyo")
    slugs.append("festivals-ete-tohoku")
    return slugs


def fetch(session: requests.Session, url: str) -> requests.Response | None:
    """Télécharge une URL avec petit retry sur erreurs transitoires (429 / 5xx).

    Retourne la réponse (y compris un 404, qui est un cas normal), ou None si toutes
    les tentatives ont échoué sur une erreur réseau/serveur.
    """
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = session.get(url, timeout=TIMEOUT)
        except requests.RequestException as exc:
            logger.warning("  réseau KO (essai %d/%d) : %s", attempt, MAX_ATTEMPTS, exc)
        else:
            if response.status_code == 429 or response.status_code >= 500:
                logger.warning(
                    "  transitoire %d (essai %d/%d)",
                    response.status_code,
                    attempt,
                    MAX_ATTEMPTS,
                )
            else:
                return response
        if attempt < MAX_ATTEMPTS:
            time.sleep(THROTTLE_S * attempt)
    return None


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    slugs = build_slugs()

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    downloaded: list[str] = []
    skipped_existing: list[str] = []
    missing: list[str] = []
    errored: list[str] = []

    logger.info("Collecte de %d slugs candidats dans %s\n", len(slugs), OUTPUT_DIR)

    for slug in slugs:
        dest = OUTPUT_DIR / f"{slug}.html"
        if dest.exists():
            logger.info("[skip] %s - déjà présent", slug)
            skipped_existing.append(slug)
            continue

        url = f"{BASE_URL}/{slug}/"
        response = fetch(session, url)

        if response is None:
            logger.error("[ERR ] %s - échec après %d tentatives", slug, MAX_ATTEMPTS)
            errored.append(slug)
        elif response.status_code == 200:
            dest.write_text(response.text, encoding="utf-8")
            size_kb = len(response.text.encode("utf-8")) / 1024
            logger.info("[ OK ] %s - %.0f Ko", slug, size_kb)
            downloaded.append(slug)
        elif response.status_code == 404:
            logger.info("[404 ] %s - absent, ignoré", slug)
            missing.append(slug)
        else:
            logger.error("[ERR ] %s - statut inattendu %d", slug, response.status_code)
            errored.append(slug)

        # Throttle uniquement après une vraie requête réseau (pas les fichiers déjà là).
        time.sleep(THROTTLE_S)

    logger.info("\n%s", "-" * 48)
    logger.info("Téléchargées   : %d", len(downloaded))
    logger.info("Déjà présentes : %d", len(skipped_existing))
    logger.info("Absentes (404) : %d", len(missing))
    logger.info("Erreurs        : %d", len(errored))
    if downloaded:
        logger.info("\nNouvellement récupérées :")
        for slug in downloaded:
            logger.info("  - %s.html", slug)


if __name__ == "__main__":
    main()
