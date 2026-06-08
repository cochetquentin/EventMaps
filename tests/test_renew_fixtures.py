"""Tests unitaires pour tools/renew_fixtures.py.

Toutes les fonctions réseau sont mockées — aucune requête réelle n'est émise.
"""

from __future__ import annotations

import textwrap
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
import requests

from tools.renew_fixtures import (
    check_not_ci,
    compute_diff,
    fetch_page,
    main,
    parse_args,
    print_diff,
    scan_pii,
    update_manifest,
    write_fixture,
)

# ── TestParseArgs ──────────────────────────────────────────────────────────────


class TestParseArgs:
    def test_required_args_all_present(self):
        args = parse_args(
            ["--source", "tot", "--url", "https://example.com", "--output", "tot/real/foo.html"]
        )
        assert args.source == "tot"
        assert args.url == "https://example.com"
        assert args.output == "tot/real/foo.html"

    def test_missing_source_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--url", "https://example.com", "--output", "tot/real/foo.html"])
        assert exc_info.value.code == 2

    def test_missing_url_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--source", "tot", "--output", "tot/real/foo.html"])
        assert exc_info.value.code == 2

    def test_missing_output_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            parse_args(["--source", "tot", "--url", "https://example.com"])
        assert exc_info.value.code == 2

    def test_invalid_source_exits(self):
        with pytest.raises(SystemExit) as exc_info:
            parse_args(
                ["--source", "invalid", "--url", "https://example.com", "--output", "x.html"]
            )
        assert exc_info.value.code == 2

    def test_default_user_agent(self):
        args = parse_args(
            ["--source", "tc", "--url", "https://x.com", "--output", "tc/real/x.html"]
        )
        assert args.user_agent == "EventMaps-fixture-renewer/1.0"

    def test_default_delay(self):
        args = parse_args(
            ["--source", "tc", "--url", "https://x.com", "--output", "tc/real/x.html"]
        )
        assert args.delay == 2.0

    def test_yes_flag(self):
        args = parse_args(
            ["--source", "tc", "--url", "https://x.com", "--output", "tc/real/x.html", "--yes"]
        )
        assert args.yes is True

    def test_yes_flag_absent(self):
        args = parse_args(
            ["--source", "tc", "--url", "https://x.com", "--output", "tc/real/x.html"]
        )
        assert args.yes is False

    def test_custom_user_agent(self):
        args = parse_args(
            [
                "--source",
                "tc",
                "--url",
                "https://x.com",
                "--output",
                "tc/real/x.html",
                "--user-agent",
                "MyBot/2.0",
            ]
        )
        assert args.user_agent == "MyBot/2.0"

    def test_custom_delay(self):
        args = parse_args(
            [
                "--source",
                "hanabi",
                "--url",
                "https://x.com",
                "--output",
                "hanabi/real/x.html",
                "--delay",
                "5.0",
            ]
        )
        assert args.delay == 5.0

    def test_all_valid_sources(self):
        for source in ("tc", "hanabi", "tot"):
            args = parse_args(
                ["--source", source, "--url", "https://x.com", "--output", f"{source}/real/x.html"]
            )
            assert args.source == source


# ── TestCheckNotCi ─────────────────────────────────────────────────────────────


class TestCheckNotCi:
    def test_blocks_when_ci_true(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        with pytest.raises(SystemExit) as exc_info:
            check_not_ci()
        assert exc_info.value.code == 1

    def test_blocks_when_github_actions(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.setenv("GITHUB_ACTIONS", "true")
        with pytest.raises(SystemExit) as exc_info:
            check_not_ci()
        assert exc_info.value.code == 1

    def test_blocks_when_gitlab_ci(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.setenv("GITLAB_CI", "true")
        with pytest.raises(SystemExit) as exc_info:
            check_not_ci()
        assert exc_info.value.code == 1

    def test_empty_ci_var_passes(self, monkeypatch):
        monkeypatch.setenv("CI", "")
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        # Ne lève pas SystemExit
        check_not_ci()

    def test_passes_without_ci_vars(self, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)
        check_not_ci()  # Ne lève pas d'exception

    def test_error_message_contains_var_name(self, monkeypatch, capsys):
        monkeypatch.setenv("CI", "true")
        with pytest.raises(SystemExit):
            check_not_ci()
        captured = capsys.readouterr()
        assert "CI" in captured.err


# ── TestComputeDiff ────────────────────────────────────────────────────────────


class TestComputeDiff:
    def test_identical_content_returns_empty(self):
        assert compute_diff("<html>same</html>", "<html>same</html>", "file.html") == ""

    def test_diff_shows_added_lines(self):
        old = "line1\n"
        new = "line1\nline2\n"
        diff = compute_diff(old, new, "file.html")
        assert "+" in diff
        assert "line2" in diff

    def test_diff_shows_removed_lines(self):
        old = "line1\nline2\n"
        new = "line1\n"
        diff = compute_diff(old, new, "file.html")
        assert "-" in diff
        assert "line2" in diff

    def test_diff_filename_in_header(self):
        diff = compute_diff("old\n", "new\n", "fixture.html")
        assert "fixture.html" in diff

    def test_new_file_empty_old(self):
        diff = compute_diff("", "<html>new</html>", "new.html")
        assert "new" in diff
        assert "+" in diff

    def test_diff_empty_both(self):
        assert compute_diff("", "", "file.html") == ""


# ── TestPrintDiff ──────────────────────────────────────────────────────────────


class TestPrintDiff:
    def test_prints_identical_message_when_empty_diff(self, capsys):
        print_diff("", "file.html")
        captured = capsys.readouterr()
        assert "identique" in captured.out
        assert "file.html" in captured.out

    def test_prints_diff_lines(self, capsys):
        diff = "+added line\n-removed line\n context line"
        print_diff(diff, "file.html")
        captured = capsys.readouterr()
        assert "added line" in captured.out
        assert "removed line" in captured.out


# ── TestScanPii ────────────────────────────────────────────────────────────────


class TestScanPii:
    def test_detects_email(self):
        content = '<meta content="user@example.com">'
        hits = scan_pii(content)
        types = [h[0] for h in hits]
        assert "email" in types

    def test_detects_timeout_auth(self):
        content = 'var config = { timeoutAuthClientId: "abc123xyz" };'
        hits = scan_pii(content)
        types = [h[0] for h in hits]
        assert "timeout_auth" in types

    def test_detects_newrelic_key(self):
        content = 'newrelic_license_key = "abc123def456"'
        hits = scan_pii(content)
        types = [h[0] for h in hits]
        assert "newrelic_key" in types

    def test_detects_bearer_token(self):
        content = "Authorization: Bearer eyJhbGciOiJSUzI1NiJ9"
        hits = scan_pii(content)
        types = [h[0] for h in hits]
        assert "bearer_token" in types

    def test_no_pii_returns_empty(self):
        content = "<html><body><h1>Hello World</h1></body></html>"
        assert scan_pii(content) == []

    def test_multiple_pii_returns_multiple(self):
        content = 'user@example.com and timeoutAuthClientId: "key123"'
        hits = scan_pii(content)
        assert len(hits) >= 2

    def test_excerpt_is_truncated(self):
        content = "user@example.com"
        hits = scan_pii(content)
        assert all(len(excerpt) <= 60 for _, excerpt in hits)


# ── TestUpdateManifest ─────────────────────────────────────────────────────────


class TestUpdateManifest:
    def _make_manifest(self, tmp_path: Path, content: str) -> Path:
        manifest = tmp_path / "MANIFEST.yml"
        manifest.write_text(content, encoding="utf-8")
        return manifest

    def test_updates_existing_real_entry(self, tmp_path):
        content = textwrap.dedent("""\
            # Manifeste
            fixtures:
              - file: tot/real/listing.html
                category: real
                captured_at: "2026-06-06"
                url: "https://example.com"
        """)
        manifest = self._make_manifest(tmp_path, content)
        result = update_manifest(
            manifest, "tot/real/listing.html", "2026-06-08", "https://example.com", "tot"
        )
        assert result is True
        updated = manifest.read_text(encoding="utf-8")
        assert 'captured_at: "2026-06-08"' in updated
        assert 'captured_at: "2026-06-06"' not in updated

    def test_preserves_comments_and_structure(self, tmp_path):
        content = textwrap.dedent("""\
            # ── Tokyo Cheapo ──────────────────
            fixtures:
              - file: tc/real/listing.html
                category: real
                captured_at: "2026-01-01"
                url: "https://example.com/tc"
        """)
        manifest = self._make_manifest(tmp_path, content)
        update_manifest(
            manifest, "tc/real/listing.html", "2026-06-08", "https://example.com/tc", "tc"
        )
        updated = manifest.read_text(encoding="utf-8")
        assert "# ── Tokyo Cheapo" in updated
        assert "category: real" in updated

    def test_returns_false_for_unknown_file(self, tmp_path):
        content = textwrap.dedent("""\
            fixtures:
              - file: tot/real/listing.html
                captured_at: "2026-06-06"
                url: "https://example.com"
        """)
        manifest = self._make_manifest(tmp_path, content)
        result = update_manifest(
            manifest, "tot/real/unknown.html", "2026-06-08", "https://example.com", "tot"
        )
        assert result is False
        # Fichier inchangé
        assert manifest.read_text(encoding="utf-8") == content

    def test_updates_null_captured_at(self, tmp_path):
        content = textwrap.dedent("""\
            fixtures:
              - file: tot/synthetic/event.html
                category: synthetic
                captured_at: null
                url: null
        """)
        manifest = self._make_manifest(tmp_path, content)
        result = update_manifest(
            manifest, "tot/synthetic/event.html", "2026-06-08", "https://example.com", "tot"
        )
        assert result is True
        updated = manifest.read_text(encoding="utf-8")
        assert 'captured_at: "2026-06-08"' in updated

    def test_does_not_corrupt_other_entries(self, tmp_path):
        content = textwrap.dedent("""\
            fixtures:
              - file: tc/real/a.html
                captured_at: "2026-01-01"
                url: "https://a.com"
              - file: tot/real/b.html
                captured_at: "2026-02-02"
                url: "https://b.com"
              - file: hanabi/real/c.html
                captured_at: "2026-03-03"
                url: "https://c.com"
        """)
        manifest = self._make_manifest(tmp_path, content)
        update_manifest(manifest, "tot/real/b.html", "2026-06-08", "https://b.com", "tot")
        updated = manifest.read_text(encoding="utf-8")
        assert 'captured_at: "2026-01-01"' in updated  # tc/real/a.html inchangé
        assert 'captured_at: "2026-06-08"' in updated  # tot/real/b.html mis à jour
        assert 'captured_at: "2026-03-03"' in updated  # hanabi/real/c.html inchangé

    def test_updates_url_when_null(self, tmp_path):
        content = textwrap.dedent("""\
            fixtures:
              - file: tc/real/listing.html
                captured_at: null
                url: null
        """)
        manifest = self._make_manifest(tmp_path, content)
        update_manifest(manifest, "tc/real/listing.html", "2026-06-08", "https://new-url.com", "tc")
        updated = manifest.read_text(encoding="utf-8")
        assert '"https://new-url.com"' in updated


# ── TestFetchPage ──────────────────────────────────────────────────────────────


class TestFetchPage:
    def test_fetch_returns_html(self):
        mock_response = MagicMock()
        mock_response.text = "<html>content</html>"
        mock_response.raise_for_status = MagicMock()

        with patch("tools.renew_fixtures.requests.get", return_value=mock_response) as mock_get:
            result = fetch_page("https://example.com", "TestBot/1.0")

        assert result == "<html>content</html>"
        mock_get.assert_called_once()

    def test_fetch_sends_user_agent_header(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = ""

        with patch("tools.renew_fixtures.requests.get", return_value=mock_response) as mock_get:
            fetch_page("https://example.com", "MyAgent/2.0")

        call_kwargs = mock_get.call_args
        headers = (
            call_kwargs.kwargs.get("headers") or call_kwargs[1].get("headers") or call_kwargs[0][1]
        )
        assert headers["User-Agent"] == "MyAgent/2.0"

    def test_fetch_uses_timeout(self):
        mock_response = MagicMock()
        mock_response.raise_for_status = MagicMock()
        mock_response.text = ""

        with patch("tools.renew_fixtures.requests.get", return_value=mock_response) as mock_get:
            fetch_page("https://example.com", "Bot/1.0", timeout=30)

        call_kwargs = mock_get.call_args
        timeout_val = call_kwargs.kwargs.get("timeout") or call_kwargs[1].get("timeout")
        assert timeout_val == 30

    def test_fetch_raises_on_http_error(self):
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = requests.HTTPError("404")

        with patch("tools.renew_fixtures.requests.get", return_value=mock_response):
            with pytest.raises(requests.HTTPError):
                fetch_page("https://example.com", "Bot/1.0")


# ── TestWriteFixture ───────────────────────────────────────────────────────────


class TestWriteFixture:
    def test_creates_file(self, tmp_path):
        out = tmp_path / "tc" / "real" / "listing.html"
        write_fixture(out, "<html>test</html>")
        assert out.exists()
        assert out.read_text(encoding="utf-8") == "<html>test</html>"

    def test_creates_parent_directories(self, tmp_path):
        out = tmp_path / "deep" / "nested" / "dir" / "file.html"
        write_fixture(out, "content")
        assert out.exists()


# ── TestMain ───────────────────────────────────────────────────────────────────


class TestMain:
    def _base_argv(self, output: str = "tot/real/listing.html") -> list[str]:
        return ["--source", "tot", "--url", "https://example.com", "--output", output]

    def test_main_blocks_in_ci(self, monkeypatch):
        monkeypatch.setenv("CI", "true")
        with pytest.raises(SystemExit) as exc_info:
            main(self._base_argv())
        assert exc_info.value.code == 1

    def test_main_writes_new_file(self, tmp_path, monkeypatch):
        out_rel = "tot/real/listing_test.html"
        out_abs = tmp_path / out_rel

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch("tools.renew_fixtures.MANIFEST_PATH", tmp_path / "MANIFEST.yml"),
            patch("tools.renew_fixtures.fetch_page", return_value="<html>new</html>"),
            patch("tools.renew_fixtures.time.sleep"),
            patch("tools.renew_fixtures.update_manifest", return_value=False),
        ):
            (tmp_path / "MANIFEST.yml").write_text("fixtures: []\n", encoding="utf-8")
            result = main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    out_rel,
                    "--yes",
                ]
            )

        assert result == 0
        assert out_abs.exists()
        assert out_abs.read_text(encoding="utf-8") == "<html>new</html>"

    def test_main_aborts_on_denial(self, tmp_path, monkeypatch):
        out_rel = "tot/real/listing_deny.html"
        out_abs = tmp_path / out_rel

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch("tools.renew_fixtures.MANIFEST_PATH", tmp_path / "MANIFEST.yml"),
            patch("tools.renew_fixtures.fetch_page", return_value="<html>new</html>"),
            patch("tools.renew_fixtures.time.sleep"),
            patch("tools.renew_fixtures.confirm_write", return_value=False),
        ):
            result = main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    out_rel,
                ]
            )

        assert result == 2
        assert not out_abs.exists()

    def test_main_yes_flag_skips_confirmation(self, tmp_path, monkeypatch):
        out_rel = "tot/real/listing_yes.html"

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch("tools.renew_fixtures.MANIFEST_PATH", tmp_path / "MANIFEST.yml"),
            patch("tools.renew_fixtures.fetch_page", return_value="<html>yes</html>"),
            patch("tools.renew_fixtures.time.sleep"),
            patch("tools.renew_fixtures.update_manifest", return_value=False),
            patch("tools.renew_fixtures.confirm_write") as mock_confirm,
        ):
            (tmp_path / "MANIFEST.yml").write_text("fixtures: []\n", encoding="utf-8")
            result = main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    out_rel,
                    "--yes",
                ]
            )

        assert result == 0
        mock_confirm.assert_not_called()

    def test_main_shows_diff_for_existing_file(self, tmp_path, monkeypatch, capsys):
        out_rel = "tot/real/listing_diff.html"
        out_abs = tmp_path / out_rel
        out_abs.parent.mkdir(parents=True, exist_ok=True)
        out_abs.write_text("<html>old</html>", encoding="utf-8")

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch("tools.renew_fixtures.MANIFEST_PATH", tmp_path / "MANIFEST.yml"),
            patch("tools.renew_fixtures.fetch_page", return_value="<html>new</html>"),
            patch("tools.renew_fixtures.time.sleep"),
            patch("tools.renew_fixtures.update_manifest", return_value=False),
        ):
            (tmp_path / "MANIFEST.yml").write_text("fixtures: []\n", encoding="utf-8")
            main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    out_rel,
                    "--yes",
                ]
            )

        captured = capsys.readouterr()
        assert "Diff" in captured.out or "old" in captured.out or "new" in captured.out

    def test_main_warns_pii_before_confirmation(self, tmp_path, monkeypatch, capsys):
        out_rel = "tot/real/listing_pii.html"

        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        html_with_pii = "<html><body>Contact: admin@secret.com</body></html>"

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch("tools.renew_fixtures.MANIFEST_PATH", tmp_path / "MANIFEST.yml"),
            patch("tools.renew_fixtures.fetch_page", return_value=html_with_pii),
            patch("tools.renew_fixtures.time.sleep"),
            patch("tools.renew_fixtures.confirm_write", return_value=False),
        ):
            main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    out_rel,
                ]
            )

        captured = capsys.readouterr()
        assert (
            "email" in captured.out or "PII" in captured.out or "admin@secret.com" in captured.out
        )

    def test_main_path_traversal_rejected(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch("tools.renew_fixtures.fetch_page", return_value="<html></html>"),
            patch("tools.renew_fixtures.time.sleep"),
        ):
            result = main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    "../../../etc/passwd",
                ]
            )

        assert result == 1

    def test_main_network_error_returns_1(self, tmp_path, monkeypatch):
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with (
            patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path),
            patch(
                "tools.renew_fixtures.fetch_page", side_effect=requests.ConnectionError("timeout")
            ),
        ):
            result = main(
                [
                    "--source",
                    "tot",
                    "--url",
                    "https://example.com",
                    "--output",
                    "tot/real/x.html",
                ]
            )

        assert result == 1

    def test_main_rejects_output_outside_source_real(self, tmp_path, monkeypatch):
        """--output doit commencer par {source}/real/ sinon exit 1."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path):
            # Mauvaise source
            result = main(
                [
                    "--source",
                    "tc",
                    "--url",
                    "https://example.com",
                    "--output",
                    "tot/real/listing.html",
                ]
            )
        assert result == 1

    def test_main_rejects_synthetic_output(self, tmp_path, monkeypatch):
        """--output vers un chemin synthetic est rejeté."""
        monkeypatch.delenv("CI", raising=False)
        monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
        monkeypatch.delenv("GITLAB_CI", raising=False)

        with patch("tools.renew_fixtures.FIXTURES_DIR", tmp_path):
            result = main(
                [
                    "--source",
                    "tc",
                    "--url",
                    "https://example.com",
                    "--output",
                    "tc/synthetic/event_full.html",
                ]
            )
        assert result == 1


class TestUpdateManifestUrlUpdate:
    """Tests spécifiques à la mise à jour de l'URL (P1 + P2 Codex)."""

    def _make_manifest(self, tmp_path: Path, content: str) -> Path:
        manifest = tmp_path / "MANIFEST.yml"
        manifest.write_text(content, encoding="utf-8")
        return manifest

    def test_updates_existing_non_null_url(self, tmp_path):
        """L'URL existante (non-null) est remplacée par la nouvelle URL fournie."""
        import textwrap

        content = textwrap.dedent("""\
            fixtures:
              - file: tot/real/listing.html
                captured_at: "2026-06-06"
                url: "https://old-url.com/page"
        """)
        manifest = self._make_manifest(tmp_path, content)
        update_manifest(
            manifest, "tot/real/listing.html", "2026-06-08", "https://new-url.com/page", "tot"
        )
        updated = manifest.read_text(encoding="utf-8")
        assert '"https://new-url.com/page"' in updated
        assert '"https://old-url.com/page"' not in updated

    def test_url_replacement_bounded_to_entry(self, tmp_path):
        """La regex URL ne corrompt pas l'entrée suivante qui a url: null."""
        import textwrap

        content = textwrap.dedent("""\
            fixtures:
              - file: tot/real/listing.html
                captured_at: "2026-06-06"
                url: "https://existing.com"
              - file: tot/synthetic/event.html
                captured_at: null
                url: null
        """)
        manifest = self._make_manifest(tmp_path, content)
        update_manifest(manifest, "tot/real/listing.html", "2026-06-08", "https://new.com", "tot")
        updated = manifest.read_text(encoding="utf-8")
        # L'entrée synthetic doit toujours avoir url: null
        assert "url: null" in updated
        # L'entrée real doit avoir la nouvelle URL
        assert '"https://new.com"' in updated
