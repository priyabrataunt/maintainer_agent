import json

import httpx
import pytest

from backend.ingestion import cli, storage
from backend.ingestion.github_client import GitHubClient


def test_prints_owner_and_repo(capsys, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith(("/issues", "/pulls", "/commits")):
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
        if request.url.path.endswith(("/pulls", "/commits")):
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
    assert "#1 Bug: crashes on startup" in captured.out
    assert "PR: fix typo" not in captured.out


def test_limit_caps_pull_requests_and_commits(capsys, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues"):
            return httpx.Response(200, json=[], headers={"X-RateLimit-Remaining": "4999"})
        if request.url.path.endswith("/pulls"):
            return httpx.Response(
                200,
                json=[
                    {"number": 1, "title": "PR one"},
                    {"number": 2, "title": "PR two"},
                ],
            )
        if request.url.path.endswith("/commits"):
            return httpx.Response(
                200,
                json=[
                    {"sha": "aaa111", "commit": {"message": "first"}},
                    {"sha": "bbb222", "commit": {"message": "second"}},
                ],
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

    cli.main(["--owner", "octocat", "--repo", "hello-world", "--limit", "1"])

    captured = capsys.readouterr()
    assert "PR #1 PR one" in captured.out
    assert "PR #2 PR two" not in captured.out
    assert "aaa111 first" in captured.out
    assert "bbb222 second" not in captured.out


def test_saves_fetched_data_to_disk(tmp_path, monkeypatch):
    monkeypatch.setattr(storage, "DATA_DIR", tmp_path)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/issues"):
            return httpx.Response(
                200,
                json=[{"number": 1, "title": "Bug: crashes on startup"}],
                headers={"X-RateLimit-Remaining": "4999"},
            )
        if request.url.path.endswith("/pulls"):
            return httpx.Response(200, json=[{"number": 7, "title": "Fix typo"}])
        if request.url.path.endswith("/commits"):
            return httpx.Response(
                200, json=[{"sha": "abc123", "commit": {"message": "Initial"}}]
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

    repo_dir = tmp_path / "octocat_hello-world"
    assert json.loads((repo_dir / "repo.json").read_text())["name"] == "hello-world"
    assert json.loads((repo_dir / "issues.json").read_text())[0]["number"] == 1
    assert json.loads((repo_dir / "pull_requests.json").read_text())[0]["number"] == 7
    assert json.loads((repo_dir / "commits.json").read_text())[0]["sha"] == "abc123"


def test_exits_cleanly_when_rate_limit_exceeded(capsys, monkeypatch):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            403,
            json={"message": "API rate limit exceeded"},
            headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
        )

    monkeypatch.setattr(
        cli,
        "GitHubClient",
        lambda: GitHubClient(token="t", transport=httpx.MockTransport(handler)),
    )

    with pytest.raises(SystemExit) as exc_info:
        cli.main(["--owner", "octocat", "--repo", "hello-world"])

    assert exc_info.value.code == 1
    captured = capsys.readouterr()
    assert "rate limit exceeded" in captured.out.lower()
    assert "2023-11-14" in captured.out
