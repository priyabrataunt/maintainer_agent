from datetime import datetime

from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel, ConfigDict, Field
from rq import Queue
from sqlalchemy.orm import Session

from backend.api.auth import current_user
from backend.api.repositories import _get_repository_or_404
from backend.db import get_db
from backend.models.job import Job
from backend.models.user import User
from backend.services.jobs import IdempotencyConflict, QueueFull, enqueue_job, get_queue

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
