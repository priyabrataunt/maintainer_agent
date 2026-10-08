from typing import Protocol

from pydantic import BaseModel, Field

from backend.agent.tools import Tool, ToolFailure, ToolRegistry


class IssueRecord(BaseModel):
    number: int
    title: str
    body: str = ""
    state: str = "open"


class IssueStore(Protocol):
    def search(self, query: str, limit: int) -> list[IssueRecord]: ...
    def get(self, number: int) -> IssueRecord | None: ...


class SearchIssuesArgs(BaseModel):
    query: str = Field(min_length=1, description="Keywords to look for in issue titles and bodies")
    limit: int = Field(default=5, ge=1, le=20)


class GetIssueArgs(BaseModel):
    number: int = Field(ge=1, description="GitHub issue number")


def build_issue_registry(store: IssueStore) -> ToolRegistry:
    def search_issues(query: str, limit: int) -> str:
        found = store.search(query, limit)
        if not found:
            return f"No issues matched '{query}'. Try different keywords."
        return "\n".join(f"#{i.number} [{i.state}] {i.title}" for i in found)

    def get_issue(number: int) -> str:
        issue = store.get(number)
        if issue is None:
            raise ToolFailure(
                f"#{number} not found; call search_issues first to find valid numbers"
            )
        return f"#{issue.number} [{issue.state}] {issue.title}\n\n{issue.body}"

    registry = ToolRegistry()
    registry.register(Tool(
        "search_issues", "Search issues by keyword; returns number, state and title.",
        SearchIssuesArgs, search_issues,
    ))
    registry.register(Tool(
        "get_issue", "Fetch the full text of one issue by number.", GetIssueArgs, get_issue,
    ))
    return registry


class InMemoryIssueStore:
    """Simple keyword store for tests and demos."""

    def __init__(self, issues: list[IssueRecord]) -> None:
        self.issues = issues

    def search(self, query: str, limit: int) -> list[IssueRecord]:
        words = query.lower().split()
        hits = [
            i for i in self.issues
            if any(w in f"{i.title} {i.body}".lower() for w in words)
        ]
        return hits[:limit]

    def get(self, number: int) -> IssueRecord | None:
        return next((i for i in self.issues if i.number == number), None)


class CommitRecord(BaseModel):
    sha: str
    message: str


class PullRequestRecord(BaseModel):
    number: int
    title: str
    state: str = "open"
    body: str = ""


class CodeStore(Protocol):
    def recent_commits(self, limit: int) -> list[CommitRecord]: ...
    def get_pr(self, number: int) -> PullRequestRecord | None: ...


class RecentCommitsArgs(BaseModel):
    limit: int = Field(default=10, ge=1, le=50)


def add_code_tools(registry: ToolRegistry, store: CodeStore) -> ToolRegistry:
    """Register `list_recent_commits` and `get_pr` on an existing registry."""

    def list_recent_commits(limit: int) -> str:
        commits = store.recent_commits(limit)
        if not commits:
            return "No commits found."
        return "\n".join(f"{c.sha[:7]} {c.message.splitlines()[0]}" for c in commits)

    def get_pr(number: int) -> str:
        pr = store.get_pr(number)
        if pr is None:
            raise ToolFailure(f"PR #{number} not found; call list_recent_commits or search_issues")
        return f"PR #{pr.number} [{pr.state}] {pr.title}\n\n{pr.body}"

    registry.register(Tool(
        "list_recent_commits", "List the most recent commits (sha and subject).",
        RecentCommitsArgs, list_recent_commits,
    ))
    registry.register(Tool("get_pr", "Fetch one pull request by number.", GetIssueArgs, get_pr))
    return registry
