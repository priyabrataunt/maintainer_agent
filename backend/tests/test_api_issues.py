def _create_repo(client):
    return client.post(
        "/repositories", json={"owner": "octocat", "name": "hello-world"}
    ).json()


def test_create_issue_returns_201(client):
    repo = _create_repo(client)

    response = client.post(
        f"/repositories/{repo['id']}/issues",
        json={
            "github_number": 1,
            "title": "bug report",
            "state": "open",
            "created_at": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["github_number"] == 1
    assert body["repository_id"] == repo["id"]


def test_create_issue_for_missing_repository_returns_404(client):
    response = client.post(
        "/repositories/999999/issues",
        json={
            "github_number": 1,
            "title": "bug report",
            "state": "open",
            "created_at": "2026-01-01T00:00:00Z",
        },
    )

    assert response.status_code == 404


def test_list_issues_filters_by_state(client):
    repo = _create_repo(client)
    client.post(
        f"/repositories/{repo['id']}/issues",
        json={
            "github_number": 1,
            "title": "open one",
            "state": "open",
            "created_at": "2026-01-01T00:00:00Z",
        },
    )
    client.post(
        f"/repositories/{repo['id']}/issues",
        json={
            "github_number": 2,
            "title": "closed one",
            "state": "closed",
            "created_at": "2026-01-01T00:00:00Z",
        },
    )

    response = client.get(f"/repositories/{repo['id']}/issues?state=open")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["title"] == "open one"
