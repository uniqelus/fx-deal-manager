from decimal import Decimal

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_validate_deal_success(integration_client: AsyncClient) -> None:
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
        },
    )
    assert create_response.status_code == 201
    deal_id = create_response.json()["id"]

    validate_response = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate_response.status_code == 200, validate_response.text
    payload = validate_response.json()
    assert payload["validation_status"] == "VALID"
    assert payload["value_date"] == "2026-05-12"
    assert len(payload["payments"]) == 2
    directions = {payment["payment_direction"] for payment in payload["payments"]}
    assert directions == {"IN", "OUT"}
    assert all(payment["account_code"] for payment in payload["payments"])


@pytest.mark.asyncio
async def test_validate_deal_missing_nostro(integration_client: AsyncClient) -> None:
    create_response = await integration_client.post(
        "/api/v1/deals",
        json={
            "trade_date": "2026-05-08",
            "deal_type": "TOD",
            "operation_direction": "BUY",
            "buy_currency": "GBP",
            "sell_currency": "RUB",
            "amount": "10000.00",
            "rate": "116.00",
            "counterparty_id": "VTBR",
        },
    )
    assert create_response.status_code == 201
    deal_id = create_response.json()["id"]

    validate_response = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate_response.status_code == 422
    detail = validate_response.json()["detail"]
    assert any("nostro" in item["message"].lower() for item in detail)
    assert validate_response.json()["detail"][0]["field"] == "payments"


@pytest.mark.asyncio
async def test_nsi_endpoints(integration_client: AsyncClient) -> None:
    cp = await integration_client.get("/api/v1/nsi/counterparties")
    assert cp.status_code == 200
    assert any(item["id"] == "VTBR" for item in cp.json())

    currencies = await integration_client.get("/api/v1/nsi/currencies")
    assert currencies.status_code == 200
    codes = {item["code"] for item in currencies.json()}
    assert "USD" in codes and "RUB" in codes

    nostro = await integration_client.get("/api/v1/nsi/nostro-accounts?currency_code=USD")
    assert nostro.status_code == 200
    assert len(nostro.json()) >= 1
    assert nostro.json()[0]["currency_code"] == "USD"
