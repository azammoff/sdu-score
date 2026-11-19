from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings, read from environment variables or a .env file."""

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_name: str = "SDU Score API"
    admin_api_key: str = "sdu-admin-key"
    database_url: str = "postgresql+psycopg://sdu:sdu@localhost:5432/sdu_score"
    test_database_url: str | None = None  # used only by pytest

    # Business rule constants
    roster_max_players: int = 25
    min_hours_between_team_matches: int = 2


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
