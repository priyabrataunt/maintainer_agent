from datetime import datetime, timezone

import httpx
import pytest

from backend.ingestion.github_client import GitHubClient, RateLimitExceeded
from backend.ingestion.models import Comment, Commit, Issue, PullRequest, Repo

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
                {
                    "number": 1,
                    "title": "Bug: crashes on startup",
                    "state": "open",
                    "created_at": "2026-01-01T00:00:00Z",
                    "labels": [{"name": "bug"}, {"name": "p1"}],
                },
                {"number": 2, "title": "PR: fix typo", "pull_request": {"url": "..."}},
            ],
            headers={"Link": f'<{PAGE_2_URL}>; rel="next"'},
        )
    assert str(request.url) == PAGE_2_URL
    return httpx.Response(
        200,
        json=[
            {
                "number": 3,
                "title": "Docs out of date",
                "state": "closed",
                "created_at": "2026-01-02T00:00:00Z",
            }
        ],
    )


def test_iter_issues_paginates_and_skips_pull_requests():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(paginated_issues_handler)
    ) as gh:
        issues = list(gh.iter_issues("octocat", "hello-world"))

    assert all(isinstance(issue, Issue) for issue in issues)
    assert [issue.number for issue in issues] == [1, 3]
    assert issues[0].state == "open"
    assert issues[0].labels == ["bug", "p1"]
    assert issues[1].state == "closed"


COMMENTS_URL = "https://api.github.com/repos/octocat/hello-world/issues/1/comments"


def comments_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == "Bearer test-token"
    assert str(request.url) == COMMENTS_URL
    return httpx.Response(
        200,
        json=[
            {
                "id": 101,
                "user": {"login": "alice"},
                "body": "Can you share a stack trace?",
                "created_at": "2026-01-01T00:00:00Z",
            },
            {
                "id": 102,
                "user": {"login": "bob"},
                "body": "Happens on Windows too.",
                "created_at": "2026-01-02T00:00:00Z",
            },
        ],
    )


def test_get_issue_comments_returns_comment_models():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(comments_handler)
    ) as gh:
        comments = gh.get_issue_comments("octocat", "hello-world", 1)

    assert all(isinstance(comment, Comment) for comment in comments)
    assert comments[0].id == 101
    assert comments[0].user_login == "alice"
    assert comments[0].body == "Can you share a stack trace?"
    assert comments[1].user_login == "bob"


PULLS_URL = "https://api.github.com/repos/octocat/hello-world/pulls"


def pulls_handler(request: httpx.Request) -> httpx.Response:
    assert str(request.url) == PULLS_URL
    return httpx.Response(
        200, json=[{"number": 7, "title": "Fix typo in README"}]
    )


def test_iter_pull_requests_returns_pull_request_models():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(pulls_handler)
    ) as gh:
        prs = list(gh.iter_pull_requests("octocat", "hello-world"))

    assert all(isinstance(pr, PullRequest) for pr in prs)
    assert prs[0].number == 7
    assert prs[0].title == "Fix typo in README"


COMMITS_PAGE_1_URL = "https://api.github.com/repos/octocat/hello-world/commits"
COMMITS_PAGE_2_URL = "https://api.github.com/repos/octocat/hello-world/commits?page=2"


def paginated_commits_handler(request: httpx.Request) -> httpx.Response:
    if str(request.url) == COMMITS_PAGE_1_URL:
        return httpx.Response(
            200,
            json=[{"sha": "abc123", "commit": {"message": "Initial commit\n\nbody"}}],
            headers={"Link": f'<{COMMITS_PAGE_2_URL}>; rel="next"'},
        )
    assert str(request.url) == COMMITS_PAGE_2_URL
    return httpx.Response(
        200, json=[{"sha": "def456", "commit": {"message": "Fix bug"}}]
    )


def test_iter_commits_paginates():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(paginated_commits_handler)
    ) as gh:
        commits = list(gh.iter_commits("octocat", "hello-world"))

    assert all(isinstance(commit, Commit) for commit in commits)
    assert [commit.sha for commit in commits] == ["abc123", "def456"]
    assert commits[0].message == "Initial commit\n\nbody"


def rate_limited_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        403,
        json={"message": "API rate limit exceeded"},
        headers={"X-RateLimit-Remaining": "0", "X-RateLimit-Reset": "1700000000"},
    )


def test_get_repo_raises_rate_limit_exceeded_when_quota_is_zero():
    with GitHubClient(
        token="test-token", transport=httpx.MockTransport(rate_limited_handler)
    ) as gh:
        with pytest.raises(RateLimitExceeded) as exc_info:
            gh.get_repo("octocat", "hello-world")

    assert exc_info.value.reset_at == datetime.fromtimestamp(1700000000, tz=timezone.utc)


def test_other_403s_are_not_treated_as_rate_limit():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(403, json={"message": "Forbidden"})

    with GitHubClient(token="test-token", transport=httpx.MockTransport(handler)) as gh:
        with pytest.raises(httpx.HTTPStatusError):
            gh.get_repo("octocat", "hello-world")


def test_get_retries_server_errors_with_backoff():
    statuses = iter([502, 503, 200])
    sleeps: list[float] = []

    def flaky(request: httpx.Request) -> httpx.Response:
        status = next(statuses)
        if status != 200:
            return httpx.Response(status)
        return httpx.Response(200, json=REPO_JSON)

    with GitHubClient(
        token="t", transport=httpx.MockTransport(flaky), sleep=sleeps.append
    ) as gh:
        repo, _ = gh.get_repo("octocat", "hello-world")

    assert repo.name == "hello-world"
    assert sleeps == [1.0, 2.0]


def test_get_gives_up_after_max_attempts():
    calls = []

    def always_down(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(503)

    with GitHubClient(
        token="t", transport=httpx.MockTransport(always_down), sleep=lambda s: None
    ) as gh:
        with pytest.raises(httpx.HTTPStatusError):
            gh.get_repo("octocat", "hello-world")

    assert len(calls) == 3


def test_get_does_not_retry_client_errors():
    calls = []

    def not_found(request: httpx.Request) -> httpx.Response:
        calls.append(1)
        return httpx.Response(404)

    with GitHubClient(
        token="t", transport=httpx.MockTransport(not_found), sleep=lambda s: None
    ) as gh:
        with pytest.raises(httpx.HTTPStatusError):
            gh.get_repo("octocat", "hello-world")

    assert len(calls) == 1
