"""Orchestration du cycle de review Codex ↔ Claude Code.

Flux en deux étapes :
  1. uv run --locked python scripts/handle_codex_review.py
       → Phases 1-4 : identifie la PR, vérifie l'anti-boucle, récupère et affiche
         les remarques Codex. Enregistre l'état dans .hcr_state.json et s'arrête.
  2. (Claude applique les corrections via ses outils natifs)
  3. uv run --locked python scripts/handle_codex_review.py --finish
       → Phases 5-7 : tests, commit/push, relance Codex.
"""

from __future__ import annotations

import json
import os
import pathlib
import subprocess
import sys
from dataclasses import dataclass, field
from datetime import datetime

# Force UTF-8 sur stdout/stderr pour les consoles Windows
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
if hasattr(sys.stderr, "reconfigure"):
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")

CODEX_BOT = "chatgpt-codex-connector[bot]"
CODEX_TRIGGER = "@codex review"
CODEX_INTRO_MARKER = "here are some automated review suggestions"
STATE_FILE = pathlib.Path(".hcr_state.json")
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
# Helpers bas niveau (mockables dans les tests)
# ---------------------------------------------------------------------------


def _run(cmd: list[str], check: bool = True, capture: bool = True) -> subprocess.CompletedProcess:
    return subprocess.run(cmd, capture_output=capture, text=True, check=check, encoding="utf-8")


def _gh(*args: str) -> str:
    return _run(["gh", *args]).stdout.strip()


def _git(*args: str, check: bool = True, raw: bool = False) -> str:
    result = _run(["git", *args], check=check)
    return result.stdout if raw else result.stdout.strip()


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
    source: str
    body: str
    file: str | None = None
    line: int | None = None
    created_at: str = ""


@dataclass
class CycleResult:
    pr: PRInfo | None = None
    remarks_found: int = 0
    applied: list[str] = field(default_factory=list)
    ignored: list[tuple[str, str]] = field(default_factory=list)
    tests_passed: bool = False
    coverage: float | None = None
    commit_sha: str | None = None
    commit_message: str | None = None
    pushed: bool = False
    codex_relaunched: bool = False
    skip_reason: str | None = None
    stopped_early: bool = False
    stop_reason: str | None = None


# ---------------------------------------------------------------------------
# Utilitaires date
# ---------------------------------------------------------------------------


def parse_iso_epoch(s: str) -> int:
    """ISO 8601 → epoch UTC. Retourne 0 si vide ou non parseable."""
    if not s:
        return 0
    cleaned = s.strip()
    if not cleaned or cleaned == "null":
        return 0
    try:
        return int(datetime.fromisoformat(cleaned.replace("Z", "+00:00")).timestamp())
    except ValueError:
        return 0


def _latest_epoch(values: list[str]) -> int:
    return max((parse_iso_epoch(v) for v in values), default=0)


# ---------------------------------------------------------------------------
# Phase 1 — Identifier la PR
# ---------------------------------------------------------------------------


def phase1_get_pr_info() -> PRInfo:
    repo = _gh("repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner")
    pr_json = _gh("pr", "view", "--json", "number,title,state,headRefOid")
    data = json.loads(pr_json)
    if data.get("state", "").upper() != "OPEN":
        raise SystemExit("PR fermée ou mergée — arrêt.")
    return PRInfo(
        repo=repo,
        number=data["number"],
        title=data["title"],
        head_branch=_git("branch", "--show-current"),
        head_sha=data["headRefOid"],
    )


# ---------------------------------------------------------------------------
# Phase 2 — Anti-boucle
# ---------------------------------------------------------------------------


def phase2_anti_loop(pr: PRInfo) -> tuple[bool, str, str]:
    """Retourne (should_stop, reason, t_trigger)."""
    trigger_dates = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/issues/{pr.number}/comments",
        "--jq",
        '.[] | select(.body | ltrimstr("\\n") | rtrimstr("\\n") | ltrimstr("\\r") | rtrimstr("\\r") | ascii_downcase | . == "@codex review") | .created_at',
    )
    t_trigger = trigger_dates.strip().split("\n")[-1].strip() if trigger_dates.strip() else ""
    t_trigger_e = parse_iso_epoch(t_trigger)

    if not t_trigger_e:
        return False, "", t_trigger

    codex_reviews = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/pulls/{pr.number}/reviews",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}" and .submitted_at != null) | .submitted_at',
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
        d
        for part in (codex_reviews, codex_comments, codex_issue)
        for d in part.strip().split("\n")
        if d.strip()
    ]
    t_codex_e = _latest_epoch(all_codex_dates)

    commit_date = _gh(
        "api", f"repos/{pr.repo}/commits/{pr.head_sha}", "--jq", ".commit.author.date"
    )
    if not commit_date:
        commit_date = _git("log", "-1", "--format=%cI", pr.head_sha, check=False)
    t_commit_e = parse_iso_epoch(commit_date)

    if t_trigger_e > t_commit_e and t_codex_e <= t_trigger_e:
        reason = f"Anti-boucle : trigger ({t_trigger}) > commit, Codex n'a pas encore répondu."
        return True, reason, t_trigger

    return False, "", t_trigger


# ---------------------------------------------------------------------------
# Phase 3 — Récupérer les remarques Codex
# ---------------------------------------------------------------------------


def _parse_remarks_from_json(raw: str, source: str) -> list[CodexRemark]:
    remarks = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        if obj.get("user", {}).get("login") != CODEX_BOT:
            continue
        body = (obj.get("body") or "").strip()
        if not body:
            continue
        if body.lower().lstrip("\r\n") == CODEX_TRIGGER:
            continue
        if CODEX_INTRO_MARKER in body.lower():
            continue
        remarks.append(
            CodexRemark(
                source=source,
                body=body,
                file=obj.get("path"),
                line=obj.get("line") or obj.get("original_line"),
                created_at=obj.get("created_at") or obj.get("submitted_at") or "",
            )
        )
    return remarks


def phase3_get_remarks(pr: PRInfo) -> list[CodexRemark]:
    remarks: list[CodexRemark] = []
    for endpoint, source in [
        (f"repos/{pr.repo}/pulls/{pr.number}/reviews", "review"),
        (f"repos/{pr.repo}/pulls/{pr.number}/comments", "inline"),
        (f"repos/{pr.repo}/issues/{pr.number}/comments", "comment"),
    ]:
        raw = _gh("api", "--paginate", endpoint)
        remarks.extend(_parse_remarks_from_json(raw, source))
    return remarks


# ---------------------------------------------------------------------------
# Phase 4 — Afficher les remarques
# ---------------------------------------------------------------------------


def phase4_display_remarks(
    remarks: list[CodexRemark],
    dirty_files: list[str],
) -> tuple[list[str], list[tuple[str, str]]]:
    """Affiche les remarques. Retourne (applied=[], ignored)."""
    print("\n## Remarques Codex à traiter\n")
    applied: list[str] = []
    ignored: list[tuple[str, str]] = []
    for i, r in enumerate(remarks, 1):
        label = f"{r.file}:{r.line}" if r.file and r.line else r.file or f"[{r.source}]"
        if r.file and r.file in dirty_files:
            reason = "fichier modifié localement avant le workflow"
            print(f"  [{i}] IGNORÉ ({reason}) — {label}")
            ignored.append((label, reason))
        else:
            print(f"  [{i}] À appliquer : {label}")
            print(f"       {r.body[:300]}")
    return applied, ignored


# ---------------------------------------------------------------------------
# Utilitaires git
# ---------------------------------------------------------------------------


def get_dirty_files() -> list[str]:
    """Liste tous les fichiers modifiés (tracked + untracked) via --porcelain -z."""
    output = _git("status", "--porcelain", "-z", "--untracked-files=all", raw=True)
    files: list[str] = []
    if not output:
        return files
    entries = output.split("\0")
    i = 0
    while i < len(entries):
        entry = entries[i]
        if not entry or len(entry) < 3:
            i += 1
            continue
        status = entry[:2]
        path = entry[3:]
        if status[0] in ("R", "C") or status[1] in ("R", "C"):
            files.append(path)
            if i + 1 < len(entries) and entries[i + 1]:
                files.append(entries[i + 1])
            i += 2
        else:
            files.append(path)
            i += 1
    return files


def get_new_untracked_files(pre_dirty: list[str]) -> list[str]:
    output = _git("status", "--porcelain", "-z", "--untracked-files=all", raw=True)
    result: list[str] = []
    if output:
        for entry in output.split("\0"):
            if not entry or len(entry) < 3:
                continue
            if entry[:2] == "??" and entry[3:] not in pre_dirty:
                result.append(entry[3:])
    return result


# ---------------------------------------------------------------------------
# Phase 5 — Tests
# ---------------------------------------------------------------------------


def phase5_run_tests() -> tuple[bool, float | None]:
    cp = _run(PYTEST_CMD, check=False)
    passed = cp.returncode == 0
    if not passed:
        output = (cp.stdout or "") + (cp.stderr or "")
        print("\n--- Sortie pytest (échec) ---")
        print(output.rstrip())
        print("--- Fin sortie pytest ---\n")
    coverage: float | None = None
    for line in (cp.stdout or "").splitlines():
        if "TOTAL" in line:
            parts = line.split()
            for part in reversed(parts):
                if part.endswith("%"):
                    try:
                        coverage = float(part[:-1])
                        break
                    except ValueError:
                        pass
    return passed, coverage


# ---------------------------------------------------------------------------
# Rollback
# ---------------------------------------------------------------------------


def rollback(tracked_modified: list[str], new_untracked: list[str], pre_dirty: list[str]) -> None:
    for f in tracked_modified:
        if f not in pre_dirty:
            _run(["git", "checkout", "HEAD", "--", f":(literal){f}"], check=False)
    for f in new_untracked:
        try:
            os.unlink(f)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Phase 6 — Commit
# ---------------------------------------------------------------------------


def phase6_commit(files_to_stage: list[str]) -> tuple[str | None, str | None]:
    if not files_to_stage:
        return None, None
    for f in files_to_stage:
        _git("add", "-A", "--", f":(literal){f}")
    staged = _git("diff", "--cached", "--name-only", check=False)
    if not staged.strip():
        return None, None
    message = "fix: appliquer corrections Codex"
    _git("commit", "-m", message)
    sha = _git("rev-parse", "HEAD")
    return sha, message


# ---------------------------------------------------------------------------
# Phase 7 — Relancer Codex
# ---------------------------------------------------------------------------


def phase7_relaunch_codex(pr: PRInfo) -> bool:
    stop, _, _ = phase2_anti_loop(pr)
    if stop:
        return False
    pr_state = json.loads(_gh("pr", "view", str(pr.number), "--repo", pr.repo, "--json", "state"))
    if pr_state.get("state", "").upper() != "OPEN":
        print("PR fermée ou mergée — @Codex review non posté.")
        return False
    _gh("pr", "comment", str(pr.number), "--repo", pr.repo, "--body", "@Codex review")
    return True


# ---------------------------------------------------------------------------
# Orchestration — Étape 1 : phases 1-4
# ---------------------------------------------------------------------------


def run() -> CycleResult:
    if STATE_FILE.exists():
        raise SystemExit(
            "Un cycle est déjà en cours (.hcr_state.json). "
            "Appliquez les corrections et lancez --finish, "
            "ou supprimez .hcr_state.json pour repartir à zéro."
        )

    result = CycleResult()

    print("## Phase 1 — Identification de la PR")
    pr = phase1_get_pr_info()
    result.pr = pr
    print(f"PR #{pr.number} — {pr.title} ({pr.repo})")

    print("\n## Phase 2 — Anti-boucle")
    stop, reason, _ = phase2_anti_loop(pr)
    if stop:
        result.stopped_early = True
        result.stop_reason = reason
        print(f"STOP — {reason}")
        return result
    print("OK — pas de boucle détectée.")

    print("\n## Phase 3 — Récupération des remarques Codex")
    pre_dirty = get_dirty_files()
    remarks = phase3_get_remarks(pr)
    result.remarks_found = len(remarks)
    if not remarks:
        print("Aucune remarque Codex sur cette PR.")
        result.stop_reason = "Aucune remarque Codex sur cette PR."
        result.stopped_early = True
        return result
    print(f"{len(remarks)} remarque(s) trouvée(s).")

    print("\n## Phase 4 — Corrections à appliquer")
    applied, ignored = phase4_display_remarks(remarks, pre_dirty)
    result.applied = applied
    result.ignored = ignored

    STATE_FILE.write_text(
        json.dumps(
            {
                "pre_dirty": pre_dirty,
                "remarks_found": len(remarks),
                "pr": {
                    "repo": pr.repo,
                    "number": pr.number,
                    "title": pr.title,
                    "head_branch": pr.head_branch,
                    "head_sha": pr.head_sha,
                },
                "ignored": [list(x) for x in ignored],
            },
            indent=2,
        ),
        encoding="utf-8",
    )

    result.stopped_early = True
    result.stop_reason = (
        "Corrections à appliquer. "
        "Après modifications, relancer : "
        "uv run --locked python scripts/handle_codex_review.py --finish"
    )
    print(f"\n→ {result.stop_reason}")
    return result


# ---------------------------------------------------------------------------
# Orchestration — Étape 2 : phases 5-7
# ---------------------------------------------------------------------------


def run_finish() -> CycleResult:
    if not STATE_FILE.exists():
        raise SystemExit("Aucun état (.hcr_state.json). Lancez d'abord le script sans --finish.")

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    pr = PRInfo(**state["pr"])
    pre_dirty: list[str] = state["pre_dirty"]

    current_branch = _git("branch", "--show-current")
    if current_branch != pr.head_branch:
        raise SystemExit(f"Mauvaise branche : {current_branch!r} ≠ {pr.head_branch!r}.")

    local_sha = _git("rev-parse", "HEAD")
    if local_sha != pr.head_sha:
        raise SystemExit(
            f"HEAD local ({local_sha[:8]}) ≠ SHA de planification ({pr.head_sha[:8]}). "
            "Des commits ont été créés entre les deux étapes — relancez sans --finish."
        )

    result = CycleResult(pr=pr)
    result.ignored = [tuple(x) for x in state.get("ignored", [])]
    result.remarks_found = state.get("remarks_found", 0)

    post_dirty = get_dirty_files()
    all_new_untracked = get_new_untracked_files(pre_dirty)
    workflow_tracked = [f for f in post_dirty if f not in pre_dirty and f not in all_new_untracked]
    new_untracked_for_commit = all_new_untracked

    pre_staged = _git("diff", "--cached", "--name-only", check=False)
    if pre_staged.strip():
        print(
            "ERREUR : des changements sont déjà stagés. "
            "Déstagez-les (git restore --staged <fichier>) avant de relancer --finish.",
            file=sys.stderr,
        )
        result.skip_reason = "Changements pré-stagés — état préservé pour retry."
        return result

    print("\n## Phase 5 — Tests")
    passed, coverage = phase5_run_tests()
    result.tests_passed = passed
    result.coverage = coverage
    print(
        f"Tests : {'PASS' if passed else 'FAIL'}"
        + (f" (coverage : {coverage}%)" if coverage else "")
    )

    if not passed:
        rollback(workflow_tracked, new_untracked_for_commit, pre_dirty)
        result.skip_reason = "Tests en échec — rollback effectué."
        STATE_FILE.unlink(missing_ok=True)
        return result

    print("\n## Phase 6 — Commit et push")
    files_changed = workflow_tracked + new_untracked_for_commit
    if not files_changed:
        result.skip_reason = "Aucune modification — pas de commit."
        print(result.skip_reason)
        STATE_FILE.unlink(missing_ok=True)
        return result

    sha, message = phase6_commit(files_changed)
    if not sha:
        result.skip_reason = "Aucun diff stagé — pas de commit."
        print(result.skip_reason)
        STATE_FILE.unlink(missing_ok=True)
        return result

    result.commit_sha = sha
    result.commit_message = message
    result.applied = files_changed
    print(f"Commit : {sha[:8]} — {message}")

    _git("push", "origin", f"HEAD:refs/heads/{pr.head_branch}")
    result.pushed = True

    print("\n## Phase 7 — Relance Codex")
    relaunched = phase7_relaunch_codex(pr)
    result.codex_relaunched = relaunched
    print("@Codex review posté." if relaunched else "Anti-boucle — @Codex review non posté.")

    STATE_FILE.unlink(missing_ok=True)
    return result


# ---------------------------------------------------------------------------
# Résumé
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
    for desc, reason in result.ignored:
        print(f"  - {desc} → {reason}")
    cov_str = f" (coverage : {result.coverage}%)" if result.coverage is not None else ""
    if result.stopped_early and result.coverage is None:
        tests_label = "N/A (arrêt anticipé)"
    else:
        tests_label = f"{'PASS' if result.tests_passed else 'FAIL'}{cov_str}"
    print(f"Tests : {tests_label}")
    print(
        f"Commit : {result.commit_sha[:8] if result.commit_sha else 'SKIPPED'}"
        + (f' — "{result.commit_message}"' if result.commit_message else "")
    )
    print(f"Push : {'OK' if result.pushed else 'SKIPPED'}")
    codex_label = (
        "OUI"
        if result.codex_relaunched
        else f"NON ({result.stop_reason or result.skip_reason or ''})"
    )
    print(f"@Codex review relancé : {codex_label}")
    print("=" * 60)


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


if __name__ == "__main__":
    finish = "--finish" in sys.argv
    result = run_finish() if finish else run()
    print_summary(result)
    sys.exit(0)
