import pytest
from pydantic import ValidationError

from backend.models.repository import Repository
from backend.schemas.repository import RepositoryCreate, RepositoryRead


def test_repository_create_rejects_empty_owner():
    with pytest.raises(ValidationError):
        RepositoryCreate(owner="", name="hello-world")


def test_repository_read_builds_from_orm_instance():
    repo = Repository(id=1, owner="octocat", name="hello-world", description="demo")

    read = RepositoryRead.model_validate(repo, from_attributes=True)

    assert read.id == 1
    assert read.owner == "octocat"
    assert read.name == "hello-world"
    assert read.description == "demo"
