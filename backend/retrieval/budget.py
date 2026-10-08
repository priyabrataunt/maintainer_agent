import logging
from dataclasses import dataclass, field

from backend.retrieval.tokens import count_tokens

logger = logging.getLogger("backend.retrieval.budget")


class BudgetExceeded(Exception):
    """The fixed slots (system prompt, history, tool outputs) alone exceed the budget."""


@dataclass(frozen=True)
class ScoredChunk:
    text: str
    score: float


@dataclass
class BudgetResult:
    chunks: list[ScoredChunk]
    dropped_chunks: list[ScoredChunk]
    breakdown: dict[str, int] = field(default_factory=dict)

    @property
    def total_tokens(self) -> int:
        return sum(self.breakdown.values())


def truncate_tool_output(text: str, max_tokens: int) -> str:
    """Cut `text` to about `max_tokens`, appending a marker saying how much was removed."""
    total = count_tokens(text)
    if total <= max_tokens:
        return text
    kept = text[: max(max_tokens, 0) * 4]
    removed = total - count_tokens(kept)
    return f"{kept}…[truncated {removed:,} tokens]"


def fit_to_budget(
    *,
    system_prompt: str,
    chunks: list[ScoredChunk],
    history: list[str],
    tool_outputs: list[str],
    max_tokens: int,
) -> BudgetResult:
    """Keep the highest-scoring chunks that fit alongside the fixed slots.

    System prompt, history and tool outputs are never dropped here (callers
    truncate tool outputs and compact history); chunks are dropped lowest score
    first. Kept chunks retain their original order.
    """
    fixed = {
        "system": count_tokens(system_prompt),
        "history": sum(count_tokens(h) for h in history),
        "tool_outputs": sum(count_tokens(t) for t in tool_outputs),
    }
    remaining = max_tokens - sum(fixed.values())
    if remaining < 0:
        raise BudgetExceeded(
            f"fixed slots use {sum(fixed.values())} tokens, over budget of {max_tokens}"
        )

    keep: set[int] = set()
    by_score = sorted(range(len(chunks)), key=lambda i: chunks[i].score, reverse=True)
    for i in by_score:
        cost = count_tokens(chunks[i].text)
        if cost <= remaining:
            keep.add(i)
            remaining -= cost
        # A chunk that doesn't fit is skipped; smaller lower-scoring ones may still fit.

    kept = [c for i, c in enumerate(chunks) if i in keep]
    dropped = [c for i, c in enumerate(chunks) if i not in keep]
    breakdown = {**fixed, "chunks": sum(count_tokens(c.text) for c in kept)}
    logger.info(
        "context_budget max=%d used=%d breakdown=%s chunks_kept=%d chunks_dropped=%d",
        max_tokens, sum(breakdown.values()), breakdown, len(kept), len(dropped),
    )
    return BudgetResult(chunks=kept, dropped_chunks=dropped, breakdown=breakdown)
