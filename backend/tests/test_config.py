import pytest
from pydantic import ValidationError

from backend.config import Settings


def test_reads_token_from_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_from_env")

    settings = Settings(_env_file=None)

    assert settings.github_token.get_secret_value() == "ghp_from_env"


def test_missing_token_fails_fast(monkeypatch):
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "github_token" in str(exc_info.value)


def test_token_is_not_exposed_in_repr(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_secret_value")

    settings = Settings(_env_file=None)

    assert "ghp_secret_value" not in repr(settings)


def test_reads_oauth_credentials_from_environment(monkeypatch):
    monkeypatch.setenv("GITHUB_TOKEN", "ghp_x")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_ID", "client-id")
    monkeypatch.setenv("GITHUB_OAUTH_CLIENT_SECRET", "client-secret")

    settings = Settings(_env_file=None)

    assert settings.github_oauth_client_id == "client-id"
    assert settings.github_oauth_client_secret.get_secret_value() == "client-secret"
    assert "client-secret" not in repr(settings)
