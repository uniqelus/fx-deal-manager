from fastapi.testclient import TestClient

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.domain.schemas import UserClaims
from fx_deal_manager.main import app

client = TestClient(app)


def test_health_check_without_db() -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    payload = response.json()
    assert payload["service"] == "Foreign Exchange Deal Manager"
    assert payload["status"] in ("ok", "degraded")
    assert "database" in payload


def test_me_requires_auth() -> None:
    response = client.get("/api/v1/me")
    assert response.status_code == 401


def test_me_returns_user() -> None:
    mock_user = UserClaims(
        user_id="00000000-0000-0000-0000-000000000001",
        email="trader@demo.local",
        first_name="Илья",
        last_name="Смирнов",
        role="TRADER",
        expires_at=9999999999,
    )
    app.dependency_overrides[get_current_user] = lambda: mock_user
    try:
        response = client.get("/api/v1/me")
        assert response.status_code == 200
        payload = response.json()
        assert payload["email"] == "trader@demo.local"
        assert payload["role"] == "TRADER"
        assert payload["first_name"] == "Илья"
    finally:
        app.dependency_overrides.clear()
