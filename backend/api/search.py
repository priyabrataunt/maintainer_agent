from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from backend.api.repositories import _get_repository_or_404
from backend.db import get_db
from backend.retrieval.embedder import Embedder, get_embedder
from backend.retrieval.search import search_chunks

router = APIRouter()


class SearchHitRead(BaseModel):
    issue_number: int
    title: str
    state: str
    text: str
    score: float


@router.get("/repositories/{repository_id}/search", response_model=list[SearchHitRead])
def search_repository(
    repository_id: int,
    q: str = Query(min_length=1),
    k: int = Query(default=5, ge=1, le=50),
    state: str | None = None,
    source_type: str | None = None,
    db: Session = Depends(get_db),
    embedder: Embedder = Depends(get_embedder),
):
    _get_repository_or_404(repository_id, db)
    hits = search_chunks(db, embedder, repository_id, q, k, state, source_type)
    return [SearchHitRead(**{f: getattr(h, f) for f in SearchHitRead.model_fields}) for h in hits]
