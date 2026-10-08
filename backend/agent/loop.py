from dataclasses import dataclass, field

from backend.agent.tools import ToolExecution, ToolRegistry
from backend.agent.types import AgentModel

DEFAULT_MAX_STEPS = 8
PARTIAL_NOTICE = "I hit the step limit before finishing. Partial findings so far:\n"


@dataclass
class AgentState:
    messages: list[dict]
    steps: int = 0
    executions: list[ToolExecution] = field(default_factory=list)


@dataclass
class AgentResult:
    answer: str
    steps: int
    partial: bool
    executions: list[ToolExecution]


def run_agent(
    model: AgentModel,
    registry: ToolRegistry,
    question: str,
    system_prompt: str = "You help maintainers investigate GitHub issues. Use the tools.",
    max_steps: int = DEFAULT_MAX_STEPS,
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
        state.steps += 1
        turn = model.step(state.messages, specs)
        if not turn.tool_calls:
            return AgentResult(turn.text, state.steps, False, state.executions)

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

    findings = "\n".join(
        f"- {e.name}({e.args}): {e.output[:200]}" for e in state.executions if e.ok
    )
    return AgentResult(PARTIAL_NOTICE + findings, state.steps, True, state.executions)
