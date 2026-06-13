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

# Force UTF-8 sur stdout/stderr pour les consoles Windows (cp1252 ne supporte pas les emojis)
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


def _git(*args: str, check: bool = True, raw: bool = False) -> str:
    """Exécute git et retourne stdout.

    Par défaut strip() le résultat. Passer raw=True pour conserver l'output
    sans modification (nécessaire pour les formats NUL-délimités comme --porcelain -z).
    """
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
    source: str  # "review" | "inline" | "comment"
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


def phase2_anti_loop(pr: PRInfo) -> tuple[bool, str, str]:
    """Vérifie si @Codex review a déjà été posté sans réponse depuis le dernier commit.

    Retourne (should_stop, reason, t_trigger).
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
    # try/except car une erreur API transiente ne doit pas annuler le cycle entier
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
    """Parse une sortie jq (un objet JSON par ligne) en liste de CodexRemark.

    Filtre :
    - body vide ou None ou égal au trigger "@codex review"
    - messages d'intro standards de Codex (CODEX_INTRO_MARKER)
    - utilisateurs autres que CODEX_BOT
    """
    remarks = []
    for line in raw.strip().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            obj = json.loads(line)
        except json.JSONDecodeError:
            continue
        # obj.get("body") peut être None (champ présent mais null dans l'API)
        body = (obj.get("body") or "").strip()
        if not body or body.lower() == CODEX_TRIGGER:
            continue
        if CODEX_INTRO_MARKER in body.lower():
            continue
        login = (obj.get("user") or {}).get("login", "")
        if login != CODEX_BOT:
            continue
        file_ = obj.get("path") or None
        line_num = obj.get("line") or obj.get("original_line") or None
        created_at = obj.get("created_at") or obj.get("submitted_at") or ""
        remarks.append(
            CodexRemark(source=source, body=body, file=file_, line=line_num, created_at=created_at)
        )
    return remarks


def phase3_get_remarks(pr: PRInfo, since: str = "") -> list[CodexRemark]:
    """Récupère les remarques Codex depuis les 3 endpoints GitHub, filtrées après `since`.

    Reviews acceptées : CHANGES_REQUESTED et COMMENTED (le corps peut contenir du feedback
    actionnable même sans CHANGES_REQUESTED). Les messages d'intro sont filtrés dans
    _parse_remarks_from_json.
    """
    since_filter = f' | select(.created_at > "{since}")' if since else ""
    since_filter_r = f' | select(.submitted_at > "{since}")' if since else ""

    raw_reviews = _gh(
        "api",
        "--paginate",
        f"repos/{pr.repo}/pulls/{pr.number}/reviews",
        "--jq",
        f'.[] | select(.user.login == "{CODEX_BOT}") | select(.state == "CHANGES_REQUESTED" or .state == "COMMENTED"){since_filter_r}',
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
    (Claude) qui applique ensuite les corrections via ses outils natifs, puis
    appelle le script avec --finish pour les phases 5-7.

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
            print(f"  [{i}] À appliquer : {loc}")
            # Afficher le corps complet sans troncature
            print(f"       {remark.body}")
            # `applied` reste vide — l'opérateur applique via ses outils natifs.

    return applied, ignored


def get_dirty_files() -> list[str]:
    """Retourne la liste des fichiers modifiés dans le working tree.

    Utilise --porcelain -z --untracked-files=all pour :
    - éviter le C-quoting des noms de fichiers avec caractères spéciaux (via -z)
    - lister les fichiers individuellement plutôt que par répertoire (via --untracked-files=all)

    Pour les renommages, retourne les deux chemins séparément.
    """
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
            # Renommage/copie : avec -z, l'entrée suivante est l'ancien chemin
            files.append(path)
            if i + 1 < len(entries) and entries[i + 1]:
                files.append(entries[i + 1])
            i += 2
        else:
            files.append(path)
            i += 1
    return files


def get_new_untracked_files(pre_dirty: list[str]) -> list[str]:
    """Retourne les fichiers non-trackés apparus APRÈS le début du workflow.

    Utilise --untracked-files=all pour obtenir les chemins de fichiers individuels
    (pas de répertoires) et éviter de confondre un fichier nouveau dans un répertoire
    pré-existant avec le répertoire lui-même.
    """
    output = _git("status", "--porcelain", "-z", "--untracked-files=all", raw=True)
    current_untracked: list[str] = []
    if output:
        for entry in output.split("\0"):
            if not entry or len(entry) < 3:
                continue
            if entry[:2] == "??":
                current_untracked.append(entry[3:])
    return [f for f in current_untracked if f not in pre_dirty]


# ---------------------------------------------------------------------------
# Phase 5 — Tests
# ---------------------------------------------------------------------------


def phase5_run_tests() -> tuple[bool, float | None]:
    """Lance pytest et retourne (passed, coverage_pct)."""
    result = _run(PYTEST_CMD, check=False)
    passed = result.returncode == 0

    # Extraire le pourcentage de coverage depuis stdout
    coverage: float | None = None
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
    """Annule les modifications apportées par le workflow (sauf pre_dirty).

    Les fichiers non-trackés sont listés individuellement (grâce à --untracked-files=all
    dans get_new_untracked_files) : on peut donc les supprimer un par un sans risquer
    d'effacer des fichiers ignorés par git dans un répertoire pré-existant.
    """
    for f in tracked_modified:
        if f not in pre_dirty:
            # Restaure depuis HEAD (pas depuis l'index) pour éviter de restaurer
            # un état intermédiaire stagé non committé
            _git("checkout", "HEAD", "--", f, check=False)
    for f in new_untracked:
        try:
            os.unlink(f)
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Phase 6 — Commit (le push est géré séparément dans run_finish)
# ---------------------------------------------------------------------------


def phase6_commit(
    pr: PRInfo,
    files_to_stage: list[str],
) -> tuple[str | None, str | None]:
    """Commite les fichiers produits par ce cycle. Retourne (sha, message).

    Ne pousse pas — le push est effectué dans run_finish après sauvegarde du sha
    dans l'état, permettant une reprise en cas d'échec réseau.

    L'appelant doit s'assurer qu'aucun changement pré-stagé n'est présent avant
    d'appeler cette fonction.
    """
    if not files_to_stage:
        return None, None

    for f in files_to_stage:
        # -- sépare les options des chemins et prévient l'injection d'options
        # (ex : un fichier nommé '--all' ne deviendrait pas git add --all)
        _git("add", "--", f)

    # Vérifier qu'il y a effectivement quelque chose de stagé
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
    """Re-vérifie l'anti-boucle (garde absolue) puis poste @Codex review.

    La vérification ici est plus stricte que phase2 : refuse si un trigger
    existe déjà après notre commit, même si Codex a déjà répondu — car un
    acteur externe pourrait avoir posté un trigger entre notre push et phase7,
    et poster un second trigger sans nouveau commit violerait la règle absolue.
    """
    # Re-fetch HEAD après push
    pr_json = _gh("pr", "view", "--json", "headRefOid")
    pr.head_sha = json.loads(pr_json)["headRefOid"]

    # Récupérer la date de notre dernier commit
    commit_date = _git("log", "-1", "--format=%cI")
    t_commit_e = parse_iso_epoch(commit_date)

    # Récupérer le trigger le plus récent
    _, _, t_trigger = phase2_anti_loop(pr)
    t_trigger_e = parse_iso_epoch(t_trigger)

    # Garde absolue : si un trigger existe après notre commit → ne pas en poster un autre
    if t_trigger_e > 0 and t_trigger_e > t_commit_e:
        return False

    _gh("pr", "comment", str(pr.number), "--body", "@Codex review")
    return True


# ---------------------------------------------------------------------------
# Orchestration — Étape 1 : phases 1-4
# ---------------------------------------------------------------------------


def run() -> CycleResult:
    """Phases 1-4 : identifie PR, anti-boucle, récupère et affiche les remarques.

    Enregistre l'état dans .hcr_state.json pour que run_finish() sache quels
    fichiers étaient déjà modifiés avant les corrections de l'opérateur.
    """
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

    # Fichiers mentionnés dans les remarques inline (pour filtrer new_untracked dans run_finish)
    remark_files = [r.file for r in remarks if r.file]

    # Sauvegarder l'état pour run_finish()
    state = {
        "pre_dirty": pre_dirty,
        "remark_files": remark_files,
        "remarks_found": len(remarks),
        "pr": {
            "repo": pr.repo,
            "number": pr.number,
            "title": pr.title,
            "head_branch": pr.head_branch,
            "head_sha": pr.head_sha,
        },
        "ignored": [list(x) for x in ignored],
    }
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    result.stopped_early = True
    result.stop_reason = (
        "Corrections à appliquer. "
        "Après modifications, relancer : "
        "uv run --locked python scripts/handle_codex_review.py --finish"
    )
    print(f"\n→ {result.stop_reason}")
    return result


# ---------------------------------------------------------------------------
# Orchestration — Étape 2 : phases 5-7  (après corrections manuelles)
# ---------------------------------------------------------------------------


def run_finish() -> CycleResult:
    """Phases 5-7 : tests, commit/push, relance Codex.

    Lit .hcr_state.json pour déterminer quels fichiers étaient pré-existants
    et ne committer que ceux produits par le cycle courant.

    Reprend depuis la phase 7 si state["commit_sha"] est déjà renseigné
    (cas où le commit a réussi mais le push ou la relance a échoué).
    """
    if not STATE_FILE.exists():
        raise SystemExit(
            "Aucun état de cycle (.hcr_state.json). Lancez d'abord le script sans --finish."
        )

    state = json.loads(STATE_FILE.read_text(encoding="utf-8"))
    pr_data = state["pr"]
    pr = PRInfo(**pr_data)
    pre_dirty: list[str] = state["pre_dirty"]
    remark_files: list[str] = state.get("remark_files", [])

    # Vérifier que l'on est sur la bonne branche
    current_branch = _git("branch", "--show-current")
    if current_branch != pr.head_branch:
        raise SystemExit(
            f"Mauvaise branche : branche courante {current_branch!r} ≠ "
            f"branche PR {pr.head_branch!r}. "
            "Basculez sur la bonne branche avant de relancer --finish."
        )

    result = CycleResult(pr=pr)
    result.ignored = [tuple(x) for x in state.get("ignored", [])]
    result.remarks_found = state.get("remarks_found", 0)

    # --- Reprise : le commit a déjà été effectué lors d'un appel précédent ---
    existing_sha = state.get("commit_sha")
    if existing_sha:
        print(f"Reprise : commit {existing_sha[:8]} déjà effectué.")
        result.commit_sha = existing_sha
        result.commit_message = state.get("commit_message")

        # Vérifier si le commit a déjà été pushé
        remote_sha = _git("rev-parse", f"origin/{pr.head_branch}", check=False)
        local_sha = _git("rev-parse", "HEAD")
        if local_sha == existing_sha and remote_sha != existing_sha:
            print("Push en attente...")
            _git("push")
        result.pushed = True

        print("\n## Phase 7 — Relance Codex")
        relaunched = phase7_relaunch_codex(pr)
        result.codex_relaunched = relaunched
        if relaunched:
            print("@Codex review posté.")
        else:
            result.skip_reason = "Anti-boucle post-push : @Codex review non posté."
            print(result.skip_reason)

        STATE_FILE.unlink(missing_ok=True)
        return result

    # --- Flux normal ---

    # Calculer les fichiers modifiés par le cycle courant
    post_dirty = get_dirty_files()
    # Tracked : inclure tous les fichiers modifiés hors pre_dirty.
    # Pas de filtre par remark_files : une correction inline peut nécessiter
    # de mettre à jour un fichier de test ou un helper non mentionné dans la remarque.
    workflow_tracked = [f for f in post_dirty if f not in pre_dirty]
    # Untracked : restreindre aux fichiers cités dans les remarques pour éviter
    # de committer des fichiers générés ou personnels non liés au cycle.
    new_untracked = get_new_untracked_files(pre_dirty)
    if remark_files:
        new_untracked = [f for f in new_untracked if f in remark_files]

    # Vérifier l'absence de changements pré-stagés avant de toucher à l'index
    pre_staged = _git("diff", "--cached", "--name-only", check=False)
    if pre_staged.strip():
        print(
            "ERREUR : des changements non liés au cycle sont déjà stagés dans l'index. "
            "Déstagez-les (git restore --staged <fichier>) avant de relancer --finish.",
            file=sys.stderr,
        )
        result.skip_reason = "Changements pré-stagés — état préservé pour retry."
        # Ne pas supprimer le state : l'opérateur doit pouvoir relancer --finish après correction
        return result

    # Phase 5 — un seul passage, rollback immédiat en cas d'échec
    print("\n## Phase 5 — Tests")
    passed, coverage = phase5_run_tests()
    result.tests_passed = passed
    result.coverage = coverage
    print(
        f"Tests : {'PASS' if passed else 'FAIL'}"
        + (f" (coverage : {coverage}%)" if coverage else "")
    )

    if not passed:
        print("Tests en échec — rollback des modifications de ce cycle.")
        rollback(workflow_tracked, new_untracked, pre_dirty)
        result.skip_reason = "Tests en échec — rollback effectué."
        return result

    # Phase 6
    print("\n## Phase 6 — Commit et push")
    files_changed = workflow_tracked + new_untracked
    if not files_changed:
        result.skip_reason = "Aucune modification — pas de commit."
        print(result.skip_reason)
        STATE_FILE.unlink(missing_ok=True)
        return result

    sha, message = phase6_commit(pr, files_changed)
    if not sha:
        result.skip_reason = "Aucun diff stagé — pas de commit."
        print(result.skip_reason)
        STATE_FILE.unlink(missing_ok=True)
        return result

    result.commit_sha = sha
    result.commit_message = message

    # Sauvegarder le SHA dans l'état AVANT le push : si le push échoue (réseau),
    # la prochaine exécution de --finish peut reprendre depuis phase 7 directement.
    state["commit_sha"] = sha
    state["commit_message"] = message
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")

    print(f"Commit : {sha[:8]} — {message}")

    _git("push")
    result.pushed = True

    # Phase 7
    print("\n## Phase 7 — Relance Codex")
    relaunched = phase7_relaunch_codex(pr)
    result.codex_relaunched = relaunched
    if relaunched:
        print("@Codex review posté.")
    else:
        result.skip_reason = "Anti-boucle post-push : @Codex review non posté."
        print(result.skip_reason)

    STATE_FILE.unlink(missing_ok=True)
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
    if "--finish" in sys.argv:
        result = run_finish()
    else:
        result = run()
    print_summary(result)
    # Code de sortie non-nul si les tests ont échoué (cycle incomplet sans arrêt anticipé)
    failed = not result.tests_passed and not result.stopped_early
    sys.exit(1 if failed else 0)
