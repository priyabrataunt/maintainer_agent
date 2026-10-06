from datetime import datetime, timezone

import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.issue import Issue
from backend.models.repository import Repository


def test_duplicate_repository_and_github_number_violates_unique_constraint(db_session):
    repo = Repository(owner="octocat", name="hello-world")
    db_session.add(repo)
    db_session.flush()

    db_session.add(
        Issue(
            repository_id=repo.id,
            github_number=1,
            title="first",
            state="open",
            labels=[],
            created_at=datetime.now(timezone.utc),
        )
    )
    db_session.flush()

    db_session.add(
        Issue(
            repository_id=repo.id,
            github_number=1,
            title="dup",
            state="open",
            labels=[],
            created_at=datetime.now(timezone.utc),
        )
    )

    with pytest.raises(IntegrityError):
        db_session.flush()
