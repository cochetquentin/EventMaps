"""Orchestration du cycle de review Codex ↔ Claude Code.

Phases :
1. Identifier la PR et le repo
2. Protection anti-boucle
3. Récupérer les remarques Codex
4. Afficher les corrections à appliquer (logique pilotée par Claude)
5. Tests
6. Commit et push
7. Relancer Codex

Usage : uv run --locked python scripts/handle_codex_review.py
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

# Force UTF-8 sur stdout/stderr pour les consoles Windows (cp1252 ne supporte pas les emojis)
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CODEX_BOT = "chatgpt-codex-connector[bot]"
CODEX_TRIGGER = "@codex review"
PYTEST_CMD = [
    "uv",
    "run",
    "--locked",
    "python",
    "-m",
    "pytest",
    "--cov=.",
    "--cov-fail-under=80",
    "tests/",
    "-v",
]


# ---------------------------------------------------------------------------
# Utilitaires bas niveau
# ---------------------------------------------------------------------------


def parse_iso_epoch(s: str) -> int:
    """Convertit une date ISO 8601 en epoch UTC (secondes). Retourne 0 si vide."""
    if not s or not s.strip():
        return 0
    return int(datetime.fromisoformat(s.strip().replace("Z", "+00:00")).timestamp())


def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    """Point d'entrée unique pour tous les appels subprocess — mockable dans les tests."""
    return subprocess.run(cmd, capture_output=capture, text=True, check=check, encoding="utf-8")


def _gh(*args: str) -> str:
    """Exécute gh CLI et retourne stdout (strip)."""
    result = _run(["gh", *args])
    return result.stdout.strip()


def _git(*args: str, check: bool = True) -> str:
    """Exécute git et retourne stdout (strip)."""
    result = _run(["git", *args], check=check)
    return result.stdout.strip()


# ---------------------------------------------------------------------------
# Structures de données
# ---------------------------------------------------------------------------


@dataclass
class PRInfo:
    repo: str
    number: int
    title: str
    head_branch: str
    head_sha: str


@dataclass
class CodexRemark:
    source: str  # "review" | "inline" | "comment"
    body: str
    file: Optional[str] = None
    line: Optional[int] = None
    created_at: str = ""


@dataclass
class CycleResult:
    pr: Optional[PRInfo] = None
    remarks_found: int = 0
    applied: list[str] = field(default_factory=list)
    ignored: list[tuple[str, str]] = field(default_factory=list)
    tests_passed: bool = False
    coverage: Optional[float] = None
    commit_sha: Optional[str] = None
    commit_message: Optional[str] = None
    pushed: bool = False
    codex_relaunched: bool = False
    skip_reason: Optional[str] = None
    stopped_early: bool = False
    stop_reason: Optional[str] = None


# ---------------------------------------------------------------------------
# Phase 1 — Identifier la PR et le repo
# ---------------------------------------------------------------------------


def phase1_get_pr_info() -> PRInfo:
    """Récupère les métadonnées de la PR courante via gh CLI."""
    repo = _gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    pr_json = _gh("pr", "view", "--json", "number,title,state,headRefOid")
    data = json.loads(pr_json)

    if data.get("state", "").upper() != "OPEN":
        raise SystemExit("PR fermée ou mergée — arrêt.")

    head_branch = _git("branch", "--show-current")

    return PRInfo(
        repo=repo,
        number=data["number"],
        title=data["title"],
        head_branch=head_branch,
        head_sha=data["headRefOid"],
    )


# ---------------------------------------------------------------------------
# Phase 2 — Protection anti-boucle
# ---------------------------------------------------------------------------


def _latest_epoch(values: list[str]) -> int:
    """Retourne le max des epochs parmi une liste de dates ISO (peut contenir des chaînes vides)."""
    return max((parse_iso_epoch(v) for v in values), default=0)


def phase2_anti_loop(pr: PRInfo) -> tuple[bool, str]:
    """Vérifie si @Codex review a déjà été posté sans réponse depuis le dernier commit.

    Retourne (should_stop, reason).
    """
    # T_TRIGGER : dernier commentaire dont le body est EXACTEMENT "@Codex review"
    trigger_dates = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/issues/{pr.number}/comments",
        "--jq",
        '.[] | select(.body | ltrimstr("\\n") | rtrimstr("\\n") | ltrimstr("\\r") | rtrimstr("\\r") | ascii_downcase | . == "@codex review") | .created_at',
    )
    t_trigger = trigger_dates.strip().split("\n")[-1].strip() if trigger_dates.strip() else ""
    t_trigger_e = parse_iso_epoch(t_trigger)

    # T_CODEX : dernière réponse Codex (3 endpoints)
    codex_reviews = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/pulls/{pr.number}/reviews",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}") | .submitted_at',
    )
    codex_comments = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/pulls/{pr.number}/comments",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}") | .created_at',
    )
    codex_issue = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/issues/{pr.number}/comments",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}") | .created_at',
    )
    all_codex_dates = [
        *(
            [d for d in codex_reviews.strip().split("\n") if d.strip()]
            if codex_reviews.strip()
            else []
        ),
        *(
            [d for d in codex_comments.strip().split("\n") if d.strip()]
            if codex_comments.strip()
            else []
        ),
        *([d for d in codex_issue.strip().split("\n") if d.strip()] if codex_issue.strip() else []),
    ]
    t_codex_e = _latest_epoch(all_codex_dates)

    # T_COMMIT : date du dernier commit de la PR
    # check=False car une erreur API transiente ne doit pas annuler le cycle entier
    try:
        commit_raw = _gh(
            "api", f"repos/{pr.repo}/commits/{pr.head_sha}", "--jq", ".commit.committer.date"
        )
    except subprocess.CalledProcessError:
        commit_raw = ""
    if not commit_raw:
        commit_raw = _git("log", "-1", "--format=%cI")
    t_commit_e = parse_iso_epoch(commit_raw)

    if t_trigger_e > 0 and t_trigger_e > t_commit_e and t_codex_e < t_trigger_e:
        return (
            True,
            (
                "Anti-boucle : @Codex review déjà posté après le dernier commit "
                "et Codex n'a pas encore répondu."
            ),
            t_trigger,
        )
    return False, "", t_trigger


# ---------------------------------------------------------------------------
# Phase 3 — Récupérer les remarques Codex
# ---------------------------------------------------------------------------


def _parse_remarks_from_json(raw: str, source: str) -> list[CodexRemark]:
    """Parse une sortie jq (un objet JSON par ligne) en liste de CodexRemark."""
    remarks = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        body = obj.get("body", "").strip()
        if not body or body.lower() == CODEX_TRIGGER:
            continue
        login = (obj.get("user") or {}).get("login", "")
        if login != CODEX_BOT:
            continue
        file_ = obj.get("path") or obj.get("diff_hunk") and obj.get("path") or None
        line_num = obj.get("line") or obj.get("original_line") or None
        created_at = obj.get("created_at") or obj.get("submitted_at") or ""
        remarks.append(
            CodexRemark(source=source, body=body, file=file_, line=line_num, created_at=created_at)
        )
    return remarks


def phase3_get_remarks(pr: PRInfo, since: str = "") -> list[CodexRemark]:
    """Récupère les remarques Codex depuis les 3 endpoints GitHub, filtrées après `since`."""
    since_filter = f' | select(.created_at > "{since}")' if since else ""
    since_filter_r = f' | select(.submitted_at > "{since}")' if since else ""

    raw_reviews = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/pulls/{pr.number}/reviews",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}") | select(.state == "CHANGES_REQUESTED"){since_filter_r}',
    )
    raw_inline = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/pulls/{pr.number}/comments",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}"){since_filter}',
    )
    raw_issue = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/issues/{pr.number}/comments",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}"){since_filter}',
    )

    remarks = []
    # Priorité : reviews formelles → inline → commentaires généraux
    remarks.extend(_parse_remarks_from_json(raw_reviews, "review"))
    remarks.extend(_parse_remarks_from_json(raw_inline, "inline"))
    remarks.extend(_parse_remarks_from_json(raw_issue, "comment"))

    return remarks


# ---------------------------------------------------------------------------
# Phase 4 — Afficher les corrections à appliquer
# (la logique d'application reste pilotée par Claude / l'opérateur)
# ---------------------------------------------------------------------------


def phase4_display_remarks(
    remarks: list[CodexRemark],
    dirty_files: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Affiche les remarques à traiter et retourne les listes (applied, ignored).

    Cette phase ne modifie aucun fichier — elle présente le plan à l'opérateur
    (Claude) qui applique ensuite les corrections via ses outils natifs.

    Un fichier dans dirty_files est signalé comme à ignorer pour éviter de
    mélanger les changements du workflow avec des modifications préexistantes.
    """
    applied: list[str] = []
    ignored: list[tuple[str, str]] = []

    print("\n## Remarques Codex à traiter\n")
    for i, remark in enumerate(remarks, 1):
        loc = (
            f"{remark.file}:{remark.line}"
            if remark.file and remark.line
            else remark.file or "(général)"
        )
        if remark.file and remark.file in dirty_files:
            reason = "fichier modifié localement avant le workflow"
            ignored.append((f"{loc} — {remark.body[:60]}", reason))
            print(f"  [{i}] IGNORÉ ({reason}) — {loc}")
        else:
            print(f"  [{i}] {loc} — {remark.body[:80]}")
            # `applied` reste vide ici — l'opérateur (Claude) applique les corrections
            # via ses outils natifs, puis appelle phase5/6/7 séparément.

    return applied, ignored


def get_dirty_files() -> list[str]:
    """Retourne la liste des fichiers modifiés dans le working tree."""
    output = _git("status", "--porcelain")
    files = []
    for line in output.splitlines():
        if len(line) >= 4:
            files.append(line[3:].strip())
    return files


def get_new_untracked_files(pre_dirty: list[str]) -> list[str]:
    """Retourne les fichiers non-trackés apparus APRÈS le début du workflow."""
    output = _git("status", "--porcelain")
    current_untracked = []
    for line in output.splitlines():
        if line.startswith("??"):
            current_untracked.append(line[3:].strip())
    return [f for f in current_untracked if f not in pre_dirty]


# ---------------------------------------------------------------------------
# Phase 5 — Tests
# ---------------------------------------------------------------------------


def phase5_run_tests() -> tuple[bool, Optional[float]]:
    """Lance pytest et retourne (passed, coverage_pct)."""
    result = _run(PYTEST_CMD, check=False)
    passed = result.returncode == 0

    # Extraire le pourcentage de coverage depuis stdout
    coverage: Optional[float] = None
    for line in (result.stdout or "").splitlines():
        if "TOTAL" in line and "%" in line:
            parts = line.split()
            for part in parts:
                if part.endswith("%"):
                    try:
                        coverage = float(part.rstrip("%"))
                    except ValueError:
                        pass
                    break

    return passed, coverage


def rollback(
    tracked_modified: list[str],
    new_untracked: list[str],
    pre_dirty: list[str],
) -> None:
    """Annule les modifications apportées par le workflow (sauf pre_dirty)."""
    for f in tracked_modified:
        if f not in pre_dirty:
            _git("checkout", "--", f, check=False)
    for f in new_untracked:
        try:
            if os.path.isdir(f):
                shutil.rmtree(f)
            else:
                os.unlink(f)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Phase 6 — Commit et push
# ---------------------------------------------------------------------------


def phase6_commit_push(
    pr: PRInfo,
    files_to_stage: list[str],
) -> tuple[Optional[str], Optional[str], bool]:
    """Commit et push les fichiers produits par ce cycle. Retourne (sha, message, pushed).

    Seuls les fichiers listés dans files_to_stage sont stagés pour éviter d'inclure
    des changements pré-existants non liés au cycle Codex.
    """
    if not files_to_stage:
        return None, None, False

    for f in files_to_stage:
        _git("add", f)

    # Vérifier qu'il y a effectivement quelque chose de stagé
    staged = _git("diff", "--cached", "--name-only", check=False)
    if not staged.strip():
        return None, None, False

    message = "fix: appliquer corrections Codex"
    _git("commit", "-m", message)
    sha = _git("rev-parse", "HEAD")

    _git("push")
    return sha, message, True


# ---------------------------------------------------------------------------
# Phase 7 — Relancer Codex
# ---------------------------------------------------------------------------


def phase7_relaunch_codex(pr: PRInfo) -> bool:
    """Re-vérifie l'anti-boucle puis poste @Codex review."""
    # Re-fetch HEAD après push
    pr_json = _gh("pr", "view", "--json", "headRefOid")
    pr.head_sha = json.loads(pr_json)["headRefOid"]

    if phase2_anti_loop(pr)[0]:
        return False

    _gh("pr", "comment", str(pr.number), "--body", "@Codex review")
    return True


# ---------------------------------------------------------------------------
# Orchestration principale
# ---------------------------------------------------------------------------


def run() -> CycleResult:
    result = CycleResult()

    # Phase 1
    print("## Phase 1 — Identification de la PR")
    pr = phase1_get_pr_info()
    result.pr = pr
    print(f"PR #{pr.number} — {pr.title} ({pr.repo})")

    # Phase 2
    print("\n## Phase 2 — Anti-boucle")
    stop, reason, t_trigger = phase2_anti_loop(pr)
    if stop:
        result.stopped_early = True
        result.stop_reason = reason
        print(f"STOP : {reason}")
        return result
    print("OK — pas de boucle détectée.")

    # Phase 3
    print("\n## Phase 3 — Récupération des remarques Codex")
    remarks = phase3_get_remarks(pr, since=t_trigger)
    result.remarks_found = len(remarks)
    if not remarks:
        result.stopped_early = True
        result.stop_reason = "Aucune remarque Codex sur cette PR."
        print(result.stop_reason)
        return result
    print(f"{len(remarks)} remarque(s) trouvée(s).")

    # Phase 4
    print("\n## Phase 4 — Corrections à appliquer")
    pre_dirty = get_dirty_files()
    applied, ignored = phase4_display_remarks(remarks, pre_dirty)
    result.applied = applied
    result.ignored = ignored

    # Phase 5
    print("\n## Phase 5 — Tests")
    # Capturer les fichiers modifiés par ce workflow (pour rollback éventuel)
    post_dirty = get_dirty_files()
    workflow_tracked = [f for f in post_dirty if f not in pre_dirty]
    new_untracked = get_new_untracked_files(pre_dirty)

    passed, coverage = phase5_run_tests()
    result.tests_passed = passed
    result.coverage = coverage
    print(
        f"Tests : {'PASS' if passed else 'FAIL'}"
        + (f" (coverage : {coverage}%)" if coverage else "")
    )

    if not passed:
        # Max 2 tentatives
        print("Tentative 2/2...")
        passed, coverage = phase5_run_tests()
        result.tests_passed = passed
        result.coverage = coverage
        if not passed:
            print("Tests toujours en échec — rollback des modifications de ce cycle.")
            rollback(workflow_tracked, new_untracked, pre_dirty)
            result.applied = []
            result.skip_reason = "Tests en échec après 2 tentatives — rollback effectué."
            return result

    # Phase 6
    print("\n## Phase 6 — Commit et push")
    files_changed = workflow_tracked + new_untracked
    if not files_changed:
        result.skip_reason = "Aucune modification — pas de commit."
        print(result.skip_reason)
        return result

    sha, message, pushed = phase6_commit_push(pr, files_changed)
    result.commit_sha = sha
    result.commit_message = message
    result.pushed = pushed

    if not sha:
        result.skip_reason = "Aucun diff — pas de commit."
        print(result.skip_reason)
        return result

    print(f"Commit : {sha[:8]} — {message}")

    # Phase 7
    print("\n## Phase 7 — Relance Codex")
    relaunched = phase7_relaunch_codex(pr)
    result.codex_relaunched = relaunched
    if relaunched:
        print("@Codex review posté.")
    else:
        result.skip_reason = "Anti-boucle post-push : @Codex review non posté."
        print(result.skip_reason)

    return result


# ---------------------------------------------------------------------------
# Résumé de sortie
# ---------------------------------------------------------------------------


def print_summary(result: CycleResult) -> None:
    pr = result.pr
    print("\n" + "=" * 60)
    print("## /handle-codex-review — Résultat\n")
    if pr:
        print(f"PR : #{pr.number} — {pr.title}")
        print(f"Branche : {pr.head_branch}")
    print(f"\nRemarques Codex : {result.remarks_found} trouvée(s)")
    print(f"Corrections : {len(result.applied)} appliquée(s), {len(result.ignored)} ignorée(s)")
    if result.ignored:
        for desc, reason in result.ignored:
            print(f"  - {desc} → {reason}")
    cov_str = f" (coverage : {result.coverage}%)" if result.coverage is not None else ""
    if result.stopped_early and result.coverage is None:
        tests_label = "N/A (arrêt anticipé)"
    else:
        tests_label = f"{'PASS' if result.tests_passed else 'FAIL'}{cov_str}"
    print(f"Tests : {tests_label}")
    if result.commit_sha:
        print(f'Commit : {result.commit_sha[:8]} — "{result.commit_message}"')
    else:
        print("Commit : SKIPPED")
    print(f"Push : {'OK' if result.pushed else 'SKIPPED'}")
    relance = (
        "OUI"
        if result.codex_relaunched
        else f"NON ({result.skip_reason or result.stop_reason or 'arrêt anticipé'})"
    )
    print(f"@Codex review relancé : {relance}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    result = run()
    print_summary(result)
    sys.exit(0)
