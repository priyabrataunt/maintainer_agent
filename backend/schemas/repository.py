from pydantic import BaseModel, ConfigDict, Field


class RepositoryCreate(BaseModel):
    owner: str = Field(min_length=1)
    name: str = Field(min_length=1)
    description: str | None = None


class RepositoryUpdate(BaseModel):
    owner: str | None = Field(default=None, min_length=1)
    name: str | None = Field(default=None, min_length=1)
    description: str | None = None


class RepositoryRead(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    owner: str
    name: str
    description: str | None


class RepositoryStats(BaseModel):
    repository_id: int
    open_count: int
    closed_count: int
