from fastapi.testclient import TestClient

from vaiiixbr.api.main import app


client = TestClient(app)


def test_health_route() -> None:
    response = client.get('/health')
    assert response.status_code == 200
    payload = response.json()
    assert payload['status'] == 'ok'
    assert 'embedded_worker' in payload


def test_dashboard_route() -> None:
    response = client.get('/dashboard')
    assert response.status_code == 200
    assert 'VAIIIxBR' in response.text


def test_root_exposes_paper_trades_route() -> None:
    response = client.get('/')
    assert response.status_code == 200
    payload = response.json()
    assert payload['paper_trades'] == '/paper-trades'
