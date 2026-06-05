import json
import warnings

from pydantic import field_validator
from pydantic_settings import (
    BaseSettings,
    DotEnvSettingsSource,
    EnvSettingsSource,
    SettingsConfigDict,
)


def _normalize_origins_value(field_name: str, value: object) -> object:
    """Convert CSV or bare wildcard ALLOWED_ORIGINS string to JSON array string."""
    if field_name == "allowed_origins" and isinstance(value, str):
        stripped = value.strip()
        if not stripped.startswith("["):
            return json.dumps([o.strip() for o in stripped.split(",") if o.strip()])
    return value


class _OriginsEnvSource(EnvSettingsSource):
    """Normalise EVENTMAPS_ALLOWED_ORIGINS from environment variables.

    Accepts both JSON array and comma-separated string:
      EVENTMAPS_ALLOWED_ORIGINS=https://a.com,https://b.com
      EVENTMAPS_ALLOWED_ORIGINS=["https://a.com","https://b.com"]
    """

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        value = _normalize_origins_value(field_name, value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class _OriginsDotEnvSource(DotEnvSettingsSource):
    """Same normalization applied when reading from a .env file."""

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        value = _normalize_origins_value(field_name, value)
        return super().prepare_field_value(field_name, field, value, value_is_complex)


class Settings(BaseSettings):
    db_path: str = "data/events.db"
    port: int = 8000
    allowed_origins: list[str] = ["*"]
    log_level: str = "INFO"
    scrape_user_agent: str = "EventMaps/1.0"
    scrape_timeout_hours: int = 2
    scrape_token: str | None = None
    scrape_error_threshold: float = 0.5
    scrape_request_timeout_seconds: int = 10
    scrape_max_pages_tc: int = 10
    scrape_max_pages_hanabi: int = 20
    scrape_retry_attempts: int = 3
    scrape_retry_wait_min: int = 2
    scrape_retry_wait_max: int = 10
    request_logging: bool = False  # EVENTMAPS_REQUEST_LOGGING — log HTTP requests

    model_config = SettingsConfigDict(
        env_prefix="EVENTMAPS_",
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    @field_validator("scrape_token", mode="before")
    @classmethod
    def normalize_empty_token(cls, v: object) -> object:
        if isinstance(v, str) and not v.strip():
            return None
        return v

    def model_post_init(self, __context) -> None:
        if "*" in self.allowed_origins and self.scrape_token is not None:
            warnings.warn(
                "CORS wildcard ('*') is active while EVENTMAPS_SCRAPE_TOKEN is set. "
                "Set EVENTMAPS_ALLOWED_ORIGINS to explicit origins in production.",
                stacklevel=2,
            )

    @classmethod
    def settings_customise_sources(
        cls, settings_cls, init_settings, env_settings, dotenv_settings=None, **kwargs
    ):
        sources: list = [init_settings, _OriginsEnvSource(settings_cls)]
        if dotenv_settings is not None:
            # Preserve runtime overrides (e.g. Settings(_env_file=None)) by forwarding
            # the env_file already resolved by pydantic-settings on the provided source.
            sources.append(
                _OriginsDotEnvSource(
                    settings_cls,
                    env_file=getattr(dotenv_settings, "env_file", None),
                )
            )
        sources.extend(kwargs.values())
        return tuple(sources)


settings = Settings()
