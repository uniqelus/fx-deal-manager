import pytest
from httpx import AsyncClient

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.domain.schemas import UserClaims
from fx_deal_manager.integrations.position_stub import InProcessPositionStub
from fx_deal_manager.main import app
from tests.conftest import TRADER

POSITIONER = UserClaims(
    user_id="00000000-0000-0000-0000-000000000002",
    email="positioner@demo.local",
    first_name="Софья",
    last_name="Борисова",
    role="POSITIONER",
    expires_at=9999999999,
)

ADMIN = UserClaims(
    user_id="00000000-0000-0000-0000-000000000099",
    email="admin@example.com",
    first_name="Admin",
    last_name="User",
    role="ADMIN",
    expires_at=9999999999,
)


@pytest.mark.asyncio
async def test_full_approve_to_executed_with_audit(integration_client: AsyncClient) -> None:
    InProcessPositionStub.reset()
    app.dependency_overrides[get_current_user] = lambda: TRADER

    create = await integration_client.post(
        "/api/v1/deals",
        json={
            "trade_date": "2026-05-08",
            "deal_type": "SPOT",
            "operation_direction": "BUY",
            "buy_currency": "USD",
            "sell_currency": "RUB",
            "amount": "50000.00",
            "rate": "92.50",
            "counterparty_id": "VTBR",
        },
    )
    assert create.status_code == 201
    deal_id = create.json()["id"]

    validate = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate.status_code == 200

    submit = await integration_client.post(f"/api/v1/deals/{deal_id}/submit")
    assert submit.status_code == 200
    assert submit.json()["status"] == "WAITING_FOR_POSITIONER"

    app.dependency_overrides[get_current_user] = lambda: POSITIONER
    queue = await integration_client.get("/api/v1/deals/queue")
    assert queue.status_code == 200
    assert any(item["id"] == deal_id for item in queue.json())

    approve = await integration_client.post(f"/api/v1/deals/{deal_id}/approve")
    assert approve.status_code == 200, approve.text
    assert approve.json()["status"] == "EXECUTED"
    assert len(InProcessPositionStub.all_received()) == 1

    audit = await integration_client.get(f"/api/v1/audit-events?entity_id={deal_id}")
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert "CREATE" in actions
    assert "VALIDATE" in actions
    assert "STATUS_CHANGE" in actions
    assert "POSITION_SEND" in actions


@pytest.mark.asyncio
async def test_nsi_sync_admin(integration_client: AsyncClient) -> None:
    app.dependency_overrides[get_current_user] = lambda: ADMIN
    response = await integration_client.post("/api/v1/nsi/sync")
    assert response.status_code == 200
    payload = response.json()
    assert payload["synced"] is True
    assert payload["counterparties"] >= 9


@pytest.mark.asyncio
async def test_self_approval_forbidden(integration_client: AsyncClient) -> None:
    InProcessPositionStub.reset()
    app.dependency_overrides[get_current_user] = lambda: TRADER

    create = await integration_client.post(
        "/api/v1/deals",
        json={
            "trade_date": "2026-05-08",
            "deal_type": "TOD",
            "operation_direction": "BUY",
            "buy_currency": "USD",
            "sell_currency": "RUB",
            "amount": "1000.00",
            "rate": "92.50",
            "counterparty_id": "VTBR",
        },
    )
    deal_id = create.json()["id"]
    await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    await integration_client.post(f"/api/v1/deals/{deal_id}/submit")

    approve = await integration_client.post(f"/api/v1/deals/{deal_id}/approve")
    assert approve.status_code == 403
