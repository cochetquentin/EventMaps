"""Tests for config.py — ALLOWED_ORIGINS parsing and CORS security warning."""

import warnings

from config import Settings

# ---------------------------------------------------------------------------
# Parsing EVENTMAPS_ALLOWED_ORIGINS
# ---------------------------------------------------------------------------


def test_allowed_origins_default_is_wildcard(monkeypatch):
    monkeypatch.delenv("EVENTMAPS_ALLOWED_ORIGINS", raising=False)
    monkeypatch.delenv("EVENTMAPS_SCRAPE_TOKEN", raising=False)
    s = Settings()
    assert s.allowed_origins == ["*"]


def test_allowed_origins_csv_single(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_ALLOWED_ORIGINS", "https://a.com")
    s = Settings()
    assert s.allowed_origins == ["https://a.com"]


def test_allowed_origins_csv_multiple(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_ALLOWED_ORIGINS", "https://a.com,https://b.com")
    s = Settings()
    assert s.allowed_origins == ["https://a.com", "https://b.com"]


def test_allowed_origins_csv_strips_spaces(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_ALLOWED_ORIGINS", " https://a.com , https://b.com ")
    s = Settings()
    assert s.allowed_origins == ["https://a.com", "https://b.com"]


def test_allowed_origins_csv_ignores_empty_segments(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_ALLOWED_ORIGINS", "https://a.com,,https://b.com")
    s = Settings()
    assert s.allowed_origins == ["https://a.com", "https://b.com"]


def test_allowed_origins_json_array(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_ALLOWED_ORIGINS", '["https://a.com","https://b.com"]')
    s = Settings()
    assert s.allowed_origins == ["https://a.com", "https://b.com"]


# ---------------------------------------------------------------------------
# CORS wildcard security warning
# ---------------------------------------------------------------------------


def test_warning_when_wildcard_and_token_set():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(allowed_origins=["*"], scrape_token="secret", _env_file=None)
    assert any("EVENTMAPS_ALLOWED_ORIGINS" in str(w.message) for w in caught), (
        "Expected a warning mentioning EVENTMAPS_ALLOWED_ORIGINS"
    )


def test_no_warning_when_wildcard_no_token(monkeypatch):
    monkeypatch.delenv("EVENTMAPS_SCRAPE_TOKEN", raising=False)
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(allowed_origins=["*"], _env_file=None)
    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(user_warnings) == 0


def test_no_warning_when_explicit_origins_with_token():
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(allowed_origins=["https://a.com"], scrape_token="secret", _env_file=None)
    user_warnings = [w for w in caught if issubclass(w.category, UserWarning)]
    assert len(user_warnings) == 0


def test_warning_when_mixed_origins_include_wildcard():
    """A list like ['*', 'https://a.com'] still triggers the warning."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(allowed_origins=["*", "https://a.com"], scrape_token="secret", _env_file=None)
    assert any("EVENTMAPS_ALLOWED_ORIGINS" in str(w.message) for w in caught)


# ---------------------------------------------------------------------------
# scrape_token normalization — empty string → None
# ---------------------------------------------------------------------------


def test_empty_scrape_token_normalized_to_none():
    s = Settings(scrape_token="")
    assert s.scrape_token is None


def test_blank_scrape_token_normalized_to_none():
    s = Settings(scrape_token="   ")
    assert s.scrape_token is None


def test_scrape_token_env_empty_string_is_none(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_SCRAPE_TOKEN", "")
    s = Settings()
    assert s.scrape_token is None


def test_valid_scrape_token_preserved():
    s = Settings(scrape_token="mysecret")
    assert s.scrape_token == "mysecret"
