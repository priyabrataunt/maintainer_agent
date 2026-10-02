from collections.abc import Iterator

import httpx

from backend.config import settings
from backend.ingestion.models import Comment, Issue, Repo

GITHUB_API_URL = "https://api.github.com"


def parse_link_header(header: str | None) -> dict[str, str]:
    """Parse a GitHub `Link` header into {rel: url}. Empty dict if missing."""
    if not header:
        return {}
    links = {}
    for part in header.split(","):
        url_part, rel_part = part.split(";", 1)
        url = url_part.strip().strip("<>")
        rel = rel_part.split("=")[1].strip('" ')
        links[rel] = url
    return links


class GitHubClient:
    """GitHub API client that shares one httpx.Client; use it in a `with` block."""

    def __init__(
        self,
        token: str | None = None,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        token = token or settings.github_token.get_secret_value()
        self._client = httpx.Client(
            base_url=GITHUB_API_URL,
            headers={"Authorization": f"Bearer {token}"},
            transport=transport,
        )

    def __enter__(self) -> "GitHubClient":
        return self

    def __exit__(self, *exc_info) -> None:
        self._client.close()

    def get_repo(self, owner: str, repo: str) -> tuple[Repo, str | None]:
        """Return the repo and the remaining GitHub rate-limit quota."""
        response = self._client.get(f"/repos/{owner}/{repo}")
        response.raise_for_status()
        return Repo.model_validate(response.json()), response.headers.get(
            "X-RateLimit-Remaining"
        )

    def iter_issues(self, owner: str, repo: str) -> Iterator[Issue]:
        """Yield issues across all pages, skipping pull requests."""
        url = f"/repos/{owner}/{repo}/issues"
        while url:
            response = self._client.get(url)
            response.raise_for_status()
            for item in response.json():
                if "pull_request" not in item:
                    yield Issue.model_validate(item)
            url = parse_link_header(response.headers.get("Link")).get("next")

    def get_issue_comments(self, owner: str, repo: str, issue_number: int) -> list[Comment]:
        """Return all comments for one issue."""
        response = self._client.get(f"/repos/{owner}/{repo}/issues/{issue_number}/comments")
        response.raise_for_status()
        return [
            Comment(user_login=item["user"]["login"], body=item["body"])
            for item in response.json()
        ]
