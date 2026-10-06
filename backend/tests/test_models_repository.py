import pytest
from sqlalchemy.exc import IntegrityError

from backend.models.repository import Repository


def test_duplicate_owner_and_name_violates_unique_constraint(db_session):
    db_session.add(Repository(owner="octocat", name="hello-world", description="demo"))
    db_session.flush()

    db_session.add(Repository(owner="octocat", name="hello-world", description="dup"))

    with pytest.raises(IntegrityError):
        db_session.flush()
