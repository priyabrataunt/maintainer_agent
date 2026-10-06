from datetime import datetime

from pydantic import BaseModel, Field, field_validator


class Repo(BaseModel):
    name: str
    description: str | None
    stargazers_count: int


class Issue(BaseModel):
    number: int
    title: str
    body: str | None = None
    state: str
    labels: list[str] = Field(default_factory=list)
    created_at: datetime

    @field_validator("labels", mode="before")
    @classmethod
    def _extract_label_names(cls, value: list) -> list[str]:
        return [item["name"] if isinstance(item, dict) else item for item in value]


class Comment(BaseModel):
    id: int
    user_login: str
    body: str
    created_at: datetime


class PullRequest(BaseModel):
    number: int
    title: str


class Commit(BaseModel):
    sha: str
    message: str
