from pydantic import BaseModel


class Repo(BaseModel):
    name: str
    description: str | None
    stargazers_count: int


class Issue(BaseModel):
    number: int
    title: str


class Comment(BaseModel):
    user_login: str
    body: str


class PullRequest(BaseModel):
    number: int
    title: str


class Commit(BaseModel):
    sha: str
    message: str
