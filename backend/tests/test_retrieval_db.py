from datetime import datetime

import httpx
import pytest
from fastapi.testclient import TestClient
from sqlalchemy import func, select, text

from backend.db import get_db
from backend.main import app
from backend.models.document_chunk import EMBEDDING_DIM, DocumentChunk
from backend.models.issue import Issue
from backend.models.issue_comment import IssueComment
from backend.models.repository import Repository
from backend.retrieval.documents import build_issue_document
from backend.retrieval.embedder import Embedder, HashEmbedder, OpenAIEmbedder, get_embedder
from backend.retrieval.indexer import index_issue, index_repository
from backend.retrieval.search import search_chunks

NOW = datetime(2026, 1, 1)


class CountingEmbedder:
    def __init__(self) -> None:
        self.inner = HashEmbedder()
        self.texts_embedded = 0

    def embed(self, texts: list[str]) -> list[list[float]]:
        self.texts_embedded += len(texts)
        return self.inner.embed(texts)


@pytest.fixture
def repo(db_session):
    repo = Repository(owner="o", name="r")
    db_session.add(repo)
    db_session.flush()
    return repo


def add_issue(db, repo, number, title, body="", state="open") -> Issue:
    issue = Issue(
        repository_id=repo.id, github_number=number, title=title, body=body,
        state=state, labels=[], created_at=NOW,
    )
    db.add(issue)
    db.flush()
    return issue


@pytest.fixture
def issues(db_session, repo):
    return [
        add_issue(db_session, repo, 1, "Crash on startup", "segfault when config file missing"),
        add_issue(db_session, repo, 2, "Add dark mode", "please support a dark theme"),
        add_issue(db_session, repo, 3, "Login broken", "oauth redirect fails", state="closed"),
    ]


def test_document_contains_title_body_and_comments_in_order(db_session, issues):
    issue = issues[0]
    later = IssueComment(issue_id=issue.id, github_comment_id=2, user_login="b", body="second",
                         created_at=datetime(2026, 1, 3))
    earlier = IssueComment(issue_id=issue.id, github_comment_id=1, user_login="a", body="first",
                           created_at=datetime(2026, 1, 2))

    doc = build_issue_document(issue, [later, earlier])

    assert doc.startswith("Crash on startup\n\nsegfault")
    assert doc.index("@a: first") < doc.index("@b: second")


def test_hash_embedder_is_deterministic_and_normalised():
    embedder = HashEmbedder()
    (a,) = embedder.embed(["crash on startup"])
    (b,) = embedder.embed(["crash on startup"])

    assert a == b and len(a) == EMBEDDING_DIM
    assert sum(v * v for v in a) == pytest.approx(1.0)


def test_openai_embedder_orders_results_by_index():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"data": [
            {"index": 1, "embedding": [0.0, 1.0]}, {"index": 0, "embedding": [1.0, 0.0]},
        ]})

    embedder = OpenAIEmbedder("k", transport=httpx.MockTransport(handler))

    assert embedder.embed(["a", "b"]) == [[1.0, 0.0], [0.0, 1.0]]


def test_get_embedder_defaults_to_hash():
    assert isinstance(get_embedder(), HashEmbedder)


def test_index_issue_stores_chunk_with_metadata(db_session, issues):
    stats = index_issue(db_session, issues[0], HashEmbedder())

    assert stats.created == 1
    chunk = db_session.scalar(select(DocumentChunk))
    assert chunk.chunk_metadata == {"number": 1, "title": "Crash on startup"}
    assert chunk.source_type == "issue"
    assert len(chunk.embedding) == EMBEDDING_DIM


def test_reindexing_unchanged_issue_skips_embedding(db_session, issues):
    embedder = CountingEmbedder()
    index_issue(db_session, issues[0], embedder)

    stats = index_issue(db_session, issues[0], embedder)

    assert (stats.created, stats.updated, stats.skipped) == (0, 0, 1)
    assert embedder.texts_embedded == 1


def test_changed_issue_is_re_embedded_in_place(db_session, issues):
    embedder = CountingEmbedder()
    index_issue(db_session, issues[0], embedder)
    issues[0].body = "completely different body"

    stats = index_issue(db_session, issues[0], embedder)

    assert stats.updated == 1
    assert db_session.scalar(select(func.count(DocumentChunk.id))) == 1
    assert "completely different" in db_session.scalar(select(DocumentChunk.text))


def test_shrinking_issue_deletes_stale_chunks(db_session, issues):
    issue = issues[0]
    issue.body = " ".join(f"word{i}" for i in range(400))
    index_issue(db_session, issue, HashEmbedder(), max_tokens=50, overlap_tokens=5)
    before = db_session.scalar(select(func.count(DocumentChunk.id)))
    issue.body = "short"

    stats = index_issue(db_session, issue, HashEmbedder(), max_tokens=50, overlap_tokens=5)

    assert before > 1 and stats.deleted == before - 1
    assert db_session.scalar(select(func.count(DocumentChunk.id))) == 1


def test_index_repository_covers_all_issues(db_session, repo, issues):
    stats = index_repository(db_session, repo.id, HashEmbedder())

    assert stats.created == 3


def test_search_ranks_relevant_issue_first(db_session, repo, issues):
    index_repository(db_session, repo.id, HashEmbedder())

    hits = search_chunks(db_session, HashEmbedder(), repo.id, "app crashes at startup", k=3)

    assert hits[0].issue_number == 1
    assert hits[0].score > hits[-1].score


def test_search_respects_k(db_session, repo, issues):
    index_repository(db_session, repo.id, HashEmbedder())

    assert len(search_chunks(db_session, HashEmbedder(), repo.id, "dark", k=2)) == 2


def test_search_filters_by_state(db_session, repo, issues):
    index_repository(db_session, repo.id, HashEmbedder())

    hits = search_chunks(db_session, HashEmbedder(), repo.id, "login oauth", k=5, state="open")

    assert {h.state for h in hits} == {"open"}
    assert 3 not in {h.issue_number for h in hits}


def test_search_filters_by_source_type(db_session, repo, issues):
    index_repository(db_session, repo.id, HashEmbedder())

    assert search_chunks(db_session, HashEmbedder(), repo.id, "dark", source_type="comment") == []


def test_search_is_scoped_to_repository(db_session, repo, issues):
    other = Repository(owner="o", name="other")
    db_session.add(other)
    db_session.flush()
    index_repository(db_session, repo.id, HashEmbedder())

    assert search_chunks(db_session, HashEmbedder(), other.id, "dark") == []


def test_hnsw_index_is_used_for_nearest_neighbour_query(db_session):
    db_session.execute(text("SET LOCAL enable_seqscan = off"))
    vector = "[" + ",".join(["0.1"] * EMBEDDING_DIM) + "]"

    plan = "\n".join(
        row[0] for row in db_session.execute(text(
            "EXPLAIN SELECT id FROM document_chunks "
            f"ORDER BY embedding <=> '{vector}' LIMIT 5"
        ))
    )

    assert "ix_document_chunks_embedding_hnsw" in plan


@pytest.fixture
def search_client(db_session, repo, issues):
    index_repository(db_session, repo.id, HashEmbedder())
    app.dependency_overrides[get_db] = lambda: db_session
    app.dependency_overrides[get_embedder] = lambda: HashEmbedder()
    try:
        yield TestClient(app), repo
    finally:
        app.dependency_overrides.pop(get_db, None)
        app.dependency_overrides.pop(get_embedder, None)


def test_search_endpoint(search_client):
    client, repo = search_client

    response = client.get(f"/repositories/{repo.id}/search", params={"q": "dark theme", "k": 2})

    assert response.status_code == 200
    body = response.json()
    assert body[0]["issue_number"] == 2 and len(body) == 2
    assert set(body[0]) == {"issue_number", "title", "state", "text", "score"}


def test_search_endpoint_state_filter(search_client):
    client, repo = search_client

    body = client.get(
        f"/repositories/{repo.id}/search", params={"q": "login", "state": "closed"}
    ).json()

    assert [h["issue_number"] for h in body] == [3]


def test_search_endpoint_unknown_repository_is_404(search_client):
    client, _ = search_client

    assert client.get("/repositories/99999/search", params={"q": "x"}).status_code == 404


def test_search_endpoint_requires_query(search_client):
    client, repo = search_client

    assert client.get(f"/repositories/{repo.id}/search").status_code == 422


def test_embedder_protocol_is_satisfied():
    embedder: Embedder = HashEmbedder()
    assert embedder.embed([]) == []
