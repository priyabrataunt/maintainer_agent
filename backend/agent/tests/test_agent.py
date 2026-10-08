import time

import pytest
from pydantic import BaseModel

from backend.agent.issue_tools import InMemoryIssueStore, IssueRecord, build_issue_registry
from backend.agent.loop import run_agent
from backend.agent.tools import Tool, ToolRegistry
from backend.agent.types import ModelTurn, ScriptedModel, ToolCall

ISSUES = [
    IssueRecord(number=12, title="Crash on startup", body="segfault when config missing"),
    IssueRecord(number=30, title="Add dark mode", body="please", state="closed"),
]


def call(name: str, id: str = "c1", **args) -> ModelTurn:
    return ModelTurn(tool_calls=[ToolCall(id=id, name=name, args=args)])


@pytest.fixture
def registry():
    return build_issue_registry(InMemoryIssueStore(ISSUES))


def test_search_tool_executes(registry):
    result = registry.execute("search_issues", {"query": "crash"})

    assert result.ok
    assert "#12 [open] Crash on startup" in result.output


def test_one_round_trip_then_answer(registry):
    model = ScriptedModel([call("search_issues", query="crash"), ModelTurn(text="It is #12.")])

    result = run_agent(model, registry, "what crashes?")

    assert result.answer == "It is #12."
    assert result.steps == 2 and not result.partial
    # The tool result was sent back to the model on the second step.
    last = model.seen[1][-1]
    assert last["role"] == "tool" and "#12" in last["content"]


def test_loop_continues_until_model_stops_calling_tools(registry):
    model = ScriptedModel([
        call("search_issues", query="crash"),
        call("get_issue", number=12),
        ModelTurn(text="done"),
    ])

    result = run_agent(model, registry, "q")

    assert [e.name for e in result.executions] == ["search_issues", "get_issue"]
    assert result.steps == 3


def test_max_steps_returns_partial_answer(registry):
    model = ScriptedModel([call("search_issues", query="crash")] * 20)

    result = run_agent(model, registry, "q", max_steps=3)

    assert result.partial
    assert result.steps == 3
    assert len(model.seen) == 3
    assert "step limit" in result.answer and "#12" in result.answer


def test_unknown_tool_returns_recoverable_error(registry):
    result = registry.execute("delete_everything", {})

    assert not result.ok
    assert "unknown tool" in result.output and "search_issues" in result.output


def test_not_found_tells_model_what_to_do(registry):
    result = registry.execute("get_issue", {"number": 999})

    assert not result.ok
    assert "#999 not found; call search_issues first" in result.output


def test_invalid_args_are_returned_to_model(registry):
    result = registry.execute("get_issue", {"number": "abc"})

    assert not result.ok
    assert "invalid arguments for get_issue" in result.output and "number" in result.output


def test_model_can_recover_from_tool_error(registry):
    model = ScriptedModel([
        call("get_issue", number=999),
        call("search_issues", query="crash"),
        ModelTurn(text="found #12"),
    ])

    result = run_agent(model, registry, "q")

    assert result.answer == "found #12"
    assert [e.ok for e in result.executions] == [False, True]


def test_allow_list_hides_tools(registry):
    limited = registry.restrict({"search_issues"})

    assert [s["name"] for s in limited.specs()] == ["search_issues"]
    assert not limited.execute("get_issue", {"number": 12}).ok


def test_tool_timeout():
    class Args(BaseModel):
        pass

    registry = ToolRegistry()
    registry.register(Tool("slow", "sleeps", Args, lambda: time.sleep(1), timeout_s=0.05))

    result = registry.execute("slow", {})

    assert not result.ok and "timed out" in result.output


def test_crashing_tool_does_not_crash_agent():
    class Args(BaseModel):
        pass

    def boom():
        raise RuntimeError("secret internals")

    registry = ToolRegistry()
    registry.register(Tool("boom", "fails", Args, boom))

    result = registry.execute("boom", {})

    assert not result.ok
    assert "RuntimeError" in result.output and "secret internals" not in result.output


def test_huge_tool_output_is_truncated():
    class Args(BaseModel):
        pass

    registry = ToolRegistry(max_output_tokens=50)
    registry.register(Tool("big", "huge", Args, lambda: "x" * 10_000))

    result = registry.execute("big", {})

    assert result.output.endswith("tokens]") and "truncated" in result.output
    assert len(result.output) < 400
