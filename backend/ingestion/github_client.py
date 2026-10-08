import time
from collections.abc import Callable, Iterator
from datetime import datetime, timezone

import httpx

from backend.config import settings
from backend.ingestion.models import Comment, Commit, Issue, PullRequest, Repo

GITHUB_API_URL = "https://api.github.com"


class RateLimitExceeded(Exception):
    """Raised when GitHub's rate limit quota has hit zero."""

    def __init__(self, reset_at: datetime) -> None:
        self.reset_at = reset_at
        super().__init__(f"GitHub rate limit exceeded; resets at {reset_at.isoformat()}")


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
        max_attempts: int = 3,
        retry_base_delay_s: float = 1.0,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._max_attempts = max_attempts
        self._retry_base_delay_s = retry_base_delay_s
        self._sleep = sleep
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

    def _get(self, url: str) -> httpx.Response:
        """GET `url`, retrying 429/5xx with backoff; raise RateLimitExceeded at quota zero."""
        for attempt in range(1, self._max_attempts + 1):
            response = self._client.get(url)
            transient = response.status_code == 429 or response.status_code >= 500
            if not transient or attempt == self._max_attempts:
                break
            self._sleep(self._retry_base_delay_s * 2 ** (attempt - 1))
        if response.status_code == 403 and response.headers.get("X-RateLimit-Remaining") == "0":
            reset_at = datetime.fromtimestamp(
                int(response.headers["X-RateLimit-Reset"]), tz=timezone.utc
            )
            raise RateLimitExceeded(reset_at)
        response.raise_for_status()
        return response

    def get_repo(self, owner: str, repo: str) -> tuple[Repo, str | None]:
        """Return the repo and the remaining GitHub rate-limit quota."""
        response = self._get(f"/repos/{owner}/{repo}")
        return Repo.model_validate(response.json()), response.headers.get(
            "X-RateLimit-Remaining"
        )

    def _iter_pages(self, url: str) -> Iterator[dict]:
        """Yield raw JSON items across all pages, following the `Link` header."""
        while url:
            response = self._get(url)
            yield from response.json()
            url = parse_link_header(response.headers.get("Link")).get("next")

    def iter_issues(self, owner: str, repo: str) -> Iterator[Issue]:
        """Yield issues across all pages, skipping pull requests."""
        for item in self._iter_pages(f"/repos/{owner}/{repo}/issues"):
            if "pull_request" not in item:
                yield Issue.model_validate(item)

    def iter_pull_requests(self, owner: str, repo: str) -> Iterator[PullRequest]:
        """Yield pull requests across all pages."""
        for item in self._iter_pages(f"/repos/{owner}/{repo}/pulls"):
            yield PullRequest.model_validate(item)

    def iter_commits(self, owner: str, repo: str) -> Iterator[Commit]:
        """Yield commits across all pages."""
        for item in self._iter_pages(f"/repos/{owner}/{repo}/commits"):
            yield Commit(sha=item["sha"], message=item["commit"]["message"])

    def get_issue_comments(self, owner: str, repo: str, issue_number: int) -> list[Comment]:
        """Return all comments for one issue."""
        response = self._get(f"/repos/{owner}/{repo}/issues/{issue_number}/comments")
        return [
            Comment(
                id=item["id"],
                user_login=item["user"]["login"],
                body=item["body"],
                created_at=item["created_at"],
            )
            for item in response.json()
        ]
