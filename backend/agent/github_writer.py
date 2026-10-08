import httpx

from backend.agent.tools import ToolFailure

GITHUB_API_URL = "https://api.github.com"


class GitHubIssueWriter:
    """Real writes to one GitHub repository, authenticated as the confirming user."""

    def __init__(
        self,
        owner: str,
        repo: str,
        token: str,
        transport: httpx.BaseTransport | None = None,
    ) -> None:
        self._repo_path = f"/repos/{owner}/{repo}"
        self._base = f"{self._repo_path}/issues"
        self._client = httpx.Client(
            base_url=GITHUB_API_URL,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json"},
            timeout=15,
            transport=transport,
        )

    def can_administer(self, login: str) -> bool:
        """True if `login` owns the repository or has admin permission on it.

        Asked of GitHub with the user's own token, so it reflects their real access.
        """
        response = self._client.get(self._repo_path)
        if response.status_code in (401, 403, 404):
            return False
        response.raise_for_status()
        data = response.json()
        is_owner = (data.get("owner") or {}).get("login", "").lower() == login.lower()
        return is_owner or bool((data.get("permissions") or {}).get("admin"))

    def _send(self, method: str, path: str, payload: dict) -> None:
        response = self._client.request(method, f"{self._base}{path}", json=payload)
        if response.status_code in (401, 403):
            raise ToolFailure("GitHub denied the request; the token lacks permission here")
        if response.status_code == 404:
            raise ToolFailure("GitHub could not find that issue")
        if response.status_code >= 400:
            raise ToolFailure(f"GitHub returned HTTP {response.status_code}")

    def post_comment(self, number: int, body: str) -> str:
        self._send("POST", f"/{number}/comments", {"body": body})
        return f"Posted comment on #{number}"

    def add_label(self, number: int, label: str) -> str:
        self._send("POST", f"/{number}/labels", {"labels": [label]})
        return f"Added label '{label}' to #{number}"

    def close_issue(self, number: int) -> str:
        self._send("PATCH", f"/{number}", {"state": "closed"})
        return f"Closed #{number}"
