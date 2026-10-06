from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from backend.api.repositories import _get_repository_or_404
from backend.db import get_db
from backend.models.issue import Issue
from backend.schemas.issue import IssueCreate, IssueRead

router = APIRouter()


@router.post(
    "/repositories/{repository_id}/issues", response_model=IssueRead, status_code=201
)
def create_issue(
    repository_id: int, payload: IssueCreate, db: Session = Depends(get_db)
):
    _get_repository_or_404(repository_id, db)

    issue = Issue(repository_id=repository_id, **payload.model_dump())
    db.add(issue)
    try:
        db.commit()
    except IntegrityError:
        db.rollback()
        raise HTTPException(status_code=409, detail="Issue already exists")
    db.refresh(issue)
    return issue


@router.get("/repositories/{repository_id}/issues", response_model=list[IssueRead])
def list_issues(
    repository_id: int,
    state: str | None = None,
    db: Session = Depends(get_db),
):
    _get_repository_or_404(repository_id, db)

    query = db.query(Issue).filter(Issue.repository_id == repository_id)
    if state is not None:
        query = query.filter(Issue.state == state)
    return query.order_by(Issue.id).all()
