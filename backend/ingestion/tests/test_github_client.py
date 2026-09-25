import httpx

from backend.ingestion.github_client import get_repo


def test_get_repo_returns_parsed_json(monkeypatch):
    def fake_get(url, **kwargs):
        assert url == "https://api.github.com/repos/octocat/hello-world"
        request = httpx.Request("GET", url)
        return httpx.Response(
            200,
            json={
                "name": "hello-world",
                "description": "My first repo",
                "stargazers_count": 42,
            },
            request=request,
        )

    monkeypatch.setattr(httpx, "get", fake_get)

    data = get_repo("octocat", "hello-world")

    assert data["name"] == "hello-world"
    assert data["description"] == "My first repo"
    assert data["stargazers_count"] == 42
