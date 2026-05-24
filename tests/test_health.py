from fastapi.testclient import TestClient

from fx_deal_manager.main import app

client = TestClient(app)


def test_health_check() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] in ("ok", "degraded")
    assert payload["service"] == "Foreign Exchange Deal Manager"
    assert "database" in payload
