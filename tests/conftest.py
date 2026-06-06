"""Configuration globale pytest — EventMaps.

Règles appliquées automatiquement à chaque session/test :
- Aucun appel HTTP live via requests (POLICY.md §2 Tests réseau live)
- Chaque fixture HTML doit être déclarée dans MANIFEST.yml (POLICY.md §4)
"""

from __future__ import annotations

import unittest.mock
from pathlib import Path

import pytest
import requests
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "MANIFEST.yml"
VALID_CATEGORIES = {"real", "synthetic"}
REQUIRED_KEYS = {"file", "category", "source", "captured_at", "url", "purpose"}


# ── Blocage réseau — installé à l'import du module ───────────────────────────
# Protège la phase de collection, les fixtures session/module-scoped et chaque
# test sans exception (contrairement à une fixture function-scoped).


def _network_blocked(self: object, *args: object, **kwargs: object) -> None:  # type: ignore[override]
    raise RuntimeError(
        "Appel réseau live interdit pendant les tests (POLICY.md §2). "
        "Utiliser des fixtures HTML statiques dans tests/fixtures/ "
        "et mocker les appels HTTP (unittest.mock ou monkeypatch)."
    )


_network_patcher = unittest.mock.patch.object(requests.Session, "send", _network_blocked)
_network_patcher.start()


# ── Conformité du manifeste ───────────────────────────────────────────────────


def pytest_sessionstart(session: pytest.Session) -> None:
    """Vérifie la conformité de MANIFEST.yml à chaque session pytest."""
    if not MANIFEST_PATH.exists():
        pytest.fail(
            f"{MANIFEST_PATH} manquant — voir tests/fixtures/POLICY.md",
            pytrace=False,
        )

    with MANIFEST_PATH.open(encoding="utf-8") as f:
        manifest = yaml.safe_load(f)

    entries = manifest.get("fixtures", []) or []

    # Détecter les entrées dupliquées
    files_list = [entry.get("file", "") for entry in entries]
    duplicates = {f for f in files_list if files_list.count(f) > 1}
    if duplicates:
        pytest.fail(
            f"MANIFEST.yml contient des déclarations dupliquées : {sorted(duplicates)}\n"
            "Chaque fixture ne doit apparaître qu'une seule fois.",
            pytrace=False,
        )

    for entry in entries:
        filename = entry.get("file", "<unknown>")

        # Vérifier les champs requis
        missing = REQUIRED_KEYS - entry.keys()
        if missing:
            pytest.fail(
                f"MANIFEST.yml : entrée '{filename}' manque les champs requis : {sorted(missing)}\n"
                "Champs attendus : file, category, source, captured_at, url, purpose.",
                pytrace=False,
            )

        # Vérifier la catégorie
        cat = entry.get("category")
        if cat not in VALID_CATEGORIES:
            pytest.fail(
                f"MANIFEST.yml : entrée '{filename}' a une catégorie invalide '{cat}'. "
                f"Valeurs autorisées : {sorted(VALID_CATEGORIES)}",
                pytrace=False,
            )

        # Contraintes par catégorie
        if cat == "real" and not entry.get("captured_at"):
            pytest.fail(
                f"MANIFEST.yml : fixture réelle '{filename}' doit avoir 'captured_at' "
                "au format ISO 8601 (YYYY-MM-DD).",
                pytrace=False,
            )

    # Comparaison bidirectionnelle : glob récursif pour couvrir les sous-répertoires futurs
    declared = {entry["file"] for entry in entries}
    on_disk = {
        str(p.relative_to(FIXTURES_DIR)).replace("\\", "/") for p in FIXTURES_DIR.rglob("*.html")
    }

    undeclared = on_disk - declared
    if undeclared:
        pytest.fail(
            f"Fixtures HTML non déclarées dans MANIFEST.yml : {sorted(undeclared)}\n"
            "Ajouter une entrée dans tests/fixtures/MANIFEST.yml (voir POLICY.md).",
            pytrace=False,
        )

    orphaned = declared - on_disk
    if orphaned:
        pytest.fail(
            f"MANIFEST.yml contient des entrées sans fichier correspondant : {sorted(orphaned)}\n"
            "Supprimer l'entrée ou restaurer le fichier HTML manquant.",
            pytrace=False,
        )
