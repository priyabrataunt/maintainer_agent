import contextlib
import uuid
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from redis import Redis
from rq import Queue, Retry
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.config import settings
from backend.db import SessionLocal
from backend.ingestion.github_client import GitHubClient, RateLimitExceeded
from backend.ingestion.storage import DATA_DIR
from backend.llm.base import LLMProvider
from backend.llm.factory import LLMNotConfigured, build_llm_provider
from backend.models.job import Job
from backend.models.repository import Repository
from backend.retrieval.embedder import Embedder, get_embedder
from backend.services.investigation import run_investigation
from backend.services.sync import sync_repository

ACTIVE_STATUSES = ("queued", "running")


class QueueFull(Exception):
    pass


class IdempotencyConflict(Exception):
    """The same Idempotency-Key was reused for a different request."""


class PermanentJobError(Exception):
    """A failure that retrying cannot fix (bad input, missing configuration)."""


@dataclass
class Deps:
    """What handlers need from the outside world; tests swap these for fakes."""

    session_factory: Callable[[], contextlib.AbstractContextManager[Session]] = SessionLocal
    llm_provider: Callable[[], LLMProvider] = build_llm_provider
    embedder: Callable[[], Embedder] = get_embedder
    github: Callable[[], GitHubClient] = GitHubClient
    data_dir: Path = field(default=DATA_DIR)


deps = Deps()


def retry_delays() -> list[int]:
    return [int(d) for d in settings.job_retry_delays_s.split(",") if d.strip()]


def get_queue() -> Queue:
    return Queue("maintainer", connection=Redis.from_url(settings.redis_url))


# ---- handlers: kind -> fn(db, payload) -> result dict ----


def _echo(db: Session, payload: dict) -> dict:
    return {"echo": payload}


def _investigation(db: Session, payload: dict) -> dict:
    try:
        provider = deps.llm_provider()
    except LLMNotConfigured as exc:
        raise PermanentJobError(str(exc)) from exc
    if db.get(Repository, payload["repository_id"]) is None:
        raise PermanentJobError("Repository not found")
    outcome = run_investigation(
        db, provider, deps.embedder(), payload["repository_id"], payload["question"],
        user_id=payload.get("user_id"), min_score=settings.retrieval_min_score,
    )
    investigation = outcome.investigation
    return {
        "investigation_id": investigation.id,
        "status": investigation.status,
        "answer": investigation.answer,
        "citations": [h.issue_number for h in outcome.cited],
    }


def _sync(db: Session, payload: dict) -> dict:
    try:
        with deps.github() as github:
            return sync_repository(
                db, github, deps.embedder(), payload["owner"], payload["repo"],
                data_dir=deps.data_dir,
            )
    except RateLimitExceeded as exc:
        raise PermanentJobError(f"GitHub rate limit exceeded; resets at {exc.reset_at}") from exc


HANDLERS: dict[str, Callable[[Session, dict], dict]] = {
    "echo": _echo,
    "investigation": _investigation,
    "sync": _sync,
}


# ---- enqueueing ----


def _active_count(db: Session) -> int:
    return db.scalar(select(func.count(Job.id)).where(Job.status.in_(ACTIVE_STATUSES))) or 0


def _find_by_key(db: Session, user_id: int | None, key: str) -> Job | None:
    return db.scalar(select(Job).where(Job.user_id == user_id, Job.idempotency_key == key))


def enqueue_job(
    db: Session,
    queue: Queue,
    kind: str,
    payload: dict[str, Any],
    user_id: int | None = None,
    idempotency_key: str | None = None,
) -> tuple[Job, bool]:
    """Create a job and queue it. Returns (job, created).

    The same user sending the same Idempotency-Key gets the original job back instead of a
    duplicate (409-style IdempotencyConflict if the request differs). A full queue refuses
    new work but never refuses a replay of work already accepted.
    """
    if kind not in HANDLERS:
        raise ValueError(f"Unknown job kind: {kind}")

    if idempotency_key:
        existing = _find_by_key(db, user_id, idempotency_key)
        if existing is not None:
            return _replay(existing, kind, payload), False

    if _active_count(db) >= settings.max_queue_depth:
        raise QueueFull(f"Queue is full ({settings.max_queue_depth} jobs waiting or running)")

    job = Job(
        id=str(uuid.uuid4()), kind=kind, user_id=user_id, idempotency_key=idempotency_key,
        payload=payload, status="queued",
    )
    db.add(job)
    try:
        db.commit()
    except IntegrityError:
        # A concurrent request with the same key won the race; return its job.
        db.rollback()
        existing = _find_by_key(db, user_id, idempotency_key or "")
        if existing is None:
            raise
        return _replay(existing, kind, payload), False

    delays = retry_delays()
    retry = None
    if settings.job_max_retries:
        retry = Retry(max=settings.job_max_retries, interval=delays)
    try:
        queue.enqueue(run_job, job.id, job_id=job.id, retry=retry)
    except Exception as exc:
        job.status = "failed"
        job.error = f"could not enqueue: {type(exc).__name__}"
        db.commit()
        raise
    return job, True


def _replay(existing: Job, kind: str, payload: dict) -> Job:
    if existing.kind != kind or existing.payload != payload:
        raise IdempotencyConflict("Idempotency-Key was already used for a different request")
    return existing


# ---- the worker side ----


def run_job(job_id: str) -> None:
    """Worker entry point. Records status, retries transient failures, never raises on the
    final attempt (so the queue does not retry beyond the bound)."""
    max_attempts = 1 + settings.job_max_retries
    with deps.session_factory() as db:
        job = db.get(Job, job_id)
        if job is None or job.status in ("succeeded", "failed"):
            return  # unknown or already finished: running it again would duplicate work
        job.status = "running"
        job.attempts += 1
        db.commit()

        try:
            result = HANDLERS[job.kind](db, job.payload)
        except PermanentJobError as exc:
            db.rollback()
            _finish(db, job, "failed", error=str(exc))
            return
        except Exception as exc:
            db.rollback()
            if job.attempts >= max_attempts:
                _finish(db, job, "failed", error=f"{type(exc).__name__}: {exc}"[:1000])
                return
            job.status = "queued"
            job.error = f"attempt {job.attempts} failed: {type(exc).__name__}: {exc}"[:1000]
            db.commit()
            raise  # lets RQ schedule the next attempt after its backoff delay
        _finish(db, job, "succeeded", result=result)


def _finish(
    db: Session,
    job: Job,
    status: str,
    result: dict | None = None,
    error: str | None = None,
) -> None:
    job.status = status
    job.result = result
    job.error = error
    db.commit()
