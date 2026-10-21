from urllib.parse import parse_qs, urlparse

import httpx

from backend.api import auth
from backend.api.auth import exchange_code_for_profile
from backend.services.jwt import decode_access_token


def test_login_redirects_to_github_with_matching_state_cookie(client):
    response = client.get("/auth/login", follow_redirects=False)

    assert response.status_code == 307

    location = urlparse(response.headers["location"])
    assert location.netloc == "github.com"
    assert location.path == "/login/oauth/authorize"

    query = parse_qs(location.query)
    state_in_url = query["state"][0]
    assert response.cookies["oauth_state"] == state_in_url


def test_callback_rejects_mismatched_state(client):
    client.cookies.set("oauth_state", "state-from-login")

    response = client.get(
        "/auth/callback",
        params={"code": "some-code", "state": "different-state"},
    )

    assert response.status_code == 400


def test_callback_sets_access_token_cookie_for_authenticated_user(client, monkeypatch):
    monkeypatch.setattr(
        auth,
        "exchange_code_for_profile",
        lambda code: {"id": 99, "login": "octocat", "name": "The Octocat"},
    )
    client.cookies.set("oauth_state", "matching-state")

    response = client.get(
        "/auth/callback",
        params={"code": "some-code", "state": "matching-state"},
    )

    assert response.status_code == 200
    token = response.cookies["access_token"]
    payload = decode_access_token(token)
    assert payload["sub"] == str(response.json()["user_id"])


def test_exchange_code_for_profile_returns_github_user():
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.host == "github.com":
            assert request.url.path == "/login/oauth/access_token"
            return httpx.Response(200, json={"access_token": "gho_test_token"})

        assert request.headers["Authorization"] == "Bearer gho_test_token"
        return httpx.Response(
            200, json={"id": 1, "login": "octocat", "name": "The Octocat"}
        )

    profile = exchange_code_for_profile(
        "some-code", transport=httpx.MockTransport(handler)
    )

    assert profile == {"id": 1, "login": "octocat", "name": "The Octocat"}
