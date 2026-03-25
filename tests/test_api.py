from fastapi.testclient import TestClient

from app import app


client = TestClient(app)


def test_health_and_status_and_audit():
    health = client.get("/health")
    assert health.status_code == 200
    assert health.json()["ok"] is True

    status = client.get("/status")
    assert status.status_code == 200
    payload = status.json()
    assert payload["ok"] is True
    assert payload["symbol"] == "ITUB4"
    assert "audit" in payload
    assert "dashboard_state" in payload

    audit = client.get("/audit")
    assert audit.status_code == 200
    audit_payload = audit.json()
    assert audit_payload["ok"] is True
    assert audit_payload["audit"]["symbol"] == "ITUB4"
