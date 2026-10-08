from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from backend.api.auth import current_user
from backend.api.investigations import get_llm_provider
from backend.api.repositories import _get_repository_or_404
from backend.config import settings
from backend.db import get_db
from backend.llm.base import LLMProvider
from backend.models.user import User
from backend.retrieval.embedder import Embedder, get_embedder
from backend.services.duplicates import find_duplicates

router = APIRouter()


class DuplicateCheck(BaseModel):
    title: str = Field(min_length=1, max_length=500)
    body: str = Field(default="", max_length=20000)


class DuplicateRead(BaseModel):
    issue_number: int
    title: str
    state: str
    score: float
    is_duplicate: bool | None
    reason: str | None


@router.post("/repositories/{repository_id}/duplicates", response_model=list[DuplicateRead])
def check_duplicates(
    repository_id: int,
    payload: DuplicateCheck,
    db: Session = Depends(get_db),
    _user: User = Depends(current_user),
    embedder: Embedder = Depends(get_embedder),
    provider: LLMProvider = Depends(get_llm_provider),
):
    _get_repository_or_404(repository_id, db)
    found = find_duplicates(
        db, provider, embedder, repository_id, payload.title, payload.body,
        min_score=settings.retrieval_min_score,
    )
    return [DuplicateRead(**vars(d)) for d in found]
