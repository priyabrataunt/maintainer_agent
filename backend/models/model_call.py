from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey, Index, Numeric, String, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.models.base import Base


class ModelCall(Base):
    __tablename__ = "model_calls"
    __table_args__ = (
        Index("ix_model_calls_created_at", "created_at"),
        Index("ix_model_calls_investigation_id", "investigation_id"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    provider: Mapped[str] = mapped_column(String, nullable=False)
    model: Mapped[str] = mapped_column(String, nullable=False)
    prompt_version_id: Mapped[int | None] = mapped_column(
        ForeignKey("prompt_versions.id"), nullable=True
    )
    investigation_id: Mapped[int | None] = mapped_column(
        ForeignKey(
            "investigations.id", ondelete="SET NULL", name="fk_model_calls_investigation_id"
        ),
        nullable=True,
    )
    status: Mapped[str] = mapped_column(String, nullable=False)  # ok | error
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    input_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    output_tokens: Mapped[int] = mapped_column(nullable=False, default=0)
    latency_s: Mapped[float] = mapped_column(Float, nullable=False)
    cost_usd: Mapped[float | None] = mapped_column(Numeric(12, 6), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, server_default=func.now()
    )
