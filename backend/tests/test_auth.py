from urllib.parse import parse_qs, urlparse

import httpx
import respx
from sqlalchemy import select

from backend.config import settings
from backend.models.user import User
from backend.security import create_access_token, decode_access_token

TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"
PROFILE = {"id": 42, "login": "octocat", "avatar_url": "https://a/b.png"}


def test_login_redirects_to_github_with_state_cookie(anon_client):
    response = anon_client.get("/auth/login")

    assert response.status_code == 307
    location = urlparse(response.headers["location"])
    query = parse_qs(location.query)
    assert f"{location.scheme}://{location.netloc}{location.path}" == (
        "https://github.com/login/oauth/authorize"
    )
    assert query["state"][0] == response.cookies["oauth_state"]
    assert query["redirect_uri"] == [settings.github_oauth_redirect_uri]
    assert "httponly" in response.headers["set-cookie"].lower()


def test_login_state_is_random(anon_client):
    first = anon_client.get("/auth/login").cookies["oauth_state"]
    second = anon_client.get("/auth/login").cookies["oauth_state"]

    assert first != second


def test_callback_rejects_state_mismatch(anon_client):
    anon_client.cookies.set("oauth_state", "good")

    response = anon_client.get("/auth/callback", params={"code": "c", "state": "evil"})

    assert response.status_code == 400


def test_callback_rejects_missing_state_cookie(anon_client):
    response = anon_client.get("/auth/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 400


@respx.mock
def test_callback_creates_user_and_sets_jwt_cookie(anon_client, db_session):
    token_route = respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "gho_x"})
    )
    respx.get(USER_URL).mock(return_value=httpx.Response(200, json=PROFILE))
    anon_client.cookies.set("oauth_state", "s1")

    response = anon_client.get("/auth/callback", params={"code": "abc", "state": "s1"})

    assert response.status_code == 303
    assert b"code=abc" in token_route.calls.last.request.content
    user = db_session.scalar(select(User).where(User.github_id == 42))
    assert user.login == "octocat"
    token = response.cookies["access_token"]
    assert decode_access_token(token) == user.id
    assert "httponly" in response.headers["set-cookie"].lower()


@respx.mock
def test_callback_twice_reuses_user_and_updates_profile(anon_client, db_session):
    respx.post(TOKEN_URL).mock(return_value=httpx.Response(200, json={"access_token": "t"}))
    user_route = respx.get(USER_URL)
    for login in ("octocat", "renamed"):
        user_route.mock(return_value=httpx.Response(200, json={**PROFILE, "login": login}))
        anon_client.cookies.set("oauth_state", "s")
        anon_client.get("/auth/callback", params={"code": "c", "state": "s"})

    users = db_session.scalars(select(User).where(User.github_id == 42)).all()
    assert [u.login for u in users] == ["renamed"]


@respx.mock
def test_callback_github_rejects_code(anon_client):
    respx.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"error": "bad_verification_code"})
    )
    anon_client.cookies.set("oauth_state", "s")

    response = anon_client.get("/auth/callback", params={"code": "c", "state": "s"})

    assert response.status_code == 400


def test_me_requires_login(anon_client):
    assert anon_client.get("/me").status_code == 401


def test_me_returns_current_user(client, user):
    response = client.get("/me")

    assert response.status_code == 200
    assert response.json()["login"] == "octocat"


def test_me_rejects_garbage_token(anon_client):
    anon_client.cookies.set("access_token", "not-a-jwt")

    assert anon_client.get("/me").status_code == 401


def test_me_rejects_token_signed_with_other_secret(anon_client, user, monkeypatch):
    token = create_access_token(user.id)
    monkeypatch.setattr(settings, "jwt_secret", type(settings.jwt_secret)("other-" + "y" * 32))
    anon_client.cookies.set("access_token", token)

    assert anon_client.get("/me").status_code == 401


def test_repository_writes_require_login(anon_client, client):
    created = client.post("/repositories", json={"owner": "o", "name": "n"})
    repo_id = created.json()["id"]
    client.cookies.clear()

    assert anon_client.post("/repositories", json={"owner": "o", "name": "m"}).status_code == 401
    assert anon_client.patch(f"/repositories/{repo_id}", json={"name": "x"}).status_code == 401
    assert anon_client.delete(f"/repositories/{repo_id}").status_code == 401
    assert anon_client.get(f"/repositories/{repo_id}").status_code == 200


def test_cookies_are_secure_when_configured(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "cookie_secure", True)

    response = anon_client.get("/auth/login")

    assert "secure" in response.headers["set-cookie"].lower()


def test_cookies_are_not_secure_by_default_for_local_http(anon_client):
    response = anon_client.get("/auth/login")

    assert "secure" not in response.headers["set-cookie"].lower()
