def test_create_repository_returns_201(client):
    response = client.post(
        "/repositories",
        json={"owner": "octocat", "name": "hello-world", "description": "demo"},
    )

    assert response.status_code == 201
    body = response.json()
    assert body["owner"] == "octocat"
    assert body["name"] == "hello-world"
    assert "id" in body


def test_create_duplicate_repository_returns_409(client):
    payload = {"owner": "octocat", "name": "hello-world"}
    client.post("/repositories", json=payload)

    response = client.post("/repositories", json=payload)

    assert response.status_code == 409


def test_list_repositories_returns_created_repository(client):
    client.post("/repositories", json={"owner": "octocat", "name": "hello-world"})

    response = client.get("/repositories")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["owner"] == "octocat"


def test_get_repository_by_id_returns_it(client):
    created = client.post(
        "/repositories", json={"owner": "octocat", "name": "hello-world"}
    ).json()

    response = client.get(f"/repositories/{created['id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created["id"]


def test_get_missing_repository_returns_404(client):
    response = client.get("/repositories/999999")

    assert response.status_code == 404


def test_patch_repository_updates_description(client):
    created = client.post(
        "/repositories", json={"owner": "octocat", "name": "hello-world"}
    ).json()

    response = client.patch(
        f"/repositories/{created['id']}", json={"description": "updated"}
    )

    assert response.status_code == 200
    assert response.json()["description"] == "updated"


def test_patch_missing_repository_returns_404(client):
    response = client.patch("/repositories/999999", json={"description": "x"})

    assert response.status_code == 404


def test_delete_repository_returns_204_and_removes_it(client):
    created = client.post(
        "/repositories", json={"owner": "octocat", "name": "hello-world"}
    ).json()

    response = client.delete(f"/repositories/{created['id']}")

    assert response.status_code == 204
    assert client.get(f"/repositories/{created['id']}").status_code == 404


def test_delete_missing_repository_returns_404(client):
    response = client.delete("/repositories/999999")

    assert response.status_code == 404


def test_list_repositories_respects_limit_and_offset(client):
    for n in range(3):
        client.post("/repositories", json={"owner": "octocat", "name": f"repo-{n}"})

    response = client.get("/repositories?limit=1&offset=1")

    assert response.status_code == 200
    body = response.json()
    assert len(body) == 1
    assert body[0]["name"] == "repo-1"
