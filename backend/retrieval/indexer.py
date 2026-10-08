import hashlib
from dataclasses import dataclass

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from backend.models.document_chunk import DocumentChunk
from backend.models.issue import Issue
from backend.models.issue_comment import IssueComment
from backend.retrieval.chunker import chunk_text
from backend.retrieval.documents import build_issue_document
from backend.retrieval.embedder import Embedder

SOURCE_TYPE = "issue"


@dataclass
class IndexStats:
    created: int = 0
    updated: int = 0
    skipped: int = 0
    deleted: int = 0

    def add(self, other: "IndexStats") -> None:
        self.created += other.created
        self.updated += other.updated
        self.skipped += other.skipped
        self.deleted += other.deleted


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode()).hexdigest()


def index_issue(
    db: Session,
    issue: Issue,
    embedder: Embedder,
    max_tokens: int = 200,
    overlap_tokens: int = 40,
) -> IndexStats:
    """Chunk, embed and store one issue; chunks whose text is unchanged are not re-embedded."""
    comments = db.scalars(select(IssueComment).where(IssueComment.issue_id == issue.id)).all()
    document = build_issue_document(issue, list(comments))
    chunks = chunk_text(document, max_tokens, overlap_tokens)

    existing = {
        c.chunk_index: c
        for c in db.scalars(
            select(DocumentChunk).where(
                DocumentChunk.issue_id == issue.id, DocumentChunk.source_type == SOURCE_TYPE
            )
        )
    }
    stats = IndexStats()
    changed = [
        i for i, text in enumerate(chunks)
        if i not in existing or existing[i].content_hash != _hash(text)
    ]
    stats.skipped = len(chunks) - len(changed)

    metadata = {"number": issue.github_number, "title": issue.title}
    vectors = embedder.embed([chunks[i] for i in changed]) if changed else []
    for i, vector in zip(changed, vectors, strict=True):
        if i in existing:
            row = existing[i]
            stats.updated += 1
        else:
            row = DocumentChunk(
                repository_id=issue.repository_id,
                issue_id=issue.id,
                source_type=SOURCE_TYPE,
                chunk_index=i,
            )
            db.add(row)
            stats.created += 1
        row.text = chunks[i]
        row.content_hash = _hash(chunks[i])
        row.embedding = vector
        row.chunk_metadata = metadata

    stale = [i for i in existing if i >= len(chunks)]
    if stale:
        db.execute(
            delete(DocumentChunk).where(
                DocumentChunk.issue_id == issue.id,
                DocumentChunk.source_type == SOURCE_TYPE,
                DocumentChunk.chunk_index.in_(stale),
            )
        )
        stats.deleted = len(stale)
    db.commit()
    return stats


def index_repository(db: Session, repository_id: int, embedder: Embedder) -> IndexStats:
    """Index every issue of a repository."""
    total = IndexStats()
    issues = db.scalars(
        select(Issue).where(Issue.repository_id == repository_id).order_by(Issue.id)
    ).all()
    for issue in issues:
        total.add(index_issue(db, issue, embedder))
    return total
