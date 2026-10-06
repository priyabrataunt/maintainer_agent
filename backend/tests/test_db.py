from fastapi.testclient import TestClient

from backend.main import app


def test_db_health_returns_200_and_healthy_status():
    client = TestClient(app)

    response = client.get("/db-health")

    assert response.status_code == 200
    assert response.json() == {"status": "healthy"}
