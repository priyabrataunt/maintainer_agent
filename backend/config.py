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
    # Comma-separated GitHub logins allowed to view /admin/metrics. Empty = nobody.
    admin_logins: str = ""
    redis_url: str = "redis://localhost:6379/0"
    # New jobs are refused with 429 once this many are queued or running.
    max_queue_depth: int = 50
    # Extra attempts after the first for a failing job, with growing delays between them.
    job_max_retries: int = 3
    job_retry_delays_s: str = "10,30,90"
    # Scopes requested at login. Writing to GitHub needs "public_repo" (or "repo"); the default
    # is read-only on purpose, so write access is an explicit opt-in.
    github_oauth_scopes: str = "read:user"
    # Fernet key used to encrypt stored GitHub tokens. Empty = tokens are never stored and
    # GitHub writes stay disabled. Generate with:
    #   python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
    token_encryption_key: SecretStr = SecretStr("")
    # Where the browser is sent after a successful login (the UI's home page in production).
    post_login_redirect: str = "/me"
    test_database_url: str = "postgresql+psycopg://maintainer:maintainer@localhost:5432/maintainer_test"


settings = Settings()
