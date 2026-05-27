import os
from collections.abc import AsyncIterator, Callable
from typing import Any

import pytest
from httpx import ASGITransport, AsyncClient

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.domain.schemas import UserClaims
from fx_deal_manager.integrations.position_client import PositionSendResult, PositionSystemAdapter
from fx_deal_manager.main import app

TRADER = UserClaims(
    user_id="00000000-0000-0000-0000-000000000001",
    email="integration-trader@demo.local",
    first_name="Test",
    last_name="Trader",
    role="TRADER",
    expires_at=9999999999,
)

POSITIONER = UserClaims(
    user_id="00000000-0000-0000-0000-000000000002",
    email="integration-positioner@demo.local",
    first_name="Test",
    last_name="Positioner",
    role="POSITIONER",
    expires_at=9999999999,
)

ADMIN = UserClaims(
    user_id="00000000-0000-0000-0000-000000000003",
    email="integration-admin@demo.local",
    first_name="Test",
    last_name="Admin",
    role="ADMIN",
    expires_at=9999999999,
)

AUDITOR = UserClaims(
    user_id="00000000-0000-0000-0000-000000000004",
    email="integration-auditor@demo.local",
    first_name="Test",
    last_name="Auditor",
    role="AUDITOR",
    expires_at=9999999999,
)

SAMPLE_DEAL: dict[str, Any] = {
    "trade_date": "2026-05-08",
    "deal_type": "SPOT",
    "operation_direction": "BUY",
    "buy_currency": "USD",
    "sell_currency": "RUB",
    "amount": "100000.00",
    "rate": "92.50",
    "counterparty_id": "VTBR",
}


@pytest.fixture(scope="session")
def integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "").lower() in ("1", "true", "yes")


def set_integration_user(user: UserClaims) -> None:
    app.dependency_overrides[get_current_user] = lambda: user


@pytest.fixture
async def integration_client(integration_enabled: bool) -> AsyncIterator[AsyncClient]:
    if not integration_enabled:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 with running PostgreSQL")
    set_integration_user(TRADER)
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()


@pytest.fixture
def mock_position_success(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _send(_self: PositionSystemAdapter, _deal: object) -> PositionSendResult:
        return PositionSendResult(
            success=True,
            correlation_id="pmi-test-correlation",
            external_ref="pmi-ext-ref",
        )

    monkeypatch.setattr(PositionSystemAdapter, "send_deal", _send)


async def create_draft(client: AsyncClient, payload: dict[str, Any] | None = None) -> str:
    response = await client.post("/api/v1/deals", json=payload or SAMPLE_DEAL)
    assert response.status_code == 201, response.text
    return response.json()["id"]


async def validate_deal(client: AsyncClient, deal_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v1/deals/{deal_id}/validate")
    assert response.status_code == 200, response.text
    return response.json()


async def submit_deal(client: AsyncClient, deal_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v1/deals/{deal_id}/submit")
    assert response.status_code == 200, response.text
    return response.json()


async def approve_deal(client: AsyncClient, deal_id: str) -> dict[str, Any]:
    response = await client.post(f"/api/v1/deals/{deal_id}/approve")
    assert response.status_code == 200, response.text
    return response.json()


def role_client_factory(user: UserClaims) -> Callable[[], None]:
    def _apply() -> None:
        set_integration_user(user)

    return _apply
