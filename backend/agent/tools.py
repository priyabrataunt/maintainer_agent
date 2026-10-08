import time
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout
from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel, ValidationError

from backend.retrieval.budget import truncate_tool_output


class ToolFailure(Exception):
    """Raise from a tool to give the model a recoverable, human-readable error."""


@dataclass
class Tool:
    name: str
    description: str
    args_model: type[BaseModel]
    func: Callable[..., Any]
    timeout_s: float = 10.0
    requires_confirmation: bool = False

    def spec(self) -> dict:
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.args_model.model_json_schema(),
        }


@dataclass
class ToolExecution:
    name: str
    args: dict
    ok: bool
    output: str
    duration_s: float
    pending: bool = False


@dataclass
class ToolRegistry:
    tools: dict[str, Tool] = field(default_factory=dict)
    max_output_tokens: int = 1000

    def register(self, tool: Tool) -> None:
        self.tools[tool.name] = tool

    def restrict(self, allowed: set[str]) -> "ToolRegistry":
        """A per-request view containing only the allow-listed tools."""
        return ToolRegistry(
            {n: t for n, t in self.tools.items() if n in allowed}, self.max_output_tokens
        )

    def specs(self) -> list[dict]:
        return [t.spec() for t in self.tools.values()]

    def execute(self, name: str, args: dict, confirmed: bool = False) -> ToolExecution:
        """Run a tool; every failure becomes an error string the model can act on.

        Tools with `requires_confirmation` are not run unless `confirmed` is True;
        instead the call comes back with `pending=True` so a human can approve it.
        """
        tool = self.tools.get(name)
        if tool is not None and tool.requires_confirmation and not confirmed:
            output = (
                f"{name} needs human confirmation and has NOT run. It is queued as a "
                "pending action; do not call it again, and tell the user it awaits approval."
            )
            return ToolExecution(name, args, True, output, 0.0, pending=True)
        start = time.perf_counter()
        ok, output = self._run(name, args)
        output = truncate_tool_output(output, self.max_output_tokens)
        return ToolExecution(name, args, ok, output, time.perf_counter() - start)

    def _run(self, name: str, args: dict) -> tuple[bool, str]:
        tool = self.tools.get(name)
        if tool is None:
            available = ", ".join(sorted(self.tools)) or "none"
            return False, f"Error: unknown tool '{name}'. Available tools: {available}."
        try:
            parsed = tool.args_model.model_validate(args)
        except ValidationError as exc:
            problems = "; ".join(
                f"{'.'.join(map(str, e['loc'])) or 'args'}: {e['msg']}" for e in exc.errors()
            )
            return False, f"Error: invalid arguments for {name}: {problems}."

        pool = ThreadPoolExecutor(max_workers=1)
        future = pool.submit(tool.func, **parsed.model_dump())
        try:
            result = future.result(timeout=tool.timeout_s)
        except FutureTimeout:
            return False, f"Error: {name} timed out after {tool.timeout_s}s; narrow the request."
        except ToolFailure as exc:
            return False, f"Error: {exc}"
        except Exception as exc:  # a buggy tool must not crash the agent loop
            return False, f"Error: {name} failed unexpectedly ({type(exc).__name__})."
        finally:
            pool.shutdown(wait=False)
        return True, result if isinstance(result, str) else str(result)
