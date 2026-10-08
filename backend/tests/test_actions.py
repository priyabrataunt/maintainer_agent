import json
from datetime import datetime

import httpx
import pytest
from sqlalchemy import select

from backend.agent.github_writer import GitHubIssueWriter
from backend.agent.issue_tools import InMemoryIssueStore, IssueRecord, build_issue_registry
from backend.agent.loop import run_agent
from backend.agent.types import ModelTurn, ScriptedModel
from backend.agent.types import ToolCall as ModelToolCall
from backend.agent.write_tools import InMemoryIssueWriter, build_write_registry
from backend.api.actions import get_registry_factory
from backend.main import app
from backend.models.agent_run import PendingAction, ToolCall
from backend.models.investigation import Investigation
from backend.models.repository import Repository
from backend.services.actions import (
    ActionAlreadyResolved,
    confirm_action,
    persist_agent_run,
    reject_action,
)


@pytest.fixture
def investigation(db_session, user):
    repo = Repository(owner="octo", name="demo")
    db_session.add(repo)
    db_session.flush()
    inv = Investigation(
        repository_id=repo.id, user_id=user.id, question="q", status="answered", answer="a"
    )
    db_session.add(inv)
    db_session.flush()
    return inv


def combined_registry(writer):
    registry = build_issue_registry(InMemoryIssueStore([IssueRecord(number=5, title="Stale bug")]))
    for tool in build_write_registry(writer).tools.values():
        registry.register(tool)
    return registry


def agent_run(writer):
    model = ScriptedModel([
        ModelTurn(tool_calls=[
            ModelToolCall(id="1", name="search_issues", args={"query": "stale"})
        ]),
        ModelTurn(tool_calls=[ModelToolCall(id="2", name="get_issue", args={"number": 999})]),
        ModelTurn(tool_calls=[ModelToolCall(id="3", name="close_issue", args={"number": 5})]),
        ModelTurn(text="Proposed closing #5."),
    ])
    return run_agent(model, combined_registry(writer), "close stale issues")


def test_tool_calls_are_persisted(db_session, investigation):
    persist_agent_run(db_session, investigation.id, agent_run(InMemoryIssueWriter()))

    calls = db_session.scalars(select(ToolCall).order_by(ToolCall.id)).all()
    assert [(c.name, c.ok) for c in calls] == [
        ("search_issues", True), ("get_issue", False), ("close_issue", True),
    ]
    assert calls[0].args == {"query": "stale"}  # as sent by the model
    assert calls[0].result_size > 0 and calls[0].duration_s >= 0


def test_only_gated_calls_become_pending_actions(db_session, investigation):
    pending = persist_agent_run(db_session, investigation.id, agent_run(InMemoryIssueWriter()))

    assert [(a.tool_name, a.status) for a in pending] == [("close_issue", "pending")]


def test_confirm_runs_the_write_exactly_once(db_session, investigation):
    writer = InMemoryIssueWriter()
    (action,) = persist_agent_run(db_session, investigation.id, agent_run(writer))
    assert writer.actions == []

    done = confirm_action(db_session, investigation.id, action.id, build_write_registry(writer))

    assert done.status == "confirmed" and done.resolved_at is not None
    assert writer.actions == [("close_issue", 5)]
    with pytest.raises(ActionAlreadyResolved):
        confirm_action(db_session, investigation.id, action.id, build_write_registry(writer))
    assert len(writer.actions) == 1


def test_failed_write_is_marked_failed(db_session, investigation):
    class Broken(InMemoryIssueWriter):
        def close_issue(self, number):
            raise RuntimeError("boom")

    (action,) = persist_agent_run(db_session, investigation.id, agent_run(InMemoryIssueWriter()))

    done = confirm_action(db_session, investigation.id, action.id, build_write_registry(Broken()))

    assert done.status == "failed" and "failed unexpectedly" in done.result


def test_reject_never_runs_the_write(db_session, investigation):
    writer = InMemoryIssueWriter()
    (action,) = persist_agent_run(db_session, investigation.id, agent_run(writer))

    assert reject_action(db_session, investigation.id, action.id).status == "rejected"

    with pytest.raises(ActionAlreadyResolved):
        confirm_action(db_session, investigation.id, action.id, build_write_registry(writer))
    assert writer.actions == []


def test_action_of_another_investigation_is_not_found(db_session, investigation):
    other = Investigation(
        repository_id=investigation.repository_id, question="q", status="answered", answer="a"
    )
    db_session.add(other)
    db_session.flush()
    (action,) = persist_agent_run(db_session, investigation.id, agent_run(InMemoryIssueWriter()))

    registry = build_write_registry(InMemoryIssueWriter())
    assert confirm_action(db_session, other.id, action.id, registry) is None


@pytest.fixture
def api(db_session, investigation, client):
    writer = InMemoryIssueWriter()
    seen = {}

    def factory():
        def build(owner, repo, user):
            seen["target"] = (owner, repo, user.login)
            return build_write_registry(writer)

        return build

    app.dependency_overrides[get_registry_factory] = factory
    (action,) = persist_agent_run(db_session, investigation.id, agent_run(writer))
    yield client, investigation, action, writer, seen
    app.dependency_overrides.pop(get_registry_factory, None)


def test_endpoint_lists_actions(api):
    client, investigation, action, _, _ = api

    body = client.get(f"/investigations/{investigation.id}/actions").json()

    assert [(a["id"], a["tool_name"], a["status"]) for a in body] == [
        (action.id, "close_issue", "pending")
    ]


def test_endpoint_confirm_executes_against_the_investigations_repo(api):
    client, investigation, action, writer, seen = api

    response = client.post(
        f"/investigations/{investigation.id}/confirm",
        json={"action_id": action.id, "approve": True},
    )

    assert response.status_code == 200 and response.json()["status"] == "confirmed"
    assert writer.actions == [("close_issue", 5)]
    assert seen["target"] == ("octo", "demo", "octocat")


def test_endpoint_reject(api):
    client, investigation, action, writer, _ = api

    response = client.post(
        f"/investigations/{investigation.id}/confirm",
        json={"action_id": action.id, "approve": False},
    )

    assert response.json()["status"] == "rejected" and writer.actions == []


def test_endpoint_double_confirm_is_409(api):
    client, investigation, action, writer, _ = api
    body = {"action_id": action.id, "approve": True}
    client.post(f"/investigations/{investigation.id}/confirm", json=body)

    assert client.post(f"/investigations/{investigation.id}/confirm", json=body).status_code == 409
    assert len(writer.actions) == 1


def test_endpoint_unknown_action_is_404(api):
    client, investigation, _, _, _ = api

    assert client.post(
        f"/investigations/{investigation.id}/confirm", json={"action_id": 99999, "approve": True}
    ).status_code == 404


def test_endpoint_requires_login(api):
    client, investigation, action, _, _ = api
    client.cookies.clear()

    assert client.post(
        f"/investigations/{investigation.id}/confirm",
        json={"action_id": action.id, "approve": True},
    ).status_code == 401


def test_endpoint_other_users_investigation_is_404(api, db_session):
    client, investigation, action, writer, _ = api
    investigation.user_id = None
    db_session.flush()

    assert client.post(
        f"/investigations/{investigation.id}/confirm",
        json={"action_id": action.id, "approve": True},
    ).status_code == 404
    assert writer.actions == []


def test_confirm_fails_closed_without_write_access(db_session, investigation, client):
    (action,) = persist_agent_run(db_session, investigation.id, agent_run(InMemoryIssueWriter()))

    response = client.post(
        f"/investigations/{investigation.id}/confirm",
        json={"action_id": action.id, "approve": True},
    )

    assert response.status_code == 503
    assert db_session.get(PendingAction, action.id).status == "pending"


def test_github_writer_requests():
    requests: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        requests.append(request)
        return httpx.Response(200, json={})

    writer = GitHubIssueWriter("octo", "demo", "tok", httpx.MockTransport(handler))
    writer.post_comment(5, "hello")
    writer.add_label(5, "bug")
    writer.close_issue(5)

    assert [(r.method, r.url.path) for r in requests] == [
        ("POST", "/repos/octo/demo/issues/5/comments"),
        ("POST", "/repos/octo/demo/issues/5/labels"),
        ("PATCH", "/repos/octo/demo/issues/5"),
    ]
    assert requests[0].headers["Authorization"] == "Bearer tok"
    assert json.loads(requests[0].content) == {"body": "hello"}
    assert json.loads(requests[1].content) == {"labels": ["bug"]}
    assert json.loads(requests[2].content) == {"state": "closed"}


@pytest.mark.parametrize(
    "status,fragment", [(403, "denied"), (404, "could not find"), (500, "500")]
)
def test_github_writer_errors_are_recoverable(status, fragment):
    writer = GitHubIssueWriter(
        "o", "r", "t", httpx.MockTransport(lambda r: httpx.Response(status))
    )

    registry = build_write_registry(writer)
    result = registry.execute("close_issue", {"number": 5}, confirmed=True)

    assert not result.ok and fragment in result.output


def test_model_calls_are_linked_to_their_investigation(db_session, user):
    from backend.llm.fake import FakeProvider
    from backend.models.issue import Issue
    from backend.models.model_call import ModelCall
    from backend.retrieval.embedder import HashEmbedder
    from backend.retrieval.indexer import index_repository
    from backend.services.investigation import run_investigation

    repo = Repository(owner="x", name="y")
    db_session.add(repo)
    db_session.flush()
    db_session.add(Issue(
        repository_id=repo.id, github_number=1, title="Crash on startup", body="segfault",
        state="open", labels=[], created_at=datetime(2026, 1, 1),
    ))
    db_session.flush()
    index_repository(db_session, repo.id, HashEmbedder())

    outcome = run_investigation(
        db_session, FakeProvider(["It is [#1]."]), HashEmbedder(), repo.id,
        "crash on startup", min_score=0.1,
    )

    call = db_session.scalar(select(ModelCall))
    assert call.investigation_id == outcome.investigation.id
