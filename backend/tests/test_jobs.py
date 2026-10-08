import contextlib
from datetime import datetime

import fakeredis
import httpx
import pytest
from rq import Queue
from sqlalchemy import select

from backend.config import settings
from backend.ingestion.github_client import GitHubClient
from backend.llm.fake import FakeProvider
from backend.main import app
from backend.models.document_chunk import DocumentChunk
from backend.models.issue import Issue
from backend.models.job import Job
from backend.models.repository import Repository
from backend.retrieval.embedder import HashEmbedder
from backend.retrieval.indexer import index_repository
from backend.services import jobs as jobs_module
from backend.services.jobs import (
    HANDLERS,
    IdempotencyConflict,
    PermanentJobError,
    QueueFull,
    enqueue_job,
    get_queue,
    run_job,
)


@pytest.fixture(autouse=True)
def job_deps(db_session, monkeypatch, tmp_path):
    @contextlib.contextmanager
    def session():
        yield db_session  # share the test transaction; the real worker opens its own

    monkeypatch.setattr(jobs_module.deps, "session_factory", session)
    monkeypatch.setattr(jobs_module.deps, "embedder", lambda: HashEmbedder())
    monkeypatch.setattr(jobs_module.deps, "data_dir", tmp_path)
    monkeypatch.setattr(settings, "job_max_retries", 2)
    monkeypatch.setattr(settings, "max_queue_depth", 50)


@pytest.fixture
def inline_queue():
    """Runs jobs immediately inside enqueue()."""
    return Queue("t", connection=fakeredis.FakeRedis(), is_async=False)


@pytest.fixture
def parked_queue():
    """Accepts jobs but never runs them, so they stay 'queued'."""
    return Queue("t", connection=fakeredis.FakeRedis())


@pytest.fixture
def counting_handler(monkeypatch):
    calls = []

    def handler(db, payload):
        calls.append(payload)
        return {"ok": True}

    monkeypatch.setitem(HANDLERS, "count", handler)
    return calls


# ---- enqueue + run ----


def test_job_runs_and_records_result(db_session, inline_queue):
    job, created = enqueue_job(db_session, inline_queue, "echo", {"x": 1})

    db_session.refresh(job)
    assert created and job.status == "succeeded"
    assert job.result == {"echo": {"x": 1}} and job.attempts == 1


def test_job_stays_queued_until_a_worker_picks_it_up(db_session, parked_queue):
    job, _ = enqueue_job(db_session, parked_queue, "echo", {})

    assert job.status == "queued" and job.attempts == 0
    assert parked_queue.count == 1


def test_unknown_kind_is_rejected(db_session, parked_queue):
    with pytest.raises(ValueError):
        enqueue_job(db_session, parked_queue, "rm -rf", {})


# ---- idempotency (9.9) ----


def test_same_key_returns_the_same_job_and_runs_once(
    db_session, inline_queue, counting_handler, user
):
    first, created1 = enqueue_job(db_session, inline_queue, "count", {"a": 1}, user.id, "key-1")
    second, created2 = enqueue_job(db_session, inline_queue, "count", {"a": 1}, user.id, "key-1")

    assert (created1, created2) == (True, False)
    assert first.id == second.id
    assert len(counting_handler) == 1


def test_same_key_with_different_request_conflicts(db_session, parked_queue):
    enqueue_job(db_session, parked_queue, "echo", {"a": 1}, None, "key-1")

    with pytest.raises(IdempotencyConflict):
        enqueue_job(db_session, parked_queue, "echo", {"a": 2}, None, "key-1")


def test_different_users_may_reuse_a_key(db_session, parked_queue, user):
    from backend.models.user import User

    other = User(github_id=99, login="other", avatar_url=None)
    db_session.add(other)
    db_session.flush()

    a, _ = enqueue_job(db_session, parked_queue, "echo", {}, user.id, "shared")
    b, created = enqueue_job(db_session, parked_queue, "echo", {}, other.id, "shared")

    assert created and a.id != b.id


def test_no_key_means_no_deduplication(db_session, parked_queue):
    a, _ = enqueue_job(db_session, parked_queue, "echo", {"a": 1})
    b, created = enqueue_job(db_session, parked_queue, "echo", {"a": 1})

    assert created and a.id != b.id


# ---- backpressure (9.11) ----


def test_full_queue_refuses_new_jobs(db_session, parked_queue, monkeypatch):
    monkeypatch.setattr(settings, "max_queue_depth", 2)
    enqueue_job(db_session, parked_queue, "echo", {"n": 1})
    enqueue_job(db_session, parked_queue, "echo", {"n": 2})

    with pytest.raises(QueueFull):
        enqueue_job(db_session, parked_queue, "echo", {"n": 3})
    assert parked_queue.count == 2


def test_replay_is_allowed_even_when_the_queue_is_full(db_session, parked_queue, monkeypatch):
    monkeypatch.setattr(settings, "max_queue_depth", 1)
    first, _ = enqueue_job(db_session, parked_queue, "echo", {}, None, "k")

    again, created = enqueue_job(db_session, parked_queue, "echo", {}, None, "k")

    assert again.id == first.id and not created


def test_finished_jobs_free_capacity(db_session, parked_queue, monkeypatch):
    monkeypatch.setattr(settings, "max_queue_depth", 1)
    job, _ = enqueue_job(db_session, parked_queue, "echo", {"n": 1})
    run_job(job.id)

    enqueue_job(db_session, parked_queue, "echo", {"n": 2})  # no QueueFull


def test_enqueue_failure_marks_job_failed(db_session):
    class BrokenQueue:
        def enqueue(self, *args, **kwargs):
            raise ConnectionError("redis is down")

    with pytest.raises(ConnectionError):
        enqueue_job(db_session, BrokenQueue(), "echo", {})

    (job,) = db_session.scalars(select(Job)).all()
    assert job.status == "failed" and "could not enqueue" in job.error


# ---- bounded retries (9.10) ----


def make_flaky(monkeypatch, failures: int, error=RuntimeError("boom")):
    state = {"calls": 0}

    def handler(db, payload):
        state["calls"] += 1
        if state["calls"] <= failures:
            raise error
        return {"done_on_attempt": state["calls"]}

    monkeypatch.setitem(HANDLERS, "flaky", handler)
    return state


def test_transient_failure_is_retried_then_succeeds(db_session, parked_queue, monkeypatch):
    make_flaky(monkeypatch, failures=1)
    job, _ = enqueue_job(db_session, parked_queue, "flaky", {})

    with pytest.raises(RuntimeError):
        run_job(job.id)  # attempt 1 fails; the queue would schedule attempt 2
    assert job.status == "queued" and "attempt 1 failed" in job.error
    run_job(job.id)

    assert job.status == "succeeded" and job.attempts == 2
    assert job.result == {"done_on_attempt": 2} and job.error is None


def test_retries_are_bounded_and_last_attempt_does_not_raise(db_session, parked_queue, monkeypatch):
    state = make_flaky(monkeypatch, failures=99)  # max_retries=2 -> 3 attempts total
    job, _ = enqueue_job(db_session, parked_queue, "flaky", {})

    with pytest.raises(RuntimeError):
        run_job(job.id)
    with pytest.raises(RuntimeError):
        run_job(job.id)
    run_job(job.id)  # final attempt: records failure, does not ask the queue to retry again

    assert job.status == "failed" and job.attempts == 3 and state["calls"] == 3
    assert "RuntimeError: boom" in job.error
    run_job(job.id)  # a stray redelivery does nothing
    assert state["calls"] == 3


def test_permanent_error_fails_immediately_without_retry(db_session, parked_queue, monkeypatch):
    state = make_flaky(monkeypatch, failures=99, error=PermanentJobError("bad input"))
    job, _ = enqueue_job(db_session, parked_queue, "flaky", {})

    run_job(job.id)  # does not raise

    assert job.status == "failed" and job.error == "bad input" and state["calls"] == 1


def test_finished_or_missing_jobs_are_not_rerun(db_session, parked_queue, counting_handler):
    job, _ = enqueue_job(db_session, parked_queue, "count", {})
    run_job(job.id)
    run_job(job.id)
    run_job("no-such-job")

    assert len(counting_handler) == 1


# ---- handlers ----

NOW = datetime(2026, 1, 1)


@pytest.fixture
def repo(db_session):
    repo = Repository(owner="o", name="r")
    db_session.add(repo)
    db_session.flush()
    for number, title, body in [
        (1, "Crash on startup", "segfault when config file is missing"),
        (2, "Add dark mode", "please support a dark theme"),
    ]:
        db_session.add(Issue(
            repository_id=repo.id, github_number=number, title=title, body=body,
            state="open", labels=[], created_at=NOW,
        ))
    db_session.flush()
    index_repository(db_session, repo.id, HashEmbedder())
    return repo


def test_investigation_job(db_session, inline_queue, repo, monkeypatch):
    monkeypatch.setattr(jobs_module.deps, "llm_provider", lambda: FakeProvider(["Config [#1]."]))
    monkeypatch.setattr(settings, "retrieval_min_score", 0.1)

    job, _ = enqueue_job(
        db_session, inline_queue, "investigation",
        {"repository_id": repo.id, "question": "why does startup crash"},
    )

    assert job.status == "succeeded"
    assert job.result["status"] == "answered" and job.result["citations"] == [1]


def test_investigation_job_without_llm_fails_permanently(db_session, inline_queue, repo):
    def no_llm():
        raise jobs_module.LLMNotConfigured("No LLM provider is configured")

    jobs_module.deps.llm_provider = no_llm
    try:
        job, _ = enqueue_job(
            db_session, inline_queue, "investigation", {"repository_id": repo.id, "question": "q"}
        )
    finally:
        jobs_module.deps.llm_provider = jobs_module.build_llm_provider

    assert job.status == "failed" and job.attempts == 1 and "No LLM" in job.error


def github_transport() -> httpx.MockTransport:
    comment = {
        "id": 7, "user": {"login": "bob"}, "body": "Same here on Linux",
        "created_at": "2026-01-02T00:00:00Z",
    }

    def handler(request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/repos/o/r":
            return httpx.Response(200, json={
                "name": "r", "description": "demo", "stargazers_count": 3,
            })
        if path == "/repos/o/r/issues":
            return httpx.Response(200, json=[{
                "number": 1, "title": "Crash on startup", "body": "segfault",
                "state": "open", "labels": [], "created_at": "2026-01-01T00:00:00Z",
            }])
        if path == "/repos/o/r/issues/1/comments":
            return httpx.Response(200, json=[comment])
        return httpx.Response(404)

    return httpx.MockTransport(handler)


def test_sync_job_runs_ingest_load_and_embed(db_session, inline_queue, monkeypatch, tmp_path):
    monkeypatch.setattr(
        jobs_module.deps, "github", lambda: GitHubClient(token="t", transport=github_transport())
    )
    fresh = Repository(owner="o", name="syncme")
    db_session.add(fresh)
    db_session.flush()
    # GitHub mock answers for o/r, so sync that repo name.
    job, _ = enqueue_job(db_session, inline_queue, "sync", {"owner": "o", "repo": "r"})

    assert job.status == "succeeded", job.error
    assert job.result["issues"] == 1 and job.result["issues_with_comments"] == 1
    assert job.result["chunks_created"] >= 1
    assert (tmp_path / "o_r" / "issues.json").exists()
    chunk = db_session.scalar(
        select(DocumentChunk).where(DocumentChunk.repository_id == job.result["repository_id"])
    )
    assert "Same here on Linux" in chunk.text  # the comment was embedded with its issue


def test_sync_job_reports_github_rate_limit_as_permanent(db_session, inline_queue, monkeypatch):
    def limited(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403, headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1893456000"}
        )

    monkeypatch.setattr(
        jobs_module.deps, "github",
        lambda: GitHubClient(token="t", transport=httpx.MockTransport(limited)),
    )

    job, _ = enqueue_job(db_session, inline_queue, "sync", {"owner": "o", "repo": "r"})

    assert job.status == "failed" and job.attempts == 1 and "rate limit" in job.error


# ---- API ----


@pytest.fixture
def api(client, repo, inline_queue, monkeypatch):
    monkeypatch.setattr(jobs_module.deps, "llm_provider", lambda: FakeProvider(["Config [#1]."]))
    monkeypatch.setattr(settings, "retrieval_min_score", 0.1)
    app.dependency_overrides[get_queue] = lambda: inline_queue
    yield client, repo
    app.dependency_overrides.pop(get_queue, None)


def post_job(client, repo, key=None, question="why does startup crash"):
    headers = {"Idempotency-Key": key} if key else {}
    return client.post(
        "/investigations", json={"repository_id": repo.id, "question": question}, headers=headers
    )


def test_post_returns_202_and_job_can_be_polled(api):
    client, repo = api

    response = post_job(client, repo)

    assert response.status_code == 202
    body = response.json()
    assert body["deduplicated"] is False
    job = client.get(f"/jobs/{body['job_id']}").json()
    assert job["status"] == "succeeded" and job["result"]["citations"] == [1]


def test_idempotency_key_returns_same_job(api):
    client, repo = api

    first = post_job(client, repo, key="abc")
    second = post_job(client, repo, key="abc")

    assert first.status_code == 202 and second.status_code == 200
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["deduplicated"] is True


def test_idempotency_key_reused_for_different_request_is_422(api):
    client, repo = api
    post_job(client, repo, key="abc")

    assert post_job(client, repo, key="abc", question="something else").status_code == 422


def test_full_queue_returns_429_with_retry_after(api, monkeypatch, inline_queue):
    client, repo = api
    app.dependency_overrides[get_queue] = lambda: Queue(
        "parked", connection=fakeredis.FakeRedis()
    )
    monkeypatch.setattr(settings, "max_queue_depth", 1)
    assert post_job(client, repo, question="first").status_code == 202

    response = post_job(client, repo, question="second")

    assert response.status_code == 429 and response.headers["retry-after"] == "30"


def test_unavailable_queue_returns_503(api):
    client, repo = api

    class Broken:
        def enqueue(self, *a, **k):
            raise ConnectionError("down")

    app.dependency_overrides[get_queue] = lambda: Broken()

    assert post_job(client, repo).status_code == 503


def test_unknown_repository_is_404(api):
    client, repo = api

    assert client.post(
        "/investigations", json={"repository_id": 999999, "question": "q"}
    ).status_code == 404


def test_endpoints_require_login(api):
    client, repo = api
    client.cookies.clear()

    assert post_job(client, repo).status_code == 401
    assert client.get("/jobs/whatever").status_code == 401
    assert client.post(f"/repositories/{repo.id}/sync").status_code == 401


def test_other_users_job_is_404(api, db_session):
    client, repo = api
    job_id = post_job(client, repo).json()["job_id"]
    job = db_session.get(Job, job_id)
    job.user_id = None
    db_session.flush()

    assert client.get(f"/jobs/{job_id}").status_code == 404


def test_sync_endpoint(api, monkeypatch):
    client, repo = api
    monkeypatch.setattr(
        jobs_module.deps, "github", lambda: GitHubClient(token="t", transport=github_transport())
    )

    response = client.post(f"/repositories/{repo.id}/sync")

    assert response.status_code == 202
    job = client.get(f"/jobs/{response.json()['job_id']}").json()
    assert job["kind"] == "sync" and job["status"] == "succeeded"


def test_sync_unknown_repository_is_404(api):
    client, _ = api

    assert client.post("/repositories/999999/sync").status_code == 404
