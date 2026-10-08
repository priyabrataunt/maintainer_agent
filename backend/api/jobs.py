import asyncio
import json
from collections.abc import AsyncIterator, Callable
from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from fastapi.concurrency import run_in_threadpool
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field
from rq import Queue
from sqlalchemy.orm import Session

from backend.api.auth import current_user
from backend.api.repositories import _get_repository_or_404
from backend.db import get_db
from backend.models.job import Job
from backend.models.user import User
from backend.services.jobs import IdempotencyConflict, QueueFull, deps, enqueue_job, get_queue

router = APIRouter()


class InvestigationJobCreate(BaseModel):
    repository_id: int
    question: str = Field(min_length=1, max_length=2000)


class JobAccepted(BaseModel):
    job_id: str
    status: str
    deduplicated: bool


class JobRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    kind: str
    status: str
    attempts: int
    result: dict | None
    error: str | None
    created_at: datetime
    updated_at: datetime


def _accept(db, queue, kind, payload, user, idempotency_key, response) -> JobAccepted:
    try:
        job, created = enqueue_job(db, queue, kind, payload, user.id, idempotency_key)
    except QueueFull as exc:
        raise HTTPException(
            status_code=429, detail=str(exc), headers={"Retry-After": "30"}
        ) from exc
    except IdempotencyConflict as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Job queue is unavailable") from exc
    response.status_code = 202 if created else 200
    return JobAccepted(job_id=job.id, status=job.status, deduplicated=not created)


@router.post("/investigations", response_model=JobAccepted, status_code=202)
def enqueue_investigation(
    payload: InvestigationJobCreate,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    queue: Queue = Depends(get_queue),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    _get_repository_or_404(payload.repository_id, db)
    body = {
        "repository_id": payload.repository_id,
        "question": payload.question,
        "user_id": user.id,
    }
    return _accept(db, queue, "investigation", body, user, idempotency_key, response)


@router.post("/repositories/{repository_id}/sync", response_model=JobAccepted, status_code=202)
def enqueue_sync(
    repository_id: int,
    response: Response,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
    queue: Queue = Depends(get_queue),
    idempotency_key: str | None = Header(default=None, max_length=200),
):
    repo = _get_repository_or_404(repository_id, db)
    body = {"owner": repo.owner, "repo": repo.name}
    return _accept(db, queue, "sync", body, user, idempotency_key, response)


@router.get("/jobs/{job_id}", response_model=JobRead)
def get_job(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.get(Job, job_id)
    # Another user's job looks the same as a missing one.
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


# ---- live status over Server-Sent Events ----

TERMINAL_STATUSES = ("succeeded", "failed")


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data)}\n\n"


async def stream_job_events(
    read_state: Callable[[], dict | None],
    poll_interval_s: float = 0.5,
    heartbeat_every_s: float = 15.0,
    max_seconds: float = 600.0,
) -> AsyncIterator[str]:
    """Yield SSE frames: `status` when the status/attempts change, a keep-alive comment while
    waiting, and a final `done` (or `timeout`) event, after which the stream ends."""
    elapsed = since_heartbeat = 0.0
    last: tuple | None = None
    while elapsed <= max_seconds:
        state = await run_in_threadpool(read_state)
        if state is None:
            yield _sse("error", {"detail": "Job not found"})
            return
        marker = (state["status"], state["attempts"])
        if marker != last:
            last = marker
            since_heartbeat = 0.0
            yield _sse("status", {"status": state["status"], "attempts": state["attempts"]})
        if state["status"] in TERMINAL_STATUSES:
            yield _sse("done", state)
            return
        if since_heartbeat >= heartbeat_every_s:
            since_heartbeat = 0.0
            yield ": keep-alive\n\n"
        await asyncio.sleep(poll_interval_s)
        elapsed += poll_interval_s
        since_heartbeat += poll_interval_s
    yield _sse("timeout", {"detail": "Still running; poll GET /jobs/{id} for the result"})


@router.get("/jobs/{job_id}/events")
async def job_events(
    job_id: str,
    db: Session = Depends(get_db),
    user: User = Depends(current_user),
):
    job = db.get(Job, job_id)
    if job is None or job.user_id != user.id:
        raise HTTPException(status_code=404, detail="Job not found")

    def read_state() -> dict | None:
        with deps.session_factory() as session:
            current = session.get(Job, job_id)
            if current is None:
                return None
            session.refresh(current)  # see updates committed by the worker
            return JobRead.model_validate(current).model_dump(mode="json")

    return StreamingResponse(
        stream_job_events(read_state),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
    )
