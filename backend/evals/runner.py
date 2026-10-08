import json
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from backend.agent.loop import run_agent
from backend.agent.tools import ToolRegistry
from backend.agent.types import AgentModel
from backend.evals.judge import JudgeError, judge_answer
from backend.evals.scoring import citation_correct, score_trajectory
from backend.llm.base import LLMProvider
from backend.models.evaluation import EvaluationCase, EvaluationResult, EvaluationRun
from backend.models.model_call import ModelCall
from backend.retrieval.embedder import Embedder
from backend.services.investigation import extract_citations, run_investigation


@dataclass
class CaseOutcome:
    status: str  # answered | no_result | rejected
    answer: str
    cited: list[int]
    tools_used: list[str] = field(default_factory=list)
    steps: int = 0
    latency_s: float = 0.0
    cost_usd: float | None = None
    context: str = ""  # text the answerer saw, shown to the judge


AnswerFn = Callable[[EvaluationCase], CaseOutcome]


def rag_answer_fn(
    db: Session, provider: LLMProvider, embedder: Embedder, min_score: float = 0.2
) -> AnswerFn:
    """Evaluate the retrieve-then-answer pipeline (no tools, so no trajectory)."""

    def answer(case: EvaluationCase) -> CaseOutcome:
        start = time.perf_counter()
        outcome = run_investigation(
            db, provider, embedder, case.repository_id, case.question, min_score=min_score
        )
        investigation = outcome.investigation
        cost = db.scalar(
            select(func.sum(ModelCall.cost_usd)).where(
                ModelCall.investigation_id == investigation.id
            )
        )
        return CaseOutcome(
            status=investigation.status,
            answer=investigation.answer or "",
            cited=[h.issue_number for h in outcome.cited],
            latency_s=time.perf_counter() - start,
            cost_usd=float(cost) if cost is not None else None,
            context="\n\n".join(h.text for h in outcome.cited),
        )

    return answer


def agent_answer_fn(model: AgentModel, registry: ToolRegistry) -> AnswerFn:
    """Evaluate the tool-using agent loop, including its trajectory."""

    def answer(case: EvaluationCase) -> CaseOutcome:
        start = time.perf_counter()
        result = run_agent(model, registry, case.question, max_steps=case.max_steps)
        return CaseOutcome(
            status="partial" if result.partial else "answered",
            answer=result.answer,
            cited=extract_citations(result.answer),
            tools_used=[e.name for e in result.executions],
            steps=result.steps,
            latency_s=time.perf_counter() - start,
            context="\n".join(e.output for e in result.executions if e.ok),
        )

    return answer


def load_cases(db: Session, repository_id: int, path: Path) -> list[EvaluationCase]:
    """Insert cases from a JSON list of {question, expected_issues, ...} objects."""
    cases = []
    for item in json.loads(path.read_text()):
        case = EvaluationCase(
            repository_id=repository_id,
            question=item["question"],
            expected_issues=item.get("expected_issues", []),
            expected_tools=item.get("expected_tools", []),
            forbidden_tools=item.get("forbidden_tools", []),
            max_steps=item.get("max_steps", 8),
        )
        db.add(case)
        cases.append(case)
    db.commit()
    return cases


def run_eval(
    db: Session,
    name: str,
    model_label: str,
    cases: list[EvaluationCase],
    answer_fn: AnswerFn,
    judge_provider: LLMProvider | None = None,
    config: dict | None = None,
) -> EvaluationRun:
    """Answer every case, score it, and store one result row per case."""
    run = EvaluationRun(name=name, model=model_label, config=config or {})
    db.add(run)
    db.flush()

    for case in cases:
        try:
            outcome = answer_fn(case)
        except Exception as exc:  # one broken case must not abort the whole run
            outcome = CaseOutcome(status="error", answer=f"{type(exc).__name__}: {exc}", cited=[])

        has_trajectory_expectations = bool(case.expected_tools or case.forbidden_tools)
        trajectory = (
            score_trajectory(
                outcome.tools_used, outcome.steps, case.expected_tools,
                case.forbidden_tools, case.max_steps,
            ).ok
            if has_trajectory_expectations and outcome.status != "error"
            else None
        )

        judge_score = judge_reason = None
        if judge_provider is not None and outcome.status in ("answered", "partial"):
            try:
                verdict = judge_answer(
                    judge_provider, case.question, outcome.answer, outcome.context
                )
                judge_score, judge_reason = verdict.score, verdict.reason
            except JudgeError as exc:
                judge_reason = f"judge failed: {exc}"[:500]

        db.add(EvaluationResult(
            run_id=run.id,
            case_id=case.id,
            status=outcome.status,
            answer=outcome.answer,
            cited_issues=outcome.cited,
            tools_used=outcome.tools_used,
            steps=outcome.steps,
            citation_correct=outcome.status != "error"
            and citation_correct(case.expected_issues, outcome.cited),
            trajectory_ok=trajectory,
            judge_score=judge_score,
            judge_reason=judge_reason,
            latency_s=outcome.latency_s,
            cost_usd=outcome.cost_usd,
        ))
    db.commit()
    return run
