import json
import warnings

from pydantic_settings import BaseSettings, EnvSettingsSource


class _OriginsEnvSource(EnvSettingsSource):
    """Normalise EVENTMAPS_ALLOWED_ORIGINS to JSON before pydantic parses it.

    Accepts both JSON array and comma-separated string:
      EVENTMAPS_ALLOWED_ORIGINS=https://a.com,https://b.com
      EVENTMAPS_ALLOWED_ORIGINS=["https://a.com","https://b.com"]
    """

    def prepare_field_value(self, field_name, field, value, value_is_complex):
        if field_name == "allowed_origins" and isinstance(value, str):
            stripped = value.strip()
            if not stripped.startswith("["):
                value = json.dumps([o.strip() for o in stripped.split(",") if o.strip()])
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

    model_config = {"env_prefix": "EVENTMAPS_"}

    def model_post_init(self, __context) -> None:
        if self.allowed_origins == ["*"] and self.scrape_token is not None:
            warnings.warn(
                "CORS wildcard ('*') is active while EVENTMAPS_SCRAPE_TOKEN is set. "
                "Set EVENTMAPS_ALLOWED_ORIGINS to explicit origins in production.",
                stacklevel=2,
            )

    @classmethod
    def settings_customise_sources(cls, settings_cls, init_settings, env_settings, **kwargs):
        return (init_settings, _OriginsEnvSource(settings_cls)) + tuple(kwargs.values())


settings = Settings()
