from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    db_path: str = "data/events.db"
    port: int = 8000
    allowed_origins: list[str] = ["*"]
    log_level: str = "INFO"
    scrape_user_agent: str = "EventMaps/1.0"
    scrape_timeout_hours: int = 2

    model_config = {"env_prefix": "EVENTMAPS_"}


settings = Settings()
