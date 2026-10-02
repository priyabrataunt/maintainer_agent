import httpx

from backend.config import settings

GITHUB_API_URL = "https://api.github.com"


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

    def get_repo(self, owner: str, repo: str) -> tuple[dict, str | None]:
        """Return the repo JSON and the remaining GitHub rate-limit quota."""
        response = self._client.get(f"/repos/{owner}/{repo}")
        response.raise_for_status()
        return response.json(), response.headers.get("X-RateLimit-Remaining")

    def get_issues(self, owner: str, repo: str) -> tuple[list[dict], str | None]:
        """Return page 1 of issues (GitHub includes PRs here) and the rate-limit quota."""
        response = self._client.get(f"/repos/{owner}/{repo}/issues")
        response.raise_for_status()
        return response.json(), response.headers.get("X-RateLimit-Remaining")
