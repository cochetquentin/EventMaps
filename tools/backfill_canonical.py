"""Backfill des ``canonical_id`` sur une base d'événements existante.

Recalcule les clusters de doublons et écrit la colonne ``canonical_id`` sans
supprimer ni modifier aucun autre champ. Idempotent : relançable sans risque.

Usage :
    uv run python -m tools.backfill_canonical [--db PATH] [--all]

  --all   Traiter aussi les événements passés (par défaut : seulement à venir).
"""

from __future__ import annotations

import argparse
import logging

from config import settings
from db.store import EventStore

logger = logging.getLogger(__name__)


def backfill(db_path: str, upcoming_only: bool = True) -> dict[str, str]:
    """Recalculer les canonical_id sur ``db_path``. Renvoie le mapping complet."""
    with EventStore(db_path) as store:
        mapping = store.recompute_canonical(upcoming_only=upcoming_only)
    clusters = len(set(mapping.values()))
    merged = len(mapping) - clusters
    logger.info(
        "Backfill terminé sur %s : %d événements, %d clusters, %d doublons regroupés",
        db_path,
        len(mapping),
        clusters,
        merged,
    )
    return mapping


def main() -> None:
    parser = argparse.ArgumentParser(description="Backfill canonical_id (déduplication)")
    parser.add_argument("--db", default=settings.db_path, metavar="PATH")
    parser.add_argument(
        "--all",
        action="store_true",
        help="Inclure les événements passés (par défaut : seulement à venir)",
    )
    args = parser.parse_args()
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s — %(message)s"
    )
    backfill(args.db, upcoming_only=not args.all)


if __name__ == "__main__":
    main()
