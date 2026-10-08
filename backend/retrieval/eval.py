from collections.abc import Callable
from dataclasses import dataclass


@dataclass(frozen=True)
class EvalCase:
    query: str
    expected: frozenset[int]  # issue numbers that count as a correct answer


@dataclass
class CaseResult:
    case: EvalCase
    retrieved: list[int]
    hit: bool


@dataclass
class EvalReport:
    k: int
    results: list[CaseResult]

    @property
    def hit_rate(self) -> float:
        return sum(r.hit for r in self.results) / len(self.results) if self.results else 0.0

    @property
    def misses(self) -> list[CaseResult]:
        return [r for r in self.results if not r.hit]


def evaluate_retrieval(
    search: Callable[[str, int], list[int]], cases: list[EvalCase], k: int = 5
) -> EvalReport:
    """hit@k: the share of queries whose top-k results contain at least one expected issue."""
    results = []
    for case in cases:
        retrieved = search(case.query, k)[:k]
        results.append(CaseResult(case, retrieved, bool(case.expected & set(retrieved))))
    return EvalReport(k, results)
