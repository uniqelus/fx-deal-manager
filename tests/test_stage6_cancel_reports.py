"""Integration tests for Stage 6: FR-015 cancel (DRAFT) and FR-019 reports."""

from __future__ import annotations

import csv
import io

import pytest
from httpx import AsyncClient

from tests.conftest import ADMIN, POSITIONER, TRADER, create_draft, set_integration_user


@pytest.mark.asyncio
async def test_cancel_draft_deal(integration_client: AsyncClient) -> None:
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    cancel = await integration_client.post(
        f"/api/v1/deals/{deal_id}/cancel",
        json={"comment": "Trader changed mind"},
    )
    assert cancel.status_code == 200, cancel.text
    assert cancel.json()["status"] == "CANCELLED"

    audit = await integration_client.get(f"/api/v1/audit-events?entity_id={deal_id}")
    actions = {item["action"] for item in audit.json()["items"]}
    assert "STATUS_CHANGE" in actions
    cancel_event = next(
        item
        for item in audit.json()["items"]
        if item["action"] == "STATUS_CHANGE" and "CANCELLED" in (item.get("new_value") or "")
    )
    assert "Trader changed mind" in cancel_event["new_value"]


@pytest.mark.asyncio
async def test_cancel_non_draft_forbidden(integration_client: AsyncClient) -> None:
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    validate = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate.status_code == 200
    submit = await integration_client.post(f"/api/v1/deals/{deal_id}/submit")
    assert submit.status_code == 200
    assert submit.json()["status"] == "WAITING_FOR_POSITIONER"

    cancel = await integration_client.post(f"/api/v1/deals/{deal_id}/cancel")
    assert cancel.status_code == 403
    assert "DRAFT" in cancel.json()["detail"]


@pytest.mark.asyncio
async def test_cancel_requires_creator(integration_client: AsyncClient) -> None:
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    set_integration_user(POSITIONER)
    cancel = await integration_client.post(f"/api/v1/deals/{deal_id}/cancel")
    assert cancel.status_code == 403


@pytest.mark.asyncio
async def test_reports_json(integration_client: AsyncClient) -> None:
    set_integration_user(TRADER)
    await create_draft(integration_client)

    set_integration_user(ADMIN)
    response = await integration_client.get(
        "/api/v1/reports/deals?counterparty_id=VTBR&format=json"
    )
    assert response.status_code == 200, response.text
    payload = response.json()
    assert "items" in payload
    assert payload["total"] >= 1


@pytest.mark.asyncio
async def test_reports_csv(integration_client: AsyncClient) -> None:
    set_integration_user(TRADER)
    await create_draft(integration_client)

    set_integration_user(ADMIN)
    response = await integration_client.get(
        "/api/v1/reports/deals?counterparty_id=VTBR&format=csv"
    )
    assert response.status_code == 200, response.text
    assert response.headers["content-type"].startswith("text/csv")
    assert "attachment" in response.headers["content-disposition"]

    reader = csv.reader(io.StringIO(response.text))
    rows = list(reader)
    assert rows
    header = rows[0]
    assert header[0] == "deal_id"
    assert "counterparty_id" in header
    assert any(row[9] == "VTBR" for row in rows[1:])


@pytest.mark.asyncio
async def test_reports_role_restriction(integration_client: AsyncClient) -> None:
    set_integration_user(TRADER)
    response = await integration_client.get("/api/v1/reports/deals?format=json")
    assert response.status_code == 403
