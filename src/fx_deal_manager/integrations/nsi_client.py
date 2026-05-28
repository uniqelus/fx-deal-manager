"""Read-through client for NSI served by ОТЧЁТЫ-АСУБАНК.

The upstream /integration/nsi/* endpoints require a user token, so the
caller's bearer token is forwarded as-is. Responses are mapped to this
service's NSI response shapes.
"""

from typing import Any

import httpx

from fx_deal_manager.core.config import settings

_TIMEOUT = 10.0


async def _get(path: str, token: str) -> list[dict[str, Any]]:
    base = (settings.nsi_base_url or "").rstrip("/")
    async with httpx.AsyncClient(timeout=_TIMEOUT) as client:
        response = await client.get(
            f"{base}/api/v1/integration/nsi/{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        response.raise_for_status()
        data = response.json()
    if isinstance(data, list):
        return data
    if isinstance(data, dict):
        return data.get("items", [])
    return []


async def fetch_counterparties(token: str) -> list[dict[str, Any]]:
    return [
        {
            "id": row["id"],
            "name": row.get("name") or row["id"],
            "bic": row.get("bic"),
            "country": row.get("country"),
            "is_active": bool(row.get("is_active", True)),
        }
        for row in await _get("counterparties", token)
    ]


async def fetch_currencies(token: str) -> list[dict[str, Any]]:
    return [
        {
            "code": row["code"],
            "name": row.get("name_ru") or row.get("name_en") or row["code"],
            "decimal_places": int(row.get("decimal_places", 2)),
        }
        for row in await _get("currencies", token)
    ]


async def fetch_nostro_accounts(token: str, currency_code: str | None = None) -> list[dict[str, Any]]:
    wanted = currency_code.upper() if currency_code else None
    accounts: list[dict[str, Any]] = []
    for row in await _get("accounts", token):
        if row.get("type") not in (None, "NOSTRO"):
            continue
        code = (row.get("currency_code") or "").upper()
        if wanted and code != wanted:
            continue
        accounts.append(
            {
                "id": row["id"],
                "currency_code": row.get("currency_code") or "",
                "bank_name": row.get("bank_name") or "",
                "account_number": row.get("account_number") or "",
                "is_active": bool(row.get("is_active", True)),
            }
        )
    return accounts
