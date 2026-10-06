from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class IssueCreate(BaseModel):
    github_number: int
    title: str = Field(min_length=1)
    body: str | None = None
    state: str
    labels: list[str] = Field(default_factory=list)
    created_at: datetime


class IssueRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    repository_id: int
    github_number: int
    title: str
    body: str | None
    state: str
    labels: list[str]
    created_at: datetime
