import pytest

from backend.agent.issue_tools import (
    CommitRecord,
    InMemoryIssueStore,
    PullRequestRecord,
    add_code_tools,
    build_issue_registry,
)
from backend.agent.loop import apply_budget
from backend.agent.types import ModelTurn, ScriptedModel, ToolCall
from backend.agent.write_tools import (
    InMemoryIssueWriter,
    PendingActionStore,
    build_write_registry,
)


def call(name: str, **args) -> ModelTurn:
    return ModelTurn(tool_calls=[ToolCall(id="c", name=name, args=args)])


@pytest.fixture
def writer():
    return InMemoryIssueWriter()


@pytest.fixture
def registry(writer):
    return build_write_registry(writer)


def test_dry_run_tools_have_no_side_effects(registry, writer):
    draft = registry.execute("draft_comment", {"number": 5, "body": "Thanks!"})
    labels = registry.execute("suggest_labels", {"number": 5, "labels": ["bug"]})

    assert draft.ok and not draft.pending and "DRAFT" in draft.output
    assert labels.ok and "bug" in labels.output
    assert writer.actions == []


@pytest.mark.parametrize("name,args", [
    ("post_comment", {"number": 5, "body": "hi"}),
    ("add_label", {"number": 5, "label": "bug"}),
    ("close_issue", {"number": 5}),
])
def test_gated_tools_do_not_run_without_confirmation(registry, writer, name, args):
    result = registry.execute(name, args)

    assert result.pending and result.ok
    assert "NOT run" in result.output
    assert writer.actions == []


def test_agent_run_returns_pending_actions_without_executing(registry, writer, run_agent):
    model = ScriptedModel([
        call("close_issue", number=5),
        ModelTurn(text="I proposed closing #5; awaiting approval."),
    ])

    result = run_agent(model, registry, "close the stale issue")

    assert [a.name for a in result.pending_actions] == ["close_issue"]
    assert writer.actions == []
    assert "NOT run" in model.seen[1][-1]["content"]


def test_confirm_runs_the_action_exactly_once(registry, writer, run_agent):
    model = ScriptedModel([call("add_label", number=5, label="bug"), ModelTurn(text="queued")])
    result = run_agent(model, registry, "label it")
    store = PendingActionStore()
    (action,) = store.add_from(result.executions)

    confirmed = store.confirm(action.id, registry)

    assert confirmed.status == "confirmed"
    assert writer.actions == [("add_label", 5, "bug")]
    with pytest.raises(ValueError):
        store.confirm(action.id, registry)
    assert len(writer.actions) == 1


def test_reject_prevents_execution(registry, writer, run_agent):
    result = run_agent(
        ScriptedModel([call("close_issue", number=5), ModelTurn(text="ok")]), registry, "q"
    )
    store = PendingActionStore()
    (action,) = store.add_from(result.executions)

    store.reject(action.id)

    assert action.status == "rejected"
    with pytest.raises(ValueError):
        store.confirm(action.id, registry)
    assert writer.actions == []


def test_confirm_unknown_action_raises(registry):
    with pytest.raises(KeyError):
        PendingActionStore().confirm(99, registry)


def test_allow_list_can_exclude_write_tools(registry, writer):
    read_only = registry.restrict({"draft_comment"})

    result = read_only.execute("close_issue", {"number": 5})

    assert not result.ok and not result.pending
    assert writer.actions == []


def test_gate_applies_before_argument_validation(registry):
    result = registry.execute("close_issue", {"number": 0})

    # The gate comes first; args are validated only when a human confirms.
    assert result.pending


def test_confirmed_execution_still_validates_args(registry, writer):
    result = registry.execute("close_issue", {"number": 0}, confirmed=True)

    assert not result.ok
    assert writer.actions == []


def test_apply_budget_shrinks_oldest_tool_outputs_first():
    messages = [
        {"role": "system", "content": "s"},
        {"role": "tool", "content": "a" * 4000},
        {"role": "tool", "content": "b" * 4000},
    ]

    assert apply_budget(messages, max_tokens=1200)

    assert "truncated" in messages[1]["content"]
    assert messages[2]["content"] == "b" * 4000


def test_apply_budget_reports_failure_when_cannot_fit():
    messages = [{"role": "user", "content": "q" * 4000}]

    assert not apply_budget(messages, max_tokens=10)


def test_agent_stops_with_partial_when_context_cannot_fit(run_agent):
    registry = build_issue_registry(InMemoryIssueStore([]))
    model = ScriptedModel([ModelTurn(text="never")])

    result = run_agent(model, registry, "q" * 4000, max_context_tokens=10)

    assert result.partial and "context budget" in result.answer
    assert model.seen == []


def test_agent_tracks_input_tokens(run_agent):
    registry = build_issue_registry(InMemoryIssueStore([]))
    result = run_agent(ScriptedModel([ModelTurn(text="hi")]), registry, "question")

    assert result.tokens_in > 0


def test_code_tools():
    class Store:
        def recent_commits(self, limit):
            return [CommitRecord(sha="abcdef123", message="Fix bug\n\nlong body")][:limit]

        def get_pr(self, number):
            return PullRequestRecord(number=3, title="Add x") if number == 3 else None

    registry = add_code_tools(build_issue_registry(InMemoryIssueStore([])), Store())

    assert registry.execute("list_recent_commits", {}).output == "abcdef1 Fix bug"
    assert "PR #3" in registry.execute("get_pr", {"number": 3}).output
    missing = registry.execute("get_pr", {"number": 9})
    assert not missing.ok and "PR #9 not found" in missing.output
