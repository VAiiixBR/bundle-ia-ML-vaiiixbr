from fastapi.testclient import TestClient

from worker_app import app


client = TestClient(app)


def test_worker_wrapper_health():
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json()["ok"] is True
