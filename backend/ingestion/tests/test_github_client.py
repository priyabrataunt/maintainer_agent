import httpx

from backend.ingestion.github_client import GitHubClient

REPO_JSON = {
    "name": "hello-world",
    "description": "My first repo",
    "stargazers_count": 42,
}


def handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer test-token"
    assert str(request.url) == "https://api.github.com/repos/octocat/hello-world"
    return httpx.Response(
        200, json=REPO_JSON, headers={"X-RateLimit-Remaining": "4999"}
    )


def test_get_repo_returns_parsed_json_and_rate_limit():
    with GitHubClient(token="test-token", transport=httpx.MockTransport(handler)) as gh:
        data, remaining = gh.get_repo("octocat", "hello-world")

    assert data["name"] == "hello-world"
    assert data["description"] == "My first repo"
    assert data["stargazers_count"] == 42
    assert remaining == "4999"


def test_client_is_closed_after_with_block():
    with GitHubClient(token="test-token", transport=httpx.MockTransport(handler)) as gh:
        pass

    assert gh._client.is_closed


ISSUES_JSON = [
    {"number": 1, "title": "Bug: crashes on startup"},
    {"number": 2, "title": "PR: fix typo", "pull_request": {"url": "..."}},
]


def issues_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer test-token"
    assert str(request.url) == "https://api.github.com/repos/octocat/hello-world/issues"
    return httpx.Response(
        200, json=ISSUES_JSON, headers={"X-RateLimit-Remaining": "4998"}
    )


def test_get_issues_returns_parsed_json_and_rate_limit():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(issues_handler)
    ) as gh:
        issues, remaining = gh.get_issues("octocat", "hello-world")

    assert issues == ISSUES_JSON
    assert remaining == "4998"
