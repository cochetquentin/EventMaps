"""Configuration globale pytest — EventMaps.

Règles appliquées automatiquement à chaque session/test :
- Aucun appel réseau live (blocage socket + requests) — POLICY.md §2
- Chaque fixture HTML doit être déclarée dans MANIFEST.yml — POLICY.md §4
"""

from __future__ import annotations

import re
import socket as _socket_module
import unittest.mock
import urllib.parse
from datetime import date
from pathlib import Path

import pytest
import requests
import yaml

FIXTURES_DIR = Path(__file__).parent / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "MANIFEST.yml"
VALID_CATEGORIES = {"real", "synthetic"}
REQUIRED_KEYS = {"file", "category", "source", "captured_at", "url", "purpose"}
_DATE_RE = re.compile(r"\d{4}-(?:0[1-9]|1[0-2])-(?:0[1-9]|[12]\d|3[01])")

_ERROR_MSG = (
    "Connexion réseau live interdite pendant les tests (POLICY.md §2). "
    "Utiliser des fixtures HTML statiques dans tests/fixtures/ "
    "et mocker les appels HTTP (unittest.mock ou monkeypatch)."
)

# ── Blocage réseau — installé à l'import du module ───────────────────────────
# Protège la phase de collection, les fixtures session/module-scoped et chaque
# test sans exception (contrairement à une fixture function-scoped).
#
# Deux niveaux de blocage (belt-and-suspenders) :
# 1. socket.socket.connect — bloque tous les clients HTTP (requests, httpx, etc.)
#    Les connexions loopback (127.x, ::1) sont autorisées pour asyncio et le
#    TestClient ASGI de starlette (socketpair interne sur Windows).
# 2. requests.Session.send — défense en profondeur spécifique à requests.

_original_connect = _socket_module.socket.connect


def _no_external_connect(self: _socket_module.socket, address: object) -> None:
    host = address[0] if isinstance(address, tuple) else str(address)
    if host in ("127.0.0.1", "::1", "localhost"):
        return _original_connect(self, address)
    raise RuntimeError(_ERROR_MSG)


_socket_module.socket.connect = _no_external_connect  # type: ignore[method-assign]

_requests_patcher = unittest.mock.patch.object(
    requests.Session, "send", side_effect=RuntimeError(_ERROR_MSG)
)
_requests_patcher.start()


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

        # Vérifier les valeurs non-nulles obligatoires pour tous
        for field in ("source", "purpose"):
            if not entry.get(field):
                pytest.fail(
                    f"MANIFEST.yml : entrée '{filename}' a le champ '{field}' vide ou null. "
                    "Ce champ est obligatoire pour toutes les catégories.",
                    pytrace=False,
                )

        # Contraintes par catégorie
        if cat == "real":
            captured_at = entry.get("captured_at")
            if not captured_at:
                pytest.fail(
                    f"MANIFEST.yml : fixture réelle '{filename}' doit avoir 'captured_at' "
                    "au format YYYY-MM-DD.",
                    pytrace=False,
                )
            if not _DATE_RE.fullmatch(str(captured_at)):
                pytest.fail(
                    f"MANIFEST.yml : fixture réelle '{filename}' — 'captured_at' doit "
                    f"respecter le format YYYY-MM-DD (valeur : '{captured_at}').",
                    pytrace=False,
                )
            try:
                date.fromisoformat(str(captured_at))
            except ValueError:
                pytest.fail(
                    f"MANIFEST.yml : fixture réelle '{filename}' — 'captured_at' "
                    f"'{captured_at}' n'est pas une date calendaire valide.",
                    pytrace=False,
                )
            url = entry.get("url")
            if not url:
                pytest.fail(
                    f"MANIFEST.yml : fixture réelle '{filename}' doit avoir 'url' non-null "
                    "(URL canonique de la page capturée).",
                    pytrace=False,
                )
            parsed = urllib.parse.urlparse(str(url))
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                pytest.fail(
                    f"MANIFEST.yml : fixture réelle '{filename}' — 'url' doit être une URL "
                    f"HTTP(S) absolue valide (valeur : '{url}').",
                    pytrace=False,
                )

        elif cat == "synthetic":
            if entry.get("url") is not None:
                pytest.fail(
                    f"MANIFEST.yml : fixture synthétique '{filename}' doit avoir 'url: null' "
                    "(les synthétiques ne proviennent pas d'une page réelle).",
                    pytrace=False,
                )
            if entry.get("captured_at") is not None:
                pytest.fail(
                    f"MANIFEST.yml : fixture synthétique '{filename}' doit avoir "
                    "'captured_at: null' (pas de date de capture pour les synthétiques).",
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
