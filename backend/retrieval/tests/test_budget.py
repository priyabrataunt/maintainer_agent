import pytest

from backend.retrieval.budget import (
    BudgetExceeded,
    ScoredChunk,
    fit_to_budget,
    truncate_tool_output,
)
from backend.retrieval.tokens import count_tokens


def chunk(text_tokens: int, score: float) -> ScoredChunk:
    return ScoredChunk(text="x" * (text_tokens * 4), score=score)


def fit(chunks, max_tokens, system="s" * 40, history=(), tool_outputs=()):
    return fit_to_budget(
        system_prompt=system,
        chunks=chunks,
        history=list(history),
        tool_outputs=list(tool_outputs),
        max_tokens=max_tokens,
    )


def test_everything_fits_keeps_all_chunks():
    result = fit([chunk(10, 0.9), chunk(10, 0.5)], max_tokens=100)

    assert len(result.chunks) == 2
    assert result.dropped_chunks == []


def test_drops_lowest_scoring_chunk_first():
    low, mid, high = chunk(30, 0.1), chunk(30, 0.5), chunk(30, 0.9)

    # system = 10 tokens; room for two 30-token chunks.
    result = fit([low, high, mid], max_tokens=75)

    assert result.chunks == [high, mid]
    assert result.dropped_chunks == [low]


def test_kept_chunks_preserve_original_order():
    a, b, c = chunk(10, 0.3), chunk(10, 0.9), chunk(10, 0.6)

    result = fit([a, b, c], max_tokens=100)

    assert result.chunks == [a, b, c]


def test_oversized_high_score_chunk_does_not_block_smaller_ones():
    big, small = chunk(100, 0.99), chunk(5, 0.1)

    result = fit([big, small], max_tokens=50)

    assert result.chunks == [small]
    assert result.dropped_chunks == [big]


def test_breakdown_accounts_for_every_slot():
    result = fit(
        [chunk(10, 1.0)],
        max_tokens=200,
        history=["h" * 80],
        tool_outputs=["t" * 40],
    )

    assert result.breakdown == {"system": 10, "history": 20, "tool_outputs": 10, "chunks": 10}
    assert result.total_tokens == 50


def test_fixed_slots_over_budget_raises():
    with pytest.raises(BudgetExceeded):
        fit([], max_tokens=5, history=["h" * 400])


def test_budget_breakdown_is_logged(caplog):
    caplog.set_level("INFO", logger="backend.retrieval.budget")

    fit([chunk(10, 1.0)], max_tokens=100)

    assert "context_budget" in caplog.text
    assert "chunks_kept=1" in caplog.text


def test_truncate_leaves_short_output_alone():
    assert truncate_tool_output("short", 100) == "short"


def test_truncate_cuts_and_reports_removed_tokens():
    text = "a" * 4000  # 1000 tokens

    result = truncate_tool_output(text, 200)

    assert result.startswith("a" * 800)
    assert result.endswith("…[truncated 800 tokens]")
    assert count_tokens(result.split("…")[0]) == 200
