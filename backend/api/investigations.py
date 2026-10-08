from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.api.auth import current_user
from backend.api.repositories import _get_repository_or_404
from backend.config import settings
from backend.db import get_db
from backend.llm.base import LLMProvider
from backend.llm.factory import LLMNotConfigured, build_llm_provider
from backend.models.investigation import Investigation, InvestigationMessage
from backend.models.user import User
from backend.retrieval.embedder import Embedder, get_embedder
from backend.services.conversation import follow_up
from backend.services.investigation import run_investigation

router = APIRouter()


class InvestigationCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class CitationRead(BaseModel):
    issue_number: int
    title: str
    state: str | None = None


class InvestigationRead(BaseModel):
    id: int
    status: str
    answer: str
    citations: list[CitationRead]


def get_llm_provider() -> LLMProvider:
    try:
        return build_llm_provider()
    except LLMNotConfigured as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post(
    "/repositories/{repository_id}/investigations",
    response_model=InvestigationRead,
    status_code=201,
)
def create_investigation(
    repository_id: int,
    payload: InvestigationCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    embedder: Embedder = Depends(get_embedder),
    provider: LLMProvider = Depends(get_llm_provider),
):
    _get_repository_or_404(repository_id, db)
    outcome = run_investigation(
        db, provider, embedder, repository_id, payload.question,
        user_id=user.id, min_score=settings.retrieval_min_score,
    )
    investigation = outcome.investigation
    return InvestigationRead(
        id=investigation.id,
        status=investigation.status,
        answer=investigation.answer,
        citations=[
            CitationRead(issue_number=h.issue_number, title=h.title, state=h.state)
            for h in outcome.cited
        ],
    )


class FollowUpCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class MessageRead(BaseModel):
    role: str
    content: str


def _get_own_investigation(investigation_id: int, db: Session, user: User) -> Investigation:
    investigation = db.get(Investigation, investigation_id)
    # Someone else's investigation looks the same as a missing one.
    if investigation is None or investigation.user_id != user.id:
        raise HTTPException(status_code=404, detail="Investigation not found")
    return investigation


@router.post("/investigations/{investigation_id}/messages", response_model=InvestigationRead)
def ask_follow_up(
    investigation_id: int,
    payload: FollowUpCreate,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    embedder: Embedder = Depends(get_embedder),
    provider: LLMProvider = Depends(get_llm_provider),
):
    investigation = _get_own_investigation(investigation_id, db, user)
    outcome = follow_up(
        db, provider, embedder, investigation, payload.question,
        min_score=settings.retrieval_min_score,
        history_budget_tokens=settings.history_budget_tokens,
    )
    return InvestigationRead(
        id=outcome.investigation_id,
        status=outcome.status,
        answer=outcome.answer,
        citations=[
            CitationRead(issue_number=h.issue_number, title=h.title, state=h.state)
            for h in outcome.cited
        ],
    )


@router.get("/investigations/{investigation_id}/messages", response_model=list[MessageRead])
def list_messages(
    investigation_id: int,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    _get_own_investigation(investigation_id, db, user)
    rows = db.scalars(
        select(InvestigationMessage)
        .where(InvestigationMessage.investigation_id == investigation_id)
        .order_by(InvestigationMessage.id)
    )
    return [MessageRead(role=r.role, content=r.content) for r in rows if r.role != "summary"]
