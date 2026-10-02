import httpx

from backend.ingestion import cli
from backend.ingestion.github_client import GitHubClient


def test_prints_owner_and_repo(capsys, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], headers={"X-RateLimit-Remaining": "4999"})
        return httpx.Response(
            200,
            json={
                "name": "hello-world",
                "description": "My first repo",
                "stargazers_count": 42,
            },
            headers={"X-RateLimit-Remaining": "4999"},
        )

    monkeypatch.setattr(
        cli,
        "GitHubClient",
        lambda: GitHubClient(token="t", transport=httpx.MockTransport(handler)),
    )

    cli.main(["--owner", "octocat", "--repo", "hello-world"])

    captured = capsys.readouterr()
    assert "octocat" in captured.out
    assert "hello-world" in captured.out
    assert "42" in captured.out
    assert "rate limit remaining: 4999" in captured.out


def test_skips_pull_requests_and_prints_issues(capsys, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues"):
            return httpx.Response(
                200,
                json=[
                    {"number": 1, "title": "Bug: crashes on startup"},
                    {
                        "number": 2,
                        "title": "PR: fix typo",
                        "pull_request": {"url": "..."},
                    },
                ],
                headers={"X-RateLimit-Remaining": "4998"},
            )
        return httpx.Response(
            200,
            json={
                "name": "hello-world",
                "description": "My first repo",
                "stargazers_count": 42,
            },
            headers={"X-RateLimit-Remaining": "4999"},
        )

    monkeypatch.setattr(
        cli,
        "GitHubClient",
        lambda: GitHubClient(token="t", transport=httpx.MockTransport(handler)),
    )

    cli.main(["--owner", "octocat", "--repo", "hello-world"])

    captured = capsys.readouterr()
    assert "#1 Bug: crashes on startup" in captured.out
    assert "PR: fix typo" not in captured.out
