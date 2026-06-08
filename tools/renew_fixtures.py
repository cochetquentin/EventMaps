"""Script de renouvellement contrôlé des fixtures réelles.

Outil opt-in à usage exclusivement manuel — jamais exécuté en CI.
Récupère une page HTML distante et l'enregistre comme fixture dans
tests/fixtures/, avec revue du diff, détection de PII et mise à jour
du MANIFEST.yml.

Dépendances : requests (prod), PyYAML (dev), stdlib uniquement.

Usage :
    uv run python -m tools.renew_fixtures \\
        --source {tc|hanabi|tot} \\
        --url <URL> \\
        --output <chemin relatif depuis tests/fixtures/> \\
        [--user-agent "EventMaps-fixture-renewer/1.0"] \\
        [--delay 2.0] \\
        [--yes]
"""

from __future__ import annotations

import argparse
import difflib
import os
import re
import sys
import time
from datetime import date
from pathlib import Path

import requests

FIXTURES_DIR = Path(__file__).parent.parent / "tests" / "fixtures"
MANIFEST_PATH = FIXTURES_DIR / "MANIFEST.yml"
VALID_SOURCES = ("tc", "hanabi", "tot")
DEFAULT_USER_AGENT = "EventMaps-fixture-renewer/1.0"
DEFAULT_DELAY = 2.0

_PII_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("email", re.compile(r"[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}")),
    ("timeout_auth", re.compile(r'timeoutAuthClientId["\s:=]+["\']?[\w-]+')),
    ("newrelic_key", re.compile(r'newrelic_license_key["\s:=]+["\']?[\w-]+')),
    ("bearer_token", re.compile(r"Bearer\s+[A-Za-z0-9\-._~+/]+=*")),
]


# ── CLI ───────────────────────────────────────────────────────────────────────


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="renew_fixtures",
        description="Renouvelle une fixture réelle de façon contrôlée (manuel uniquement).",
    )
    parser.add_argument(
        "--source",
        required=True,
        choices=VALID_SOURCES,
        help="Source du site (tc, hanabi, tot).",
    )
    parser.add_argument(
        "--url",
        required=True,
        help="URL canonique de la page à capturer.",
    )
    parser.add_argument(
        "--output",
        required=True,
        help="Chemin de sortie relatif depuis tests/fixtures/ (ex. tot/real/listing.html).",
    )
    parser.add_argument(
        "--user-agent",
        default=DEFAULT_USER_AGENT,
        dest="user_agent",
        help=f"User-Agent HTTP (défaut : {DEFAULT_USER_AGENT!r}).",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"Délai en secondes après la requête (défaut : {DEFAULT_DELAY}).",
    )
    parser.add_argument(
        "--yes",
        action="store_true",
        help="Confirmer l'écriture sans interaction (bypass stdin).",
    )
    return parser.parse_args(argv)


# ── Garde-fous ────────────────────────────────────────────────────────────────


def check_not_ci() -> None:
    """Lève SystemExit(1) si une variable d'environnement CI est détectée."""
    ci_vars = ("CI", "GITHUB_ACTIONS", "GITLAB_CI")
    for var in ci_vars:
        value = os.environ.get(var, "")
        if value:
            print(
                f"ERREUR : variable d'environnement {var}={value!r} détectée. "
                "Ce script ne doit pas s'exécuter en CI.",
                file=sys.stderr,
            )
            raise SystemExit(1)


# ── Réseau ────────────────────────────────────────────────────────────────────


def fetch_page(url: str, user_agent: str, timeout: int = 30) -> str:
    """Récupère le contenu HTML de l'URL. Lève requests.HTTPError si status >= 400."""
    response = requests.get(
        url,
        headers={"User-Agent": user_agent},
        timeout=timeout,
    )
    response.raise_for_status()
    return response.text


# ── Diff ─────────────────────────────────────────────────────────────────────


def compute_diff(old_content: str, new_content: str, filename: str) -> str:
    """Retourne un diff unified entre old et new. Chaîne vide si contenu identique."""
    old_lines = old_content.splitlines(keepends=False)
    new_lines = new_content.splitlines(keepends=False)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
        )
    )
    return "".join(diff_lines)


def print_diff(diff: str, filename: str) -> None:
    """Affiche le diff sur stdout avec coloration ANSI si le terminal le supporte."""
    use_color = sys.stdout.isatty()
    green = "\033[32m" if use_color else ""
    red = "\033[31m" if use_color else ""
    cyan = "\033[36m" if use_color else ""
    reset = "\033[0m" if use_color else ""

    if not diff:
        print(f"  (contenu identique pour {filename})")
        return

    for line in diff.splitlines():
        if line.startswith("+++") or line.startswith("---"):
            print(f"{cyan}{line}{reset}")
        elif line.startswith("+"):
            print(f"{green}{line}{reset}")
        elif line.startswith("-"):
            print(f"{red}{line}{reset}")
        else:
            print(line)


# ── PII ──────────────────────────────────────────────────────────────────────


def scan_pii(content: str) -> list[tuple[str, str]]:
    """Retourne la liste des (type_pii, extrait_tronqué) trouvés dans le contenu."""
    hits: list[tuple[str, str]] = []
    for pii_type, pattern in _PII_PATTERNS:
        for match in pattern.finditer(content):
            excerpt = match.group()[:60]
            hits.append((pii_type, excerpt))
    return hits


# ── Écriture ─────────────────────────────────────────────────────────────────


def confirm_write(filename: str) -> bool:
    """Demande confirmation interactive. Retourne True si l'utilisateur accepte."""
    try:
        answer = input(f"Écrire {filename} ? [o/N] ").strip().lower()
    except EOFError:
        return False
    return answer in ("o", "oui")


def write_fixture(output_path: Path, content: str) -> None:
    """Écrit le contenu HTML dans output_path (crée les répertoires si nécessaire)."""
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(content, encoding="utf-8")


# ── Manifeste ────────────────────────────────────────────────────────────────


def update_manifest(
    manifest_path: Path,
    fixture_file: str,
    new_date: str,
    url: str,
    source: str,  # noqa: ARG001
) -> bool:
    """Met à jour captured_at et url pour fixture_file dans le manifeste.

    Utilise une substitution regex chirurgicale pour préserver les commentaires
    et l'indentation YAML d'origine. La regex est bornée à l'entrée sélectionnée
    (stop avant le prochain '- file:') pour éviter toute corruption des autres entrées.

    Retourne True si l'entrée a été trouvée et mise à jour, False sinon.
    """
    content = manifest_path.read_text(encoding="utf-8")

    escaped = re.escape(fixture_file)
    # (?:(?!- file:).)* : avance caractère par caractère en s'arrêtant dès que
    # la séquence '- file:' apparaît, ce qui borne la correspondance à l'entrée
    # sélectionnée et évite toute corruption des entrées suivantes.
    entry_bound = r"(?:(?!- file:).)*?"

    # Remplace captured_at (null ou "YYYY-MM-DD") dans le bloc de cette entrée
    date_pattern = re.compile(
        rf"(- file: {escaped}{entry_bound}captured_at: )(?:\"[^\"]*\"|null)",
        re.DOTALL,
    )
    new_content, n_date = date_pattern.subn(rf'\g<1>"{new_date}"', content)
    if n_date == 0:
        return False

    # Remplace url (null ou valeur existante) par l'URL canonique fournie
    url_pattern = re.compile(
        rf'(- file: {escaped}{entry_bound}url: )(?:"[^"]*"|null)',
        re.DOTALL,
    )
    new_content, _ = url_pattern.subn(rf'\g<1>"{url}"', new_content)

    manifest_path.write_text(new_content, encoding="utf-8")
    return True


# ── Orchestration ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée principal. Retourne 0=succès, 1=erreur, 2=annulé."""
    args = parse_args(argv)

    # Blocage CI
    check_not_ci()

    # Validation : l'output doit être sous {source}/real/ (fixtures réelles uniquement)
    expected_prefix = f"{args.source}/real/"
    if not args.output.startswith(expected_prefix):
        print(
            f"ERREUR : --output doit commencer par {expected_prefix!r} pour --source {args.source!r}.",
            file=sys.stderr,
        )
        return 1

    # Validation du chemin de sortie (anti path-traversal)
    output_path = FIXTURES_DIR / args.output
    try:
        output_path.resolve().relative_to(FIXTURES_DIR.resolve())
    except ValueError:
        print(
            f"ERREUR : {args.output!r} pointe en dehors de tests/fixtures/.",
            file=sys.stderr,
        )
        return 1

    print(f"→ Récupération de {args.url}")
    try:
        new_content = fetch_page(args.url, args.user_agent)
    except requests.RequestException as exc:
        print(f"ERREUR réseau : {exc}", file=sys.stderr)
        return 1

    time.sleep(args.delay)

    # Diff si le fichier existe déjà
    if output_path.exists():
        old_content = output_path.read_text(encoding="utf-8")
        diff = compute_diff(old_content, new_content, args.output)
        print(f"\n── Diff pour {args.output} ──")
        print_diff(diff, args.output)
        print()
    else:
        print(f"  (nouveau fichier : {args.output})\n")

    # Détection PII
    pii_hits = scan_pii(new_content)
    if pii_hits:
        print("⚠  PII détectées — anonymiser avant de commiter :")
        for pii_type, excerpt in pii_hits:
            print(f"   [{pii_type}] {excerpt!r}")
        print()

    # Confirmation
    if not args.yes and not confirm_write(args.output):
        print("Annulé.")
        return 2

    write_fixture(output_path, new_content)
    print(f"✓ Écrit : {output_path}")

    # Mise à jour du manifeste
    today = date.today().isoformat()
    updated = update_manifest(MANIFEST_PATH, args.output, today, args.url, args.source)
    if updated:
        print(f"✓ MANIFEST.yml mis à jour (captured_at → {today})")
    else:
        print(
            f"  Note : {args.output!r} absent du MANIFEST.yml. "
            "Ajouter l'entrée manuellement avant de commiter."
        )

    return 0


if __name__ == "__main__":
    sys.exit(main())
