from datetime import datetime

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class EvaluationCase(Base):
    __tablename__ = "evaluation_cases"

    id: Mapped[int] = mapped_column(primary_key=True)
    repository_id: Mapped[int] = mapped_column(ForeignKey("repositories.id"), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    expected_issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    expected_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    forbidden_tools: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    max_steps: Mapped[int] = mapped_column(nullable=False, default=8)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class EvaluationRun(Base):
    __tablename__ = "evaluation_runs"

    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    config: Mapped[dict] = mapped_column(JSONB, nullable=False, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )


class EvaluationResult(Base):
    __tablename__ = "evaluation_results"
    __table_args__ = (
        UniqueConstraint("run_id", "case_id"),
        Index("ix_evaluation_results_run_id", "run_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(
        ForeignKey("evaluation_runs.id", ondelete="CASCADE"), nullable=False
    )
    case_id: Mapped[int] = mapped_column(ForeignKey("evaluation_cases.id"), nullable=False)
    status: Mapped[str] = mapped_column(String, nullable=False)  # answered|no_result|rejected|error
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    cited_issues: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    tools_used: Mapped[list] = mapped_column(JSONB, nullable=False, default=list)
    steps: Mapped[int] = mapped_column(nullable=False, default=0)
    citation_correct: Mapped[bool] = mapped_column(Boolean, nullable=False)
    trajectory_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    judge_score: Mapped[int | None] = mapped_column(nullable=True)
    judge_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    latency_s: Mapped[float] = mapped_column(Float, nullable=False, default=0.0)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
