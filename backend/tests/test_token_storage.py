import httpx
import pytest
from cryptography.fernet import Fernet
from pydantic import SecretStr
from sqlalchemy import text

from backend.agent.issue_tools import InMemoryIssueStore, IssueRecord, build_issue_registry
from backend.agent.loop import run_agent
from backend.agent.types import ModelTurn, ScriptedModel, ToolCall
from backend.agent.write_tools import InMemoryIssueWriter, build_write_registry
from backend.api.actions import get_github_transport
from backend.config import settings
from backend.main import app
from backend.models.investigation import Investigation
from backend.models.repository import Repository
from backend.models.user import User
from backend.security import (
    TokenStorageDisabled,
    decrypt_token,
    encrypt_token,
    token_storage_enabled,
)
from backend.services.actions import persist_agent_run

TOKEN_URL = "https://github.com/login/oauth/access_token"
USER_URL = "https://api.github.com/user"


@pytest.fixture
def key(monkeypatch):
    value = Fernet.generate_key().decode()
    monkeypatch.setattr(settings, "token_encryption_key", SecretStr(value))
    return value


# ---- encryption ----


def test_round_trip(key):
    encrypted = encrypt_token("gho_secret")

    assert encrypted != "gho_secret" and "gho_secret" not in encrypted
    assert decrypt_token(encrypted) == "gho_secret"


def test_encryption_is_not_deterministic(key):
    assert encrypt_token("t") != encrypt_token("t")


def test_wrong_key_cannot_decrypt(key, monkeypatch):
    encrypted = encrypt_token("gho_secret")
    monkeypatch.setattr(
        settings, "token_encryption_key", SecretStr(Fernet.generate_key().decode())
    )

    assert decrypt_token(encrypted) is None


def test_tampered_ciphertext_is_rejected(key):
    encrypted = encrypt_token("gho_secret")

    assert decrypt_token(encrypted[:-4] + "AAAA") is None


def test_disabled_without_a_key():
    assert not token_storage_enabled()
    with pytest.raises(TokenStorageDisabled):
        encrypt_token("t")


# ---- login stores the token only when it is safe and useful ----


def run_callback(client, respx_mock):
    respx_mock.post(TOKEN_URL).mock(
        return_value=httpx.Response(200, json={"access_token": "gho_plain"})
    )
    respx_mock.get(USER_URL).mock(
        return_value=httpx.Response(200, json={"id": 77, "login": "alice", "avatar_url": None})
    )
    client.cookies.set("oauth_state", "s")
    return client.get("/auth/callback", params={"code": "c", "state": "s"})


def stored_token(db_session):
    return db_session.execute(
        text("SELECT github_token_encrypted FROM users WHERE github_id = 77")
    ).scalar()


def test_token_encrypted_at_rest_when_writes_enabled(anon_client, db_session, key, monkeypatch):
    import respx

    monkeypatch.setattr(settings, "github_oauth_scopes", "read:user,public_repo")
    with respx.mock as mock:
        run_callback(anon_client, mock)

    stored = stored_token(db_session)
    assert stored and "gho_plain" not in stored
    assert decrypt_token(stored) == "gho_plain"


def test_token_not_stored_without_encryption_key(anon_client, db_session, monkeypatch):
    import respx

    monkeypatch.setattr(settings, "github_oauth_scopes", "read:user,public_repo")
    with respx.mock as mock:
        run_callback(anon_client, mock)

    assert stored_token(db_session) is None


def test_token_not_stored_for_read_only_scope(anon_client, db_session, key):
    import respx

    with respx.mock as mock:  # default scope is read:user
        run_callback(anon_client, mock)

    assert stored_token(db_session) is None


def test_login_requests_the_configured_scopes(anon_client, monkeypatch):
    monkeypatch.setattr(settings, "github_oauth_scopes", "read:user,public_repo")

    location = anon_client.get("/auth/login").headers["location"]

    assert "scope=read%3Auser%2Cpublic_repo" in location


def test_logout_forgets_the_stored_token(client, user, db_session, key):
    user.github_token_encrypted = encrypt_token("gho_plain")
    db_session.flush()

    response = client.post("/auth/logout")

    assert response.status_code == 204
    db_session.refresh(user)
    assert user.github_token_encrypted is None


def test_logout_requires_login(anon_client):
    assert anon_client.post("/auth/logout").status_code == 401


# ---- confirming a write acts as the user, on repos they own ----


def pending_close(db_session, user, owner="octo"):
    repo = Repository(owner=owner, name="demo")
    db_session.add(repo)
    db_session.flush()
    inv = Investigation(
        repository_id=repo.id, user_id=user.id, question="q", status="answered", answer="a"
    )
    db_session.add(inv)
    db_session.flush()
    registry = build_issue_registry(InMemoryIssueStore([IssueRecord(number=5, title="t")]))
    for tool in build_write_registry(InMemoryIssueWriter()).tools.values():
        registry.register(tool)
    model = ScriptedModel([
        ModelTurn(tool_calls=[ToolCall(id="1", name="close_issue", args={"number": 5})]),
        ModelTurn(text="proposed"),
    ])
    (action,) = persist_agent_run(db_session, inv.id, run_agent(model, registry, "close it"))
    return inv, action


class FakeGitHub:
    """Records requests and answers the repo-permission lookup."""

    def __init__(self, owner_login="octocat", admin=False, repo_status=200):
        self.requests: list[httpx.Request] = []
        self.owner_login, self.admin, self.repo_status = owner_login, admin, repo_status

    def __call__(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if request.method == "GET":
            return httpx.Response(self.repo_status, json={
                "owner": {"login": self.owner_login}, "permissions": {"admin": self.admin},
            })
        return httpx.Response(200, json={})


@pytest.fixture
def writable(client, user, db_session, key):
    user.github_token_encrypted = encrypt_token("gho_users_own_token")
    db_session.flush()
    return client


def confirm(client, inv, action):
    return client.post(
        f"/investigations/{inv.id}/confirm", json={"action_id": action.id, "approve": True}
    )


def use_github(fake):
    app.dependency_overrides[get_github_transport] = lambda: httpx.MockTransport(fake)


@pytest.fixture(autouse=True)
def _cleanup():
    yield
    app.dependency_overrides.pop(get_github_transport, None)


def test_owner_can_confirm_and_the_write_uses_their_token(writable, user, db_session):
    inv, action = pending_close(db_session, user, owner="octocat")
    fake = FakeGitHub(owner_login="octocat")
    use_github(fake)

    response = confirm(writable, inv, action)

    assert response.status_code == 200 and response.json()["status"] == "confirmed"
    write = fake.requests[-1]
    assert (write.method, write.url.path) == ("PATCH", "/repos/octocat/demo/issues/5")
    assert all(r.headers["Authorization"] == "Bearer gho_users_own_token" for r in fake.requests)


def test_admin_of_someone_elses_repo_can_confirm(writable, user, db_session):
    inv, action = pending_close(db_session, user, owner="org")
    use_github(FakeGitHub(owner_login="org", admin=True))

    assert confirm(writable, inv, action).status_code == 200


def test_non_owner_is_refused_and_nothing_is_written(writable, user, db_session):
    inv, action = pending_close(db_session, user, owner="someone-else")
    fake = FakeGitHub(owner_login="someone-else", admin=False)
    use_github(fake)

    response = confirm(writable, inv, action)

    assert response.status_code == 403 and "do not own or administer" in response.json()["detail"]
    assert [r.method for r in fake.requests] == ["GET"]  # only the permission lookup
    db_session.refresh(action)
    assert action.status == "pending"  # still pending: the owner may retry after fixing access


def test_owner_check_is_case_insensitive(writable, user, db_session):
    inv, action = pending_close(db_session, user, owner="OctoCat")
    use_github(FakeGitHub(owner_login="OCTOCAT"))

    assert confirm(writable, inv, action).status_code == 200


def test_repo_not_visible_to_the_token_is_refused(writable, user, db_session):
    inv, action = pending_close(db_session, user)
    use_github(FakeGitHub(repo_status=404))

    assert confirm(writable, inv, action).status_code == 403


def test_github_outage_while_verifying_is_502(writable, user, db_session):
    inv, action = pending_close(db_session, user)

    def down(request):
        raise httpx.ConnectError("unreachable")

    app.dependency_overrides[get_github_transport] = lambda: httpx.MockTransport(down)

    assert confirm(writable, inv, action).status_code == 502


def test_no_stored_token_asks_the_user_to_log_in_again(client, user, db_session, key):
    inv, action = pending_close(db_session, user)

    response = confirm(client, inv, action)

    assert response.status_code == 403 and "log in again" in response.json()["detail"]


def test_unreadable_stored_token_asks_to_log_in_again(client, user, db_session, key):
    user.github_token_encrypted = "not-a-real-ciphertext"
    db_session.flush()
    inv, action = pending_close(db_session, user)

    assert confirm(client, inv, action).status_code == 403


def test_server_without_encryption_key_reports_not_configured(client, user, db_session):
    inv, action = pending_close(db_session, user)

    assert confirm(client, inv, action).status_code == 503


def test_reject_needs_no_token_or_github_access(client, user, db_session):
    inv, action = pending_close(db_session, user)

    response = client.post(
        f"/investigations/{inv.id}/confirm", json={"action_id": action.id, "approve": False}
    )

    assert response.status_code == 200 and response.json()["status"] == "rejected"


def test_one_users_token_is_never_used_for_another_user(writable, user, db_session, key):
    other = User(github_id=555, login="mallory", avatar_url=None)
    other.github_token_encrypted = encrypt_token("gho_mallory")
    db_session.add(other)
    db_session.flush()
    inv, action = pending_close(db_session, user)
    inv.user_id = other.id  # the investigation belongs to someone else
    db_session.flush()

    assert confirm(writable, inv, action).status_code == 404
