"""Configuration globale pytest — EventMaps.

Règles appliquées automatiquement à chaque session/test :
- Aucun appel HTTP live via requests (POLICY.md §2 Tests réseau live)
- Chaque fixture HTML doit être déclarée dans MANIFEST.yml (POLICY.md §4)
"""
from __future__ import annotations

from pathlib import Path

import pytest
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "MANIFEST.yml"
VALID_CATEGORIES = {"real", "synthetic"}


# ── Conformité du manifeste ───────────────────────────────────────────────────


def pytest_sessionstart(session: pytest.Session) -> None:
    """Vérifie que chaque .html de fixtures/ est déclaré dans MANIFEST.yml."""
    if not MANIFEST_PATH.exists():
        pytest.fail(
            f"{MANIFEST_PATH} manquant — voir tests/fixtures/POLICY.md",
            pytrace=False,
        )

    with MANIFEST_PATH.open(encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    entries = manifest.get("fixtures", []) or []

    # Vérifier les catégories
    for entry in entries:
        cat = entry.get("category")
        if cat not in VALID_CATEGORIES:
            pytest.fail(
                f"MANIFEST.yml : entrée '{entry.get('file')}' a une catégorie invalide "
                f"'{cat}'. Valeurs autorisées : {VALID_CATEGORIES}",
                pytrace=False,
            )

    declared = {entry["file"] for entry in entries}
    on_disk = {p.name for p in FIXTURES_DIR.glob("*.html")}

    undeclared = on_disk - declared
    if undeclared:
        pytest.fail(
            f"Fixtures HTML non déclarées dans MANIFEST.yml : {sorted(undeclared)}\n"
            "Ajouter une entrée dans tests/fixtures/MANIFEST.yml (voir POLICY.md).",
            pytrace=False,
        )


# ── Blocage réseau ────────────────────────────────────────────────────────────


@pytest.fixture(autouse=True)
def no_live_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Bloque les appels HTTP live via requests pendant chaque test.

    Patche requests.Session.send (couche inférieure commune à get/post/etc.)
    pour lever une RuntimeError explicite si un test tente un appel réseau réel.
    Les tests existants mockent déjà session.get — ce blocage est une filet de
    sécurité, pas un changement de comportement pour les tests bien écrits.
    """
    import requests

    def _blocked(self: object, *args: object, **kwargs: object) -> None:
        raise RuntimeError(
            "Appel réseau live interdit pendant les tests (POLICY.md §2). "
            "Utiliser des fixtures HTML statiques dans tests/fixtures/ "
            "et mocker les appels HTTP (unittest.mock ou monkeypatch)."
        )

    monkeypatch.setattr(requests.Session, "send", _blocked)
