"""Tests unitaires pour scripts/handle_codex_review.py.

Aucun appel GitHub réel — subprocess._run est mocké via unittest.mock.patch.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import scripts.handle_codex_review as hcr
from scripts.handle_codex_review import (
    CODEX_BOT,
    CodexRemark,
    PRInfo,
    _latest_epoch,
    _parse_remarks_from_json,
    get_dirty_files,
    get_new_untracked_files,
    parse_iso_epoch,
    phase2_anti_loop,
    phase3_get_remarks,
    phase4_display_remarks,
    phase5_run_tests,
    phase6_commit,
    rollback,
)

# ---------------------------------------------------------------------------
# parse_iso_epoch
# ---------------------------------------------------------------------------


def test_parse_iso_epoch_utc_z():
    epoch = parse_iso_epoch("2024-01-15T12:00:00Z")
    assert epoch == 1705320000


def test_parse_iso_epoch_with_offset():
    # +01:00 → 11:00 UTC → même epoch
    epoch_z = parse_iso_epoch("2024-01-15T12:00:00Z")
    epoch_offset = parse_iso_epoch("2024-01-15T13:00:00+01:00")
    assert epoch_z == epoch_offset


def test_parse_iso_epoch_empty_string():
    assert parse_iso_epoch("") == 0


def test_parse_iso_epoch_whitespace_only():
    assert parse_iso_epoch("   ") == 0


# ---------------------------------------------------------------------------
# _latest_epoch
# ---------------------------------------------------------------------------


def test_latest_epoch_returns_max():
    dates = ["2024-01-15T12:00:00Z", "2024-01-16T00:00:00Z", ""]
    result = _latest_epoch(dates)
    assert result == parse_iso_epoch("2024-01-16T00:00:00Z")


def test_latest_epoch_empty_list():
    assert _latest_epoch([]) == 0


# ---------------------------------------------------------------------------
# _parse_remarks_from_json
# ---------------------------------------------------------------------------


def _make_comment(login: str, body: str, created_at: str = "2024-01-15T12:00:00Z") -> str:
    return json.dumps({"user": {"login": login}, "body": body, "created_at": created_at})


def test_parse_remarks_filters_to_bot_only():
    raw = "\n".join(
        [
            _make_comment(CODEX_BOT, "Utilise des f-strings"),
            _make_comment("human-user", "LGTM"),
            _make_comment(CODEX_BOT, "Ajoute des types"),
        ]
    )
    remarks = _parse_remarks_from_json(raw, "comment")
    assert len(remarks) == 2
    assert all(r.source == "comment" for r in remarks)


def test_parse_remarks_skips_empty_body():
    raw = _make_comment(CODEX_BOT, "")
    remarks = _parse_remarks_from_json(raw, "comment")
    assert remarks == []


def test_parse_remarks_skips_codex_trigger():
    raw = _make_comment(CODEX_BOT, "@codex review")
    remarks = _parse_remarks_from_json(raw, "comment")
    assert remarks == []


def test_parse_remarks_skips_codex_intro_message():
    """Le message d'intro standard de Codex est filtré."""
    intro_body = (
        "### 💡 Codex Review\n\nHere are some automated review suggestions for this pull request."
    )
    raw = _make_comment(CODEX_BOT, intro_body)
    remarks = _parse_remarks_from_json(raw, "review")
    assert remarks == []


def test_parse_remarks_skips_invalid_json():
    raw = "not-json\n" + _make_comment(CODEX_BOT, "Remarque valide")
    remarks = _parse_remarks_from_json(raw, "comment")
    assert len(remarks) == 1


# ---------------------------------------------------------------------------
# Anti-boucle — phase2_anti_loop
# ---------------------------------------------------------------------------

PR = PRInfo(repo="owner/repo", number=1, title="Test PR", head_branch="feat/x", head_sha="abc123")

# Timestamps de référence
T_OLD = "2024-01-10T00:00:00Z"  # avant tout
T_COMMIT = "2024-01-15T10:00:00Z"
T_TRIGGER = "2024-01-15T12:00:00Z"  # après commit
T_CODEX = "2024-01-15T14:00:00Z"  # après trigger


def _make_gh_side_effect(trigger: str, codex_r: str, codex_c: str, codex_i: str, commit: str):
    """Fabrique un side_effect pour _gh qui retourne les bonnes valeurs selon les args."""

    def side_effect(*args):
        joined = " ".join(args)
        if "issues" in joined and "comments" in joined and "@codex review" in joined.lower():
            # Appel trigger
            return trigger
        if "pulls" in joined and "reviews" in joined:
            return codex_r
        if "pulls" in joined and "comments" in joined:
            return codex_c
        if "issues" in joined and "comments" in joined:
            return codex_i
        if "commits" in joined:
            return commit
        return ""

    return side_effect


def test_anti_loop_stops_when_trigger_after_commit_no_codex_response():
    """T_TRIGGER > T_COMMIT, T_CODEX = 0 → STOP."""
    with patch.object(hcr, "_gh") as mock_gh, patch.object(hcr, "_git") as mock_git:
        mock_gh.side_effect = _make_gh_side_effect(
            trigger=T_TRIGGER,
            codex_r="",
            codex_c="",
            codex_i="",
            commit=T_COMMIT,
        )
        mock_git.return_value = ""
        stop, reason, t_trigger = phase2_anti_loop(PR)

    assert stop is True
    assert "Anti-boucle" in reason
    assert t_trigger == T_TRIGGER


def test_anti_loop_passes_when_codex_responded_after_trigger():
    """T_CODEX > T_TRIGGER → pas de boucle."""
    with patch.object(hcr, "_gh") as mock_gh, patch.object(hcr, "_git") as mock_git:
        mock_gh.side_effect = _make_gh_side_effect(
            trigger=T_TRIGGER,
            codex_r=T_CODEX,
            codex_c="",
            codex_i="",
            commit=T_COMMIT,
        )
        mock_git.return_value = ""
        stop, reason, t_trigger = phase2_anti_loop(PR)

    assert stop is False
    assert reason == ""
    assert t_trigger == T_TRIGGER


def test_anti_loop_passes_when_no_trigger():
    """Pas de trigger → pas de boucle."""
    with patch.object(hcr, "_gh") as mock_gh, patch.object(hcr, "_git") as mock_git:
        mock_gh.side_effect = _make_gh_side_effect(
            trigger="",
            codex_r="",
            codex_c="",
            codex_i="",
            commit=T_COMMIT,
        )
        mock_git.return_value = ""
        stop, _, t_trigger = phase2_anti_loop(PR)

    assert stop is False
    assert t_trigger == ""


def test_anti_loop_passes_when_trigger_before_commit():
    """T_TRIGGER < T_COMMIT → cycle terminé normalement."""
    with patch.object(hcr, "_gh") as mock_gh, patch.object(hcr, "_git") as mock_git:
        mock_gh.side_effect = _make_gh_side_effect(
            trigger=T_OLD,
            codex_r="",
            codex_c="",
            codex_i="",
            commit=T_COMMIT,
        )
        mock_git.return_value = ""
        stop, _, _ = phase2_anti_loop(PR)

    assert stop is False


# ---------------------------------------------------------------------------
# Phase 3 — get_remarks
# ---------------------------------------------------------------------------


def test_no_remarks_returns_empty_list():
    with patch.object(hcr, "_gh", return_value=""):
        remarks = phase3_get_remarks(PR)
    assert remarks == []


def test_remarks_returns_only_bot_remarks():
    bot_comment = _make_comment(CODEX_BOT, "Utilise des f-strings")
    human_comment = _make_comment("human", "Pas d'accord")

    raw_both = bot_comment + "\n" + human_comment

    with patch.object(hcr, "_gh", return_value=raw_both):
        remarks = phase3_get_remarks(PR)

    assert len(remarks) > 0
    assert all(r.body == "Utilise des f-strings" for r in remarks)


# ---------------------------------------------------------------------------
# Phase 4 — display_remarks
# ---------------------------------------------------------------------------


def test_remark_on_dirty_file_is_ignored():
    remark = CodexRemark(source="comment", body="Corrige ça", file="api/app.py", line=10)
    dirty = ["api/app.py"]

    applied, ignored = phase4_display_remarks([remark], dirty)

    assert applied == []
    assert len(ignored) == 1
    assert "api/app.py" in ignored[0][0]
    assert "modifié localement" in ignored[0][1]


def test_remark_on_clean_file_is_displayed_not_applied():
    """Les remarques sur fichiers propres sont affichées mais applied reste vide."""
    remark = CodexRemark(source="comment", body="Ajoute des types", file="api/app.py", line=5)
    dirty: list[str] = []

    applied, ignored = phase4_display_remarks([remark], dirty)

    assert applied == []
    assert ignored == []


def test_general_remark_is_displayed_not_applied():
    """Les remarques générales sont affichées mais applied reste vide."""
    remark = CodexRemark(source="review", body="Améliore la couverture")

    applied, ignored = phase4_display_remarks([remark], [])

    assert applied == []
    assert ignored == []


# ---------------------------------------------------------------------------
# Phase 5 — tests + rollback
# ---------------------------------------------------------------------------


def _make_completed_process(returncode: int, stdout: str = "") -> subprocess.CompletedProcess:
    cp = MagicMock(spec=subprocess.CompletedProcess)
    cp.returncode = returncode
    cp.stdout = stdout
    return cp


def test_phase5_returns_true_on_success():
    stdout = "TOTAL                    100     10    90%\n1 passed"
    with patch.object(hcr, "_run", return_value=_make_completed_process(0, stdout)):
        passed, cov = phase5_run_tests()
    assert passed is True
    assert cov == 90.0


def test_phase5_returns_false_on_failure():
    with patch.object(hcr, "_run", return_value=_make_completed_process(1, "1 failed")):
        passed, cov = phase5_run_tests()
    assert passed is False


def test_rollback_calls_git_checkout_for_tracked_files(tmp_path, monkeypatch):
    """rollback() appelle git checkout HEAD -- <file> pour les fichiers trackés."""
    monkeypatch.chdir(tmp_path)
    # Créer un fichier non-tracké pour tester os.unlink
    untracked = tmp_path / "new_file.py"
    untracked.write_text("temp")

    with patch.object(hcr, "_git") as mock_git:
        rollback(
            tracked_modified=["api/app.py"],
            new_untracked=[str(untracked)],
            pre_dirty=[],
        )
    mock_git.assert_called_once_with("checkout", "HEAD", "--", "api/app.py", check=False)
    assert not untracked.exists()


def test_rollback_skips_pre_dirty_files():
    """Les fichiers qui étaient déjà sales avant le workflow ne sont pas touchés."""
    with patch.object(hcr, "_git") as mock_git:
        rollback(
            tracked_modified=["pre_existing.py"],
            new_untracked=[],
            pre_dirty=["pre_existing.py"],
        )
    mock_git.assert_not_called()


# ---------------------------------------------------------------------------
# Phase 6 — commit/push
# ---------------------------------------------------------------------------


def test_no_diff_skips_commit_when_no_files():
    """Si files_to_stage est vide → pas de commit."""
    with patch.object(hcr, "_git", return_value=""):
        sha, message = phase6_commit(PR, [])
    assert sha is None


def test_no_diff_skips_commit_when_nothing_staged():
    """Si diff --cached est vide après git add → pas de commit."""

    def git_side_effect(*args, **kwargs):
        if args[0] == "diff":
            return ""  # rien de stagé
        return ""

    with patch.object(hcr, "_git", side_effect=git_side_effect):
        sha, message = phase6_commit(PR, ["api/app.py"])

    assert sha is None


def test_commit_when_diff_exists():
    """Si diff --cached retourne des fichiers → commit."""

    def git_side_effect(*args, **kwargs):
        if args[0] == "diff":
            return "api/app.py"
        if args[0] == "rev-parse":
            return "deadbeef1234"
        return ""

    with patch.object(hcr, "_git", side_effect=git_side_effect):
        sha, message = phase6_commit(PR, ["api/app.py"])

    assert sha == "deadbeef1234"
    assert "corrections Codex" in message


# ---------------------------------------------------------------------------
# get_dirty_files / get_new_untracked_files
# ---------------------------------------------------------------------------


def test_get_dirty_files_parses_porcelain():
    # Format --porcelain -z : entrées séparées par NUL
    with patch.object(hcr, "_git", return_value=" M api/app.py\x00?? new_file.py\x00"):
        files = get_dirty_files()
    assert "api/app.py" in files
    assert "new_file.py" in files


def test_get_dirty_files_parses_rename_record():
    """Les renommages avec -z : 'R  new.py\0old.py\0' → deux chemins séparés."""
    with patch.object(hcr, "_git", return_value="R  new.py\x00old.py\x00"):
        files = get_dirty_files()
    assert "old.py" in files
    assert "new.py" in files


def test_get_new_untracked_files_excludes_pre_dirty():
    # Format --porcelain -z
    with patch.object(hcr, "_git", return_value="?? new_file.py\x00?? pre_existing.py\x00"):
        new = get_new_untracked_files(pre_dirty=["pre_existing.py"])
    assert "new_file.py" in new
    assert "pre_existing.py" not in new
