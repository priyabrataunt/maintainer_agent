from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.auth import current_user
from backend.api.repositories import _get_repository_or_404
from backend.config import settings
from backend.db import get_db
from backend.llm.base import LLMProvider
from backend.llm.http_providers import AnthropicProvider, OpenAIProvider
from backend.llm.wrappers import FallbackProvider, RetryingProvider
from backend.models.user import User
from backend.retrieval.embedder import Embedder, get_embedder
from backend.services.investigation import run_investigation

router = APIRouter()


class InvestigationCreate(BaseModel):
    question: str = Field(min_length=1, max_length=2000)


class CitationRead(BaseModel):
    issue_number: int
    title: str


class InvestigationRead(BaseModel):
    id: int
    status: str
    answer: str
    citations: list[CitationRead]


def get_llm_provider() -> LLMProvider:
    """Anthropic first, OpenAI as fallback, each retried; 503 if no key is configured."""
    providers: list[LLMProvider] = []
    if settings.anthropic_api_key.get_secret_value():
        providers.append(RetryingProvider(AnthropicProvider()))
    if settings.openai_api_key.get_secret_value():
        providers.append(RetryingProvider(OpenAIProvider()))
    if not providers:
        raise HTTPException(status_code=503, detail="No LLM provider is configured")
    return FallbackProvider(providers)


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
        citations=[CitationRead(issue_number=h.issue_number, title=h.title) for h in outcome.cited],
    )
