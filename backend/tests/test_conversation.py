from datetime import datetime

import pytest
from sqlalchemy import select

from backend.api.investigations import get_llm_provider
from backend.llm.fake import FakeProvider
from backend.main import app
from backend.models.investigation import Citation, InvestigationMessage
from backend.models.issue import Issue
from backend.models.model_call import ModelCall
from backend.models.repository import Repository
from backend.models.user import User
from backend.retrieval.embedder import HashEmbedder, get_embedder
from backend.retrieval.indexer import index_repository
from backend.services.conversation import (
    active_history,
    compact_history,
    follow_up,
)
from backend.services.investigation import NO_RESULT_ANSWER, run_investigation

NOW = datetime(2026, 1, 1)


@pytest.fixture
def repo(db_session):
    repo = Repository(owner="o", name="r")
    db_session.add(repo)
    db_session.flush()
    for number, title, body in [
        (1, "Crash on startup", "segfault when config file is missing"),
        (2, "Add dark mode", "please support a dark theme"),
    ]:
        db_session.add(Issue(
            repository_id=repo.id, github_number=number, title=title, body=body,
            state="open", labels=[], created_at=NOW,
        ))
    db_session.flush()
    index_repository(db_session, repo.id, HashEmbedder())
    return repo


def start(db, repo, answer="It crashes when config is missing [#1].", user=None):
    outcome = run_investigation(
        db, FakeProvider([answer]), HashEmbedder(), repo.id, "why does startup crash",
        user_id=user.id if user else None, min_score=0.1,
    )
    return outcome.investigation


def ask(db, investigation, provider, question, **kw):
    return follow_up(
        db, provider, HashEmbedder(), investigation, question, min_score=0.1, **kw
    )


def rows(db, investigation):
    return db.scalars(
        select(InvestigationMessage)
        .where(InvestigationMessage.investigation_id == investigation.id)
        .order_by(InvestigationMessage.id)
    ).all()


def test_first_turn_is_stored_as_messages(db_session, repo):
    investigation = start(db_session, repo)

    assert [(r.role, r.content[:12]) for r in rows(db_session, investigation)] == [
        ("user", "why does sta"), ("assistant", "It crashes w"),
    ]


def test_follow_up_sends_history_before_new_question(db_session, repo):
    investigation = start(db_session, repo)
    provider = FakeProvider(["Dark mode is separate [#2]."])

    outcome = ask(db_session, investigation, provider, "what about dark mode theme")

    messages = provider.calls[0]
    assert [m.role for m in messages] == ["system", "user", "assistant", "user"]
    assert messages[1].content == "why does startup crash"
    assert "<question>\nwhat about dark mode theme" in messages[3].content
    assert outcome.status == "answered" and [h.issue_number for h in outcome.cited] == [2]
    assert [r.role for r in rows(db_session, investigation)] == ["user", "assistant"] * 2


def test_follow_up_adds_new_citation_without_duplicating_old(db_session, repo):
    investigation = start(db_session, repo)

    ask(db_session, investigation, FakeProvider(["Both [#1] and [#2]."]), "dark mode crash theme")

    numbers = db_session.scalars(select(Citation.issue_number).order_by(Citation.issue_number))
    assert list(numbers) == [1, 2]


def test_follow_up_may_cite_issue_from_earlier_turn(db_session, repo):
    investigation = start(db_session, repo)
    # Retrieval for this question surfaces only #2, but #1 was cited earlier.
    provider = FakeProvider(["Recall [#1], and now [#2]."])

    outcome = ask(db_session, investigation, provider, "dark theme please")

    assert outcome.status == "answered"


def test_follow_up_rejects_invented_citation(db_session, repo):
    investigation = start(db_session, repo)
    provider = FakeProvider(["Made up [#77].", "Again [#77]."])

    outcome = ask(db_session, investigation, provider, "dark theme please")

    assert outcome.status == "rejected"
    assert len(rows(db_session, investigation)) == 2  # failed turn is not stored


def test_follow_up_with_nothing_relevant_skips_llm(db_session, repo):
    investigation = start(db_session, repo)
    provider = FakeProvider([])

    outcome = follow_up(
        db_session, provider, HashEmbedder(), investigation, "zzzz qqqq", min_score=0.5
    )

    assert outcome.status == "no_result" and outcome.answer == NO_RESULT_ANSWER
    assert provider.calls == []


def fill_history(db, investigation, pairs=4, size=400):
    for i in range(pairs):
        db.add(InvestigationMessage(
            investigation_id=investigation.id, role="user", content=f"question {i} " + "q" * size
        ))
        db.add(InvestigationMessage(
            investigation_id=investigation.id, role="assistant", content=f"answer {i} " + "a" * size
        ))
    db.commit()


def test_no_compaction_under_budget(db_session, repo):
    investigation = start(db_session, repo)
    provider = FakeProvider([])

    assert compact_history(db_session, provider, investigation.id, budget_tokens=10_000) is False
    assert provider.calls == []


def test_compaction_triggers_over_budget_and_keeps_recent_turns(db_session, repo):
    investigation = start(db_session, repo)
    fill_history(db_session, investigation)
    provider = FakeProvider(["Notes: discussed #1 crash."])

    assert compact_history(db_session, provider, investigation.id, budget_tokens=500) is True

    summary, turns = active_history(db_session, investigation.id)
    assert summary == "Notes: discussed #1 crash."
    assert len(turns) == 2 and turns[-1].content.startswith("answer 3")
    assert "question 0" in provider.calls[0][1].content


def test_compaction_keeps_old_rows_for_audit(db_session, repo):
    investigation = start(db_session, repo)
    fill_history(db_session, investigation)
    total_before = len(rows(db_session, investigation))

    compact_history(db_session, FakeProvider(["notes"]), investigation.id, budget_tokens=500)

    all_rows = rows(db_session, investigation)
    assert len(all_rows) == total_before + 1
    assert sum(r.compacted for r in all_rows) == total_before - 2


def test_second_compaction_merges_previous_summary(db_session, repo):
    investigation = start(db_session, repo)
    fill_history(db_session, investigation)
    compact_history(db_session, FakeProvider(["first notes"]), investigation.id, 500)
    fill_history(db_session, investigation, pairs=3)
    provider = FakeProvider(["merged notes"])

    compact_history(db_session, provider, investigation.id, 500)

    assert "first notes" in provider.calls[0][1].content
    summary, _ = active_history(db_session, investigation.id)
    assert summary == "merged notes"
    live = [r for r in rows(db_session, investigation) if r.role == "summary" and not r.compacted]
    assert len(live) == 1


def test_follow_up_prompt_uses_summary_instead_of_old_turns(db_session, repo):
    investigation = start(db_session, repo)
    fill_history(db_session, investigation)
    compact_history(db_session, FakeProvider(["Notes: discussed #1."]), investigation.id, 500)
    provider = FakeProvider(["Dark theme [#2]."])

    ask(db_session, investigation, provider, "dark theme please", history_budget_tokens=10_000)

    system = provider.calls[0][0].content
    assert "Notes: discussed #1." in system
    assert all("question 0" not in m.content for m in provider.calls[0])


def test_follow_up_triggers_compaction_when_history_grows(db_session, repo):
    investigation = start(db_session, repo)
    fill_history(db_session, investigation)
    provider = FakeProvider(["Dark theme [#2].", "Compact notes"])

    ask(db_session, investigation, provider, "dark theme please", history_budget_tokens=500)

    assert len(provider.calls) == 2  # the answer, then the summarisation call
    summary, _ = active_history(db_session, investigation.id)
    assert summary == "Compact notes"
    assert len(db_session.scalars(select(ModelCall)).all()) >= 3


@pytest.fixture
def api(db_session, repo, client, user):
    app.dependency_overrides[get_embedder] = lambda: HashEmbedder()
    investigation = start(db_session, repo, user=user)
    state = {"provider": FakeProvider([])}
    app.dependency_overrides[get_llm_provider] = lambda: state["provider"]
    yield client, investigation, state
    app.dependency_overrides.pop(get_embedder, None)
    app.dependency_overrides.pop(get_llm_provider, None)


def test_endpoint_follow_up_and_history(api):
    client, investigation, state = api
    state["provider"] = FakeProvider(["Dark theme [#2]."])

    response = client.post(
        f"/investigations/{investigation.id}/messages", json={"question": "dark theme please"}
    )

    assert response.status_code == 200
    assert response.json()["citations"] == [
        {"issue_number": 2, "title": "Add dark mode", "state": "open"}
    ]
    history = client.get(f"/investigations/{investigation.id}/messages").json()
    assert [m["role"] for m in history] == ["user", "assistant", "user", "assistant"]


def test_endpoint_hides_other_users_investigations(api, db_session):
    client, investigation, _ = api
    other = User(github_id=2, login="mallory", avatar_url=None)
    db_session.add(other)
    db_session.flush()
    investigation.user_id = other.id
    db_session.flush()

    assert client.post(
        f"/investigations/{investigation.id}/messages", json={"question": "x"}
    ).status_code == 404
    assert client.get(f"/investigations/{investigation.id}/messages").status_code == 404


def test_endpoint_requires_login(api):
    client, investigation, _ = api
    client.cookies.clear()

    assert client.get(f"/investigations/{investigation.id}/messages").status_code == 401
    assert client.post(
        f"/investigations/{investigation.id}/messages", json={"question": "x"}
    ).status_code == 401
