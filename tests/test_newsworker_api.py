from pathlib import Path

from fastapi.testclient import TestClient

from newsworker.worker import app, run_demo


client = TestClient(app)


def test_newsworker_health_without_snapshot(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = client.get("/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["snapshot_available"] is False


def test_newsworker_run_demo_and_latest(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)

    created = run_demo()
    assert created.exists()

    latest_response = client.get("/latest")
    assert latest_response.status_code == 200
    latest_payload = latest_response.json()
    assert latest_payload["ok"] is True
    assert latest_payload["snapshot"]["symbol"] == "ITUB4"
    assert latest_payload["snapshot"]["headline_count"] >= 1


def test_newsworker_run_demo_endpoint(tmp_path: Path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    response = client.post("/run-demo")
    assert response.status_code == 200
    payload = response.json()
    assert payload["ok"] is True
    assert payload["snapshot"]["price_bias"] == "UP_BIAS"
