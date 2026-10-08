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
    database_url: str = "postgresql+psycopg://maintainer:maintainer@localhost:5432/maintainer"
    github_oauth_client_id: str = ""
    github_oauth_client_secret: SecretStr = SecretStr("")
    github_oauth_redirect_uri: str = "http://localhost:8000/auth/callback"
    jwt_secret: SecretStr = SecretStr("")
    jwt_expire_minutes: int = 60 * 24
    anthropic_api_key: SecretStr = SecretStr("")
    openai_api_key: SecretStr = SecretStr("")
    # Exact model versions, never "latest" aliases.
    anthropic_model: str = "claude-sonnet-5-5"
    openai_model: str = "gpt-4.1-2025-04-14"
    # "hash" = deterministic local embeddings for dev/tests; "openai" = real embeddings.
    embedding_provider: str = "hash"
    openai_embedding_model: str = "text-embedding-3-small"
    # Minimum cosine similarity for a chunk to count as relevant; tune with the 5.16 eval.
    retrieval_min_score: float = 0.2
    # Conversation history above this many tokens is compacted into a summary.
    history_budget_tokens: int = 1500
    test_database_url: str = "postgresql+psycopg://maintainer:maintainer@localhost:5432/maintainer_test"


settings = Settings()
