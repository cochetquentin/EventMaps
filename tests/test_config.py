"""Tests for config.py — ALLOWED_ORIGINS parsing and CORS security warning."""

import warnings

import pytest
from pydantic import ValidationError

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
# LEGACY-003 — EVENTMAPS_ENV et blocage CORS wildcard en production
# ---------------------------------------------------------------------------


def test_env_default_is_development(monkeypatch):
    monkeypatch.delenv("EVENTMAPS_ENV", raising=False)
    s = Settings(_env_file=None)
    assert s.env == "development"


def test_production_with_wildcard_origins_raises():
    with pytest.raises(RuntimeError, match="EVENTMAPS_ENV=production"):
        Settings(env="production", allowed_origins=["*"], _env_file=None)


def test_production_with_wildcard_in_mixed_origins_raises():
    with pytest.raises(RuntimeError, match="EVENTMAPS_ENV=production"):
        Settings(env="production", allowed_origins=["*", "https://a.com"], _env_file=None)


def test_production_with_explicit_origins_does_not_raise():
    s = Settings(env="production", allowed_origins=["https://a.com"], _env_file=None)
    assert s.env == "production"


def test_production_env_var_with_wildcard_raises(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_ENV", "production")
    monkeypatch.delenv("EVENTMAPS_ALLOWED_ORIGINS", raising=False)
    with pytest.raises(RuntimeError, match="EVENTMAPS_ENV=production"):
        Settings(_env_file=None)


def test_invalid_env_value_rejected():
    with pytest.raises(ValidationError):
        Settings(env="staging", _env_file=None)


def test_development_with_wildcard_and_token_still_warns():
    """Le warning existant (dev + token + wildcard) reste inchangé — seule la
    production bloque désormais le démarrage."""
    with warnings.catch_warnings(record=True) as caught:
        warnings.simplefilter("always")
        Settings(env="development", allowed_origins=["*"], scrape_token="secret", _env_file=None)
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


# ---------------------------------------------------------------------------
# ARCH-006 — Scraping config settings
# ---------------------------------------------------------------------------


def test_scrape_request_timeout_seconds_default():
    s = Settings(_env_file=None)
    assert s.scrape_request_timeout_seconds == 10


def test_scrape_max_pages_tc_default():
    s = Settings(_env_file=None)
    assert s.scrape_max_pages_tc == 10


def test_scrape_max_pages_hanabi_default():
    s = Settings(_env_file=None)
    assert s.scrape_max_pages_hanabi == 20


def test_scrape_retry_attempts_default():
    s = Settings(_env_file=None)
    assert s.scrape_retry_attempts == 3


def test_scrape_retry_wait_min_default():
    s = Settings(_env_file=None)
    assert s.scrape_retry_wait_min == 2


def test_scrape_retry_wait_max_default():
    s = Settings(_env_file=None)
    assert s.scrape_retry_wait_max == 10


def test_scrape_request_timeout_env_override(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_SCRAPE_REQUEST_TIMEOUT_SECONDS", "30")
    s = Settings()
    assert s.scrape_request_timeout_seconds == 30


def test_scrape_max_pages_tc_env_override(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_SCRAPE_MAX_PAGES_TC", "5")
    s = Settings()
    assert s.scrape_max_pages_tc == 5


def test_scrape_retry_attempts_env_override(monkeypatch):
    monkeypatch.setenv("EVENTMAPS_SCRAPE_RETRY_ATTEMPTS", "5")
    s = Settings()
    assert s.scrape_retry_attempts == 5
