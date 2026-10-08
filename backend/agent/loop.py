from dataclasses import dataclass, field

from backend.agent.tools import ToolExecution, ToolRegistry
from backend.agent.types import AgentModel
from backend.retrieval.budget import truncate_tool_output
from backend.retrieval.tokens import count_tokens

DEFAULT_MAX_STEPS = 8
PARTIAL_NOTICE = "I hit the step limit before finishing. Partial findings so far:\n"


@dataclass
class AgentState:
    messages: list[dict]
    steps: int = 0
    executions: list[ToolExecution] = field(default_factory=list)
    tokens_in: int = 0

    @property
    def pending_actions(self) -> list[ToolExecution]:
        return [e for e in self.executions if e.pending]


@dataclass
class AgentResult:
    answer: str
    steps: int
    partial: bool
    executions: list[ToolExecution]
    tokens_in: int = 0
    pending_actions: list[ToolExecution] = field(default_factory=list)


def context_tokens(messages: list[dict]) -> int:
    return sum(count_tokens(str(m.get("content", ""))) for m in messages)


def apply_budget(messages: list[dict], max_tokens: int, shrink_to: int = 50) -> bool:
    """Shrink the oldest tool results until the context fits; False if it still doesn't.

    The system prompt, the question and assistant turns are never altered.
    """
    for message in messages:
        if context_tokens(messages) <= max_tokens:
            return True
        if message["role"] == "tool":
            message["content"] = truncate_tool_output(message["content"], shrink_to)
    return context_tokens(messages) <= max_tokens


def run_agent(
    model: AgentModel,
    registry: ToolRegistry,
    question: str,
    system_prompt: str = "You help maintainers investigate GitHub issues. Use the tools.",
    max_steps: int = DEFAULT_MAX_STEPS,
    max_context_tokens: int = 8000,
) -> AgentResult:
    """Call the model, run any tools it requests, feed results back; stop when it answers.

    Each model call is one step. If `max_steps` is reached while the model still
    wants tools, return a partial answer built from the tool results gathered.
    """
    state = AgentState(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": question},
        ]
    )
    specs = registry.specs()

    while state.steps < max_steps:
        if not apply_budget(state.messages, max_context_tokens):
            return _partial("I ran out of context budget. Partial findings so far:\n", state)
        state.steps += 1
        state.tokens_in += context_tokens(state.messages)
        turn = model.step(state.messages, specs)
        if not turn.tool_calls:
            return _result(turn.text, state, partial=False)

        state.messages.append({
            "role": "assistant",
            "content": turn.text,
            "tool_calls": [c.model_dump() for c in turn.tool_calls],
        })
        for call in turn.tool_calls:
            execution = registry.execute(call.name, call.args)
            state.executions.append(execution)
            state.messages.append({
                "role": "tool",
                "tool_call_id": call.id,
                "name": call.name,
                "content": execution.output,
            })

    return _partial(PARTIAL_NOTICE, state)


def _result(answer: str, state: AgentState, partial: bool) -> AgentResult:
    return AgentResult(
        answer, state.steps, partial, state.executions, state.tokens_in, state.pending_actions
    )


def _partial(notice: str, state: AgentState) -> AgentResult:
    findings = "\n".join(
        f"- {e.name}({e.args}): {e.output[:200]}" for e in state.executions if e.ok
    )
    return _result(notice + findings, state, partial=True)
