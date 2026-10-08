from dataclasses import dataclass

from sqlalchemy import select, text
from sqlalchemy.orm import Session

from backend.models.document_chunk import DocumentChunk
from backend.models.issue import Issue
from backend.retrieval.embedder import Embedder


@dataclass
class SearchHit:
    issue_id: int
    issue_number: int
    title: str
    state: str
    text: str
    score: float  # cosine similarity, 1.0 = identical direction


def search_chunks(
    db: Session,
    embedder: Embedder,
    repository_id: int,
    query: str,
    k: int = 5,
    state: str | None = None,
    source_type: str | None = None,
    ef_search: int = 200,
) -> list[SearchHit]:
    """Top-k chunks by cosine similarity, optionally filtered by issue state and source type.

    The HNSW index finds its nearest neighbours first and the repository/state filters are
    applied afterwards, so it can return fewer than k rows (or none) when most near
    neighbours belong to other repositories or dead index entries. A wider `ef_search`
    makes that rarer; when it still happens the query is repeated as an exact scan.
    """
    (query_vector,) = embedder.embed([query])
    distance = DocumentChunk.embedding.cosine_distance(query_vector)
    stmt = (
        select(DocumentChunk, Issue, distance.label("distance"))
        .join(Issue, Issue.id == DocumentChunk.issue_id)
        .where(DocumentChunk.repository_id == repository_id)
        .order_by(distance)
        .limit(k)
    )
    if state is not None:
        stmt = stmt.where(Issue.state == state)
    if source_type is not None:
        stmt = stmt.where(DocumentChunk.source_type == source_type)

    db.execute(text("SELECT set_config('hnsw.ef_search', :value, true)"), {"value": str(ef_search)})
    rows = db.execute(stmt).all()
    if len(rows) < k:
        db.execute(text("SET LOCAL enable_indexscan = off"))
        try:
            rows = db.execute(stmt).all()
        finally:
            db.execute(text("SET LOCAL enable_indexscan = on"))

    return [
        SearchHit(issue.id, issue.github_number, issue.title, issue.state, chunk.text, 1 - dist)
        for chunk, issue, dist in rows
    ]
