from dataclasses import dataclass, field
from typing import Protocol

from pydantic import BaseModel, Field

from backend.agent.tools import Tool, ToolExecution, ToolRegistry


class IssueWriter(Protocol):
    def post_comment(self, number: int, body: str) -> str: ...
    def add_label(self, number: int, label: str) -> str: ...
    def close_issue(self, number: int) -> str: ...


class InMemoryIssueWriter:
    """Records writes instead of calling GitHub; used in tests and demos."""

    def __init__(self) -> None:
        self.actions: list[tuple] = []

    def post_comment(self, number: int, body: str) -> str:
        self.actions.append(("post_comment", number, body))
        return f"Posted comment on #{number}"

    def add_label(self, number: int, label: str) -> str:
        self.actions.append(("add_label", number, label))
        return f"Added label '{label}' to #{number}"

    def close_issue(self, number: int) -> str:
        self.actions.append(("close_issue", number))
        return f"Closed #{number}"


class IssueNumber(BaseModel):
    number: int = Field(ge=1)


class CommentArgs(IssueNumber):
    body: str = Field(min_length=1)


class LabelArgs(IssueNumber):
    label: str = Field(min_length=1)


class SuggestLabelsArgs(IssueNumber):
    labels: list[str] = Field(min_length=1)


def build_write_registry(writer: IssueWriter) -> ToolRegistry:
    """Dry-run tools run freely; real writes are gated behind human confirmation."""
    registry = ToolRegistry()
    registry.register(Tool(
        "draft_comment", "Draft a comment for an issue. Nothing is posted.", CommentArgs,
        lambda number, body: f"DRAFT comment for #{number}:\n{body}",
    ))
    registry.register(Tool(
        "suggest_labels", "Suggest labels for an issue. Nothing is applied.", SuggestLabelsArgs,
        lambda number, labels: f"SUGGESTED labels for #{number}: {', '.join(labels)}",
    ))
    registry.register(Tool(
        "post_comment", "Post a comment on an issue (needs human approval).", CommentArgs,
        writer.post_comment, requires_confirmation=True,
    ))
    registry.register(Tool(
        "add_label", "Add a label to an issue (needs human approval).", LabelArgs,
        writer.add_label, requires_confirmation=True,
    ))
    registry.register(Tool(
        "close_issue", "Close an issue (needs human approval).", IssueNumber,
        writer.close_issue, requires_confirmation=True,
    ))
    return registry


@dataclass
class PendingAction:
    id: int
    name: str
    args: dict
    status: str = "pending"  # pending | confirmed | rejected
    result: str | None = None


@dataclass
class PendingActionStore:
    """In-memory queue of gated actions. A DB-backed version arrives with `investigations`."""

    actions: dict[int, PendingAction] = field(default_factory=dict)
    _next_id: int = 1

    def add_from(self, executions: list[ToolExecution]) -> list[PendingAction]:
        added = []
        for e in executions:
            if e.pending:
                action = PendingAction(self._next_id, e.name, e.args)
                self.actions[action.id] = action
                self._next_id += 1
                added.append(action)
        return added

    def confirm(self, action_id: int, registry: ToolRegistry) -> PendingAction:
        action = self._get_pending(action_id)
        execution = registry.execute(action.name, action.args, confirmed=True)
        action.status = "confirmed" if execution.ok else "pending"
        action.result = execution.output
        return action

    def reject(self, action_id: int) -> PendingAction:
        action = self._get_pending(action_id)
        action.status = "rejected"
        return action

    def _get_pending(self, action_id: int) -> PendingAction:
        action = self.actions.get(action_id)
        if action is None:
            raise KeyError(f"No pending action {action_id}")
        if action.status != "pending":
            raise ValueError(f"Action {action_id} is already {action.status}")
        return action
