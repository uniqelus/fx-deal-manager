from decimal import Decimal

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_deal_crud_integration(integration_client: AsyncClient) -> None:
    create_response = await integration_client.post(
        "/api/v1/deals",
        json={
            "trade_date": "2026-05-08",
            "deal_type": "SPOT",
            "operation_direction": "BUY",
            "buy_currency": "USD",
            "sell_currency": "RUB",
            "amount": "100000.00",
            "rate": "92.50",
            "counterparty_id": "VTBR",
            "comment": "integration test",
        },
    )
    assert create_response.status_code == 201, create_response.text
    created = create_response.json()
    assert created["status"] == "DRAFT"
    assert created["validation_status"] == "NOT_VALIDATED"
    deal_id = created["id"]

    list_response = await integration_client.get("/api/v1/deals?counterparty_id=VTBR")
    assert list_response.status_code == 200
    listing = list_response.json()
    assert listing["total"] >= 1
    assert any(item["id"] == deal_id for item in listing["items"])

    get_response = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert get_response.status_code == 200
    assert get_response.json()["comment"] == "integration test"

    patch_response = await integration_client.patch(
        f"/api/v1/deals/{deal_id}",
        json={"amount": "150000.00"},
    )
    assert patch_response.status_code == 200
    assert Decimal(patch_response.json()["amount"]) == Decimal("150000.00")

    bad_cp = await integration_client.post(
        "/api/v1/deals",
        json={
            "trade_date": "2026-05-08",
            "deal_type": "TOD",
            "operation_direction": "SELL",
            "buy_currency": "EUR",
            "sell_currency": "RUB",
            "amount": "1000.00",
            "rate": "98.00",
            "counterparty_id": "INACTIVE",
        },
    )
    assert bad_cp.status_code == 422
