def test_repository_stats_returns_open_and_closed_counts(client):
    repo = client.post(
        "/repositories", json={"owner": "octocat", "name": "hello-world"}
    ).json()
    for number, state in [(1, "open"), (2, "open"), (3, "closed")]:
        client.post(
            f"/repositories/{repo['id']}/issues",
            json={
                "github_number": number,
                "title": f"issue {number}",
                "state": state,
                "created_at": "2026-01-01T00:00:00Z",
            },
        )

    response = client.get(f"/repositories/{repo['id']}/stats")

    assert response.status_code == 200
    body = response.json()
    assert body["repository_id"] == repo["id"]
    assert body["open_count"] == 2
    assert body["closed_count"] == 1


def test_repository_stats_for_missing_repository_returns_404(client):
    response = client.get("/repositories/999999/stats")

    assert response.status_code == 404
