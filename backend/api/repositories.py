from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.db import get_db
from backend.models.issue import Issue
from backend.models.repository import Repository
from backend.schemas.repository import (
    RepositoryCreate,
    RepositoryRead,
    RepositoryStats,
    RepositoryUpdate,
)

router = APIRouter()


def _get_repository_or_404(repository_id: int, db: Session) -> Repository:
    repo = db.get(Repository, repository_id)
    if repo is None:
        raise HTTPException(status_code=404, detail="Repository not found")
    return repo


@router.post("/repositories", response_model=RepositoryRead, status_code=201)
def create_repository(payload: RepositoryCreate, db: Session = Depends(get_db)):
    repo = Repository(**payload.model_dump())
    db.add(repo)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Repository already exists")
    db.refresh(repo)
    return repo


@router.get("/repositories", response_model=list[RepositoryRead])
def list_repositories(
    limit: int = 100, offset: int = 0, db: Session = Depends(get_db)
):
    return (
        db.query(Repository)
        .order_by(Repository.id)
        .limit(limit)
        .offset(offset)
        .all()
    )


@router.get("/repositories/{repository_id}", response_model=RepositoryRead)
def get_repository(repository_id: int, db: Session = Depends(get_db)):
    return _get_repository_or_404(repository_id, db)


@router.patch("/repositories/{repository_id}", response_model=RepositoryRead)
def update_repository(
    repository_id: int, payload: RepositoryUpdate, db: Session = Depends(get_db)
):
    repo = _get_repository_or_404(repository_id, db)
    for field, value in payload.model_dump(exclude_unset=True).items():
        setattr(repo, field, value)
    db.commit()
    db.refresh(repo)
    return repo


@router.delete("/repositories/{repository_id}", status_code=204)
def delete_repository(repository_id: int, db: Session = Depends(get_db)):
    repo = _get_repository_or_404(repository_id, db)
    db.delete(repo)
    db.commit()


@router.get("/repositories/{repository_id}/stats", response_model=RepositoryStats)
def get_repository_stats(repository_id: int, db: Session = Depends(get_db)):
    _get_repository_or_404(repository_id, db)

    rows = (
        db.query(Issue.state, func.count(Issue.id))
        .join(Repository, Repository.id == Issue.repository_id)
        .filter(Repository.id == repository_id)
        .group_by(Issue.state)
        .all()
    )
    counts = dict(rows)
    return RepositoryStats(
        repository_id=repository_id,
        open_count=counts.get("open", 0),
        closed_count=counts.get("closed", 0),
    )
