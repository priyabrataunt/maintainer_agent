from typing import Any, Protocol

from pydantic import BaseModel, Field


class ToolCall(BaseModel):
    id: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)


class ModelTurn(BaseModel):
    """One model response: final text, or tool calls to run (text may accompany calls)."""

    text: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class AgentModel(Protocol):
    def step(self, messages: list[dict], tools: list[dict]) -> ModelTurn: ...


class ScriptedModel:
    """Fake model for tests: returns the scripted turns in order and records its inputs."""

    def __init__(self, turns: list[ModelTurn]) -> None:
        self.turns = list(turns)
        self.seen: list[list[dict]] = []

    def step(self, messages: list[dict], tools: list[dict]) -> ModelTurn:
        self.seen.append([dict(m) for m in messages])
        return self.turns.pop(0)
