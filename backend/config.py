from pathlib import Path

from pydantic import SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent


class Settings(BaseSettings):
    """Application configuration, read from the environment or a .env file."""

    model_config = SettingsConfigDict(
        env_file=PROJECT_ROOT / ".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    github_token: SecretStr
    github_client_id: str
    github_client_secret: SecretStr
    database_url: str = "postgresql+psycopg://maintainer:maintainer@localhost:5432/maintainer"
    test_database_url: str = "postgresql+psycopg://maintainer:maintainer@localhost:5432/maintainer_test"


settings = Settings()
