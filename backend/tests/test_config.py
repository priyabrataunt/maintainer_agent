import pytest
from pydantic import ValidationError

from backend.config import Settings


def _set_required_env(monkeypatch, **overrides):
    monkeypatch.setenv("GITHUB_TOKEN", overrides.get("github_token", "ghp_from_env"))
    monkeypatch.setenv(
        "GITHUB_CLIENT_ID", overrides.get("github_client_id", "client_id_from_env")
    )
    monkeypatch.setenv(
        "GITHUB_CLIENT_SECRET",
        overrides.get("github_client_secret", "client_secret_from_env"),
    )


def test_reads_token_from_environment(monkeypatch):
    _set_required_env(monkeypatch)

    settings = Settings(_env_file=None)

    assert settings.github_token.get_secret_value() == "ghp_from_env"


def test_missing_token_fails_fast(monkeypatch):
    _set_required_env(monkeypatch)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)

    with pytest.raises(ValidationError) as exc_info:
        Settings(_env_file=None)

    assert "github_token" in str(exc_info.value)


def test_token_is_not_exposed_in_repr(monkeypatch):
    _set_required_env(monkeypatch, github_token="ghp_secret_value")

    settings = Settings(_env_file=None)

    assert "ghp_secret_value" not in repr(settings)


def test_reads_oauth_client_credentials_from_environment(monkeypatch):
    _set_required_env(
        monkeypatch,
        github_client_id="Iv1.client_id",
        github_client_secret="client_secret_value",
    )

    settings = Settings(_env_file=None)

    assert settings.github_client_id == "Iv1.client_id"
    assert settings.github_client_secret.get_secret_value() == "client_secret_value"


def test_client_secret_is_not_exposed_in_repr(monkeypatch):
    _set_required_env(monkeypatch, github_client_secret="client_secret_value")

    settings = Settings(_env_file=None)

    assert "client_secret_value" not in repr(settings)
