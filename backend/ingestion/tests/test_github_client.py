import httpx

from backend.ingestion.github_client import GitHubClient
from backend.ingestion.models import Issue, Repo

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


def test_get_repo_returns_repo_model_and_rate_limit():
    with GitHubClient(token="test-token", transport=httpx.MockTransport(handler)) as gh:
        repo, remaining = gh.get_repo("octocat", "hello-world")

    assert isinstance(repo, Repo)
    assert repo.name == "hello-world"
    assert repo.description == "My first repo"
    assert repo.stargazers_count == 42
    assert remaining == "4999"


def test_client_is_closed_after_with_block():
    with GitHubClient(token="test-token", transport=httpx.MockTransport(handler)) as gh:
        pass

    assert gh._client.is_closed


PAGE_1_URL = "https://api.github.com/repos/octocat/hello-world/issues"
PAGE_2_URL = "https://api.github.com/repos/octocat/hello-world/issues?page=2"


def paginated_issues_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer test-token"
    if str(request.url) == PAGE_1_URL:
        return httpx.Response(
            200,
            json=[
                {"number": 1, "title": "Bug: crashes on startup"},
                {"number": 2, "title": "PR: fix typo", "pull_request": {"url": "..."}},
            ],
            headers={"Link": f'<{PAGE_2_URL}>; rel="next"'},
        )
    assert str(request.url) == PAGE_2_URL
    return httpx.Response(200, json=[{"number": 3, "title": "Docs out of date"}])


def test_iter_issues_paginates_and_skips_pull_requests():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(paginated_issues_handler)
    ) as gh:
        issues = list(gh.iter_issues("octocat", "hello-world"))

    assert all(isinstance(issue, Issue) for issue in issues)
    assert [issue.number for issue in issues] == [1, 3]
