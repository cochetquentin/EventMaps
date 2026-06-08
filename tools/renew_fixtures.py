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
import math
import os
import re
import sys
import time
import urllib.robotparser
from datetime import date
from pathlib import Path
from urllib.parse import urljoin, urlparse

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


def _non_negative_float(value: str) -> float:
    """Convertit value en float non-négatif pour argparse."""
    try:
        f = float(value)
    except ValueError:
        raise argparse.ArgumentTypeError(f"{value!r} n'est pas un nombre valide")
    if not math.isfinite(f):
        raise argparse.ArgumentTypeError(f"le délai doit être un nombre fini, reçu {f}")
    if f < 0:
        raise argparse.ArgumentTypeError(f"le délai doit être >= 0, reçu {f}")
    return f


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
        type=_non_negative_float,
        default=DEFAULT_DELAY,
        help=f"Délai en secondes après la requête, >= 0 (défaut : {DEFAULT_DELAY}).",
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


def fetch_page(url: str, user_agent: str, timeout: int = 30, delay: float = 0.0) -> str:
    """Récupère le contenu HTML de l'URL. Lève requests.HTTPError si status >= 400.

    Suit les redirections manuellement pour vérifier robots.txt à chaque hop.
    Applique `delay` secondes entre chaque hop de redirection pour respecter les sites.
    Détecte le charset depuis <meta charset> si absent des en-têtes HTTP ;
    si aucun charset détectable, décode en UTF-8 (avec remplacement des caractères invalides).
    Lève TooManyRedirects après 10 sauts consécutifs.
    """
    headers = {"User-Agent": user_agent}
    current_url = url
    max_hops = 10

    for _ in range(max_hops):
        response = requests.get(
            current_url,
            headers=headers,
            timeout=timeout,
            allow_redirects=False,
        )
        if response.is_redirect:
            location = response.headers.get("Location", "")
            if not location:
                break
            next_url = urljoin(current_url, location)
            if not check_robots_allowed(next_url, user_agent):
                raise requests.HTTPError(
                    f"robots.txt interdit le suivi de la redirection vers {next_url!r}",
                    response=response,
                )
            current_url = next_url
            if delay > 0:
                time.sleep(delay)
            continue

        # Rejeter les 3xx sans Location : is_redirect=False mais raise_for_status ne les rejette pas
        if 300 <= response.status_code < 400:
            raise requests.HTTPError(
                f"Réponse {response.status_code} sans en-tête Location pour {current_url!r}",
                response=response,
            )

        response.raise_for_status()

        # Détecte le charset dans <meta charset> si absent des en-têtes HTTP
        if "charset" not in response.headers.get("Content-Type", "").lower():
            snippet = response.content[:4096].decode("latin-1", errors="replace")
            meta_match = re.search(
                r'<meta[^>]+charset=["\']?\s*([a-zA-Z0-9_-]+)',
                snippet,
                re.IGNORECASE,
            )
            if meta_match:
                charset = meta_match.group(1)
                return response.content.decode(charset, errors="replace")
            # Fallback UTF-8 : préférable à ISO-8859-1 (comportement par défaut de Requests)
            return response.content.decode("utf-8", errors="replace")

        return response.text

    raise requests.TooManyRedirects(f"Trop de redirections : {url!r}")


def _fetch_robots(robots_url: str, user_agent: str) -> str | None:
    """Récupère le contenu de robots.txt.

    Retourne :
    - str non vide : robots.txt valide (200)
    - ""            : robots.txt absent (4xx) — aucune restriction
    - None          : injoignable (erreur réseau ou 5xx) — bloquer par précaution (RFC 9309)
    """
    try:
        resp = requests.get(robots_url, headers={"User-Agent": user_agent}, timeout=10)
        if resp.status_code == 200:
            return resp.text
        if resp.status_code >= 500:
            return None  # 5xx = injoignable
        return ""  # 4xx = pas de robots.txt = autorisé
    except Exception:  # noqa: BLE001
        return None  # Erreur réseau = injoignable


def check_robots_allowed(url: str, user_agent: str) -> bool:
    """Vérifie que robots.txt autorise la capture de cette URL.

    Retourne False si robots.txt est injoignable (RFC 9309 : assumer disallow total).
    Retourne True si robots.txt est absent (4xx) ou si la règle autorise l'URL.
    """
    parsed = urlparse(url)
    robots_url = f"{parsed.scheme}://{parsed.netloc}/robots.txt"
    robots_content = _fetch_robots(robots_url, user_agent)
    if robots_content is None:
        return False  # Injoignable → bloquer par précaution (RFC 9309)
    if not robots_content:
        return True  # Pas de robots.txt → autorisé
    rp = urllib.robotparser.RobotFileParser()
    rp.parse(robots_content.splitlines())
    return rp.can_fetch(user_agent, url)


# ── Diff ─────────────────────────────────────────────────────────────────────


def compute_diff(old_content: str, new_content: str, filename: str) -> str:
    """Retourne un diff unified entre old et new. Chaîne vide si contenu identique.

    Utilise splitlines(keepends=True) pour préserver les différences de fins de
    ligne (CRLF vs LF) : deux fichiers identiques à la virgule près mais avec
    des terminateurs différents produisent un diff non-vide. Les lignes d'en-tête
    (---/+++/@@), qui n'ont pas de terminateur natif avec lineterm="", reçoivent
    un \n explicite pour un rendu cohérent.
    """
    old_lines = old_content.splitlines(keepends=True)
    new_lines = new_content.splitlines(keepends=True)
    diff_lines = list(
        difflib.unified_diff(
            old_lines,
            new_lines,
            fromfile=f"a/{filename}",
            tofile=f"b/{filename}",
            lineterm="",
        )
    )
    if not diff_lines:
        return ""
    # Les lignes de contenu ont déjà \n/\r\n ; les lignes d'en-tête n'en ont pas.
    normalized = [line if line.endswith(("\n", "\r\n")) else line + "\n" for line in diff_lines]
    return "".join(normalized).rstrip("\n")


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


def _yaml_escape(value: str) -> str:
    """Échappe value pour une insertion sûre dans un scalaire YAML double-quoté."""
    return value.replace("\\", "\\\\").replace('"', '\\"')


def update_manifest(
    manifest_path: Path,
    fixture_file: str,
    new_date: str,
    url: str,
    source: str,  # noqa: ARG001
) -> bool:
    """Met à jour captured_at et url pour fixture_file dans le manifeste.

    Utilise une substitution regex chirurgicale pour préserver les commentaires
    et l'indentation YAML d'origine.

    Propriétés de la regex :
    - (?=\\s) après le nom de fichier : ancre exacte (évite le match partiel sur
      "a.html" quand le manifeste contient "a.html.bak").
    - (?:(?!- file:).)*? (entry_bound) : borne la correspondance à l'entrée
      sélectionnée, stop avant le prochain '- file:'.
    - Gère les scalaires YAML quotés (double/simple), non-quotés et null.

    Retourne True si l'entrée a été trouvée et mise à jour, False sinon.
    """
    content = manifest_path.read_text(encoding="utf-8")

    escaped = re.escape(fixture_file)
    entry_bound = r"(?:(?!- file:).)*?"
    # Valeurs YAML : double-quoté (avec guillemets échappés), simple-quoté, non-quoté, null
    date_value = r'(?:"(?:[^"\\]|\\.)*"|\'[^\']*\'|null|[0-9]{4}-[0-9]{2}-[0-9]{2})'
    url_value = r'(?:"(?:[^"\\]|\\.)*"|\'[^\']*\'|null|https?://\S+)'

    # Remplace captured_at dans le bloc de cette entrée (ancre exacte après le nom)
    date_pattern = re.compile(
        rf"(- file: {escaped}(?=\s){entry_bound}captured_at: ){date_value}",
        re.DOTALL,
    )
    safe_date = _yaml_escape(new_date)
    new_content, n_date = date_pattern.subn(lambda m: m.group(1) + f'"{safe_date}"', content)
    if n_date == 0:
        return False

    # Remplace url (toute forme valide) par l'URL canonique fournie
    url_pattern = re.compile(
        rf"(- file: {escaped}(?=\s){entry_bound}url: ){url_value}",
        re.DOTALL,
    )
    safe_url = _yaml_escape(url)
    new_content, _ = url_pattern.subn(lambda m: m.group(1) + f'"{safe_url}"', new_content)

    # Réinitialise anonymized: true → false (le nouveau HTML n'est pas encore anonymisé)
    anonymized_pattern = re.compile(
        rf"(- file: {escaped}(?=\s){entry_bound}anonymized: )true",
        re.DOTALL,
    )
    new_content, _ = anonymized_pattern.subn(lambda m: m.group(1) + "false", new_content)

    manifest_path.write_text(new_content, encoding="utf-8")
    return True


# ── Orchestration ─────────────────────────────────────────────────────────────


def main(argv: list[str] | None = None) -> int:
    """Point d'entrée principal. Retourne 0=succès, 1=erreur, 2=annulé."""
    args = parse_args(argv)

    # Blocage CI
    check_not_ci()

    # Validation : résoudre le chemin et vérifier qu'il est sous {source}/real/
    # Cette vérification couvre à la fois la contrainte de source et les path-traversal
    # (ex. tot/real/../../tc/synthetic/event.html passe le test prefix mais pas resolve).
    output_path = FIXTURES_DIR / args.output
    source_real_dir = (FIXTURES_DIR / args.source / "real").resolve()
    try:
        output_path.resolve().relative_to(source_real_dir)
    except ValueError:
        print(
            f"ERREUR : {args.output!r} doit résoudre vers un chemin sous "
            f"{args.source}/real/ (chemin résolu : {output_path.resolve()}).",
            file=sys.stderr,
        )
        return 1

    # Vérification robots.txt
    if not check_robots_allowed(args.url, args.user_agent):
        print(
            f"ERREUR : robots.txt interdit la capture de {args.url!r} "
            f"avec User-Agent {args.user_agent!r}.",
            file=sys.stderr,
        )
        return 1

    time.sleep(args.delay)

    print(f"→ Récupération de {args.url}")
    try:
        new_content = fetch_page(args.url, args.user_agent, delay=args.delay)
    except requests.RequestException as exc:
        print(f"ERREUR réseau : {exc}", file=sys.stderr)
        return 1

    # Diff — toujours affiché (nouveau fichier compris, comparé à "")
    if output_path.exists():
        old_content = output_path.read_text(encoding="utf-8")
        diff = compute_diff(old_content, new_content, args.output)
        print(f"\n── Diff pour {args.output} ──")
    else:
        old_content = ""
        diff = compute_diff(old_content, new_content, args.output)
        print(f"\n── Nouveau fichier : {args.output} ──")
    print_diff(diff, args.output)
    print()

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
