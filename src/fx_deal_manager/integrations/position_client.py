"""Реальный адаптер интеграции FX -> ПОЗИЦИИ-АСУБАНК.

При подтверждении сделки позиционером каждый платёж сделки отправляется
в ПОЗИЦИИ-АСУБАНК через POST /payments/incoming. ПОЗИЦИИ принимают счёт
и по UUID, и по номеру (account_code из FX = account_number в ПОЗИЦИЯХ).

Авторизация выполняется сервисным токеном IdP (client_credentials). Ретраи и
backoff контролируются настройками position_send_retries и
position_send_backoff_seconds.
"""

from __future__ import annotations

import asyncio
import time
import uuid
from dataclasses import dataclass
from datetime import date
from typing import Any

import httpx

from fx_deal_manager.core.config import settings
from fx_deal_manager.core.logging import get_logger
from fx_deal_manager.domain.models import FXDeal, Payment

logger = get_logger(__name__)


@dataclass(frozen=True)
class PositionSendResult:
    success: bool
    correlation_id: str
    external_ref: str | None = None
    error: str | None = None


@dataclass
class _ServiceTokenCache:
    access_token: str | None = None
    expires_at_monotonic: float = 0.0


def _payment_payload(deal: FXDeal, payment: Payment, correlation_id: str) -> dict[str, Any]:
    return {
        "deal_id": str(deal.id),
        "currency_code": payment.currency_code,
        "amount": str(payment.amount),
        "value_date": (payment.value_date or deal.value_date or deal.trade_date).isoformat(),
        "direction": payment.payment_direction.code,
        "account_number": payment.account_code,
        "correlation_id": correlation_id,
    }


class PositionSystemAdapter:
    """HTTP-клиент к ПОЗИЦИИ-АСУБАНК. URL берётся из POSITION_SYSTEM_URL."""

    def __init__(self) -> None:
        self._token = _ServiceTokenCache()

    async def send_deal(self, deal: FXDeal) -> PositionSendResult:
        correlation_id = str(uuid.uuid4())
        if not settings.position_system_url:
            logger.error(
                "POSITION_SYSTEM_URL не задан — невозможно отправить сделку %s в ПОЗИЦИИ-АСУБАНК",
                deal.id,
            )
            return PositionSendResult(
                success=False,
                correlation_id=correlation_id,
                error="POSITION_SYSTEM_URL is not configured",
            )

        if not deal.payments:
            logger.warning("Сделка %s не имеет платежей — нечего отправлять в ПОЗИЦИИ", deal.id)
            return PositionSendResult(
                success=True,
                correlation_id=correlation_id,
                external_ref=None,
            )

        retries = settings.position_send_retries
        backoff = settings.position_send_backoff_seconds
        base_url = settings.position_system_url.rstrip("/")
        endpoint = f"{base_url}/payments/incoming"

        accepted_refs: list[str] = []

        async with httpx.AsyncClient(timeout=15.0) as client:
            try:
                auth_headers = await self._auth_headers(client)
            except Exception as exc:  # noqa: BLE001
                logger.error("Не удалось получить сервисный токен IdP для ПОЗИЦИЙ: %s", exc)
                return PositionSendResult(
                    success=False,
                    correlation_id=correlation_id,
                    error=f"IdP service token error: {exc}",
                )

            for payment in deal.payments:
                payload = _payment_payload(deal, payment, correlation_id)
                last_error: str | None = None
                for attempt in range(1, retries + 1):
                    try:
                        headers = {
                            "X-Correlation-Id": correlation_id,
                            **auth_headers,
                        }
                        response = await client.post(
                            endpoint,
                            json=payload,
                            headers=headers,
                        )
                        response.raise_for_status()
                        body = response.json()
                        ref = body.get("payment_id") or body.get("id")
                        if ref:
                            accepted_refs.append(str(ref))
                        logger.info(
                            "Платёж сделки %s принят ПОЗИЦИЯМИ correlation_id=%s payment_id=%s attempt=%s",
                            deal.id,
                            correlation_id,
                            ref,
                            attempt,
                        )
                        break
                    except httpx.HTTPStatusError as exc:
                        last_error = f"{exc.response.status_code} {exc.response.text}"
                        logger.warning(
                            "ПОЗИЦИИ отклонили платёж сделки %s attempt=%s/%s: %s",
                            deal.id,
                            attempt,
                            retries,
                            last_error,
                        )
                        # 4xx — нет смысла ретраить
                        if 400 <= exc.response.status_code < 500:
                            return PositionSendResult(
                                success=False,
                                correlation_id=correlation_id,
                                error=last_error,
                            )
                    except Exception as exc:  # noqa: BLE001
                        last_error = str(exc)
                        logger.warning(
                            "Ошибка отправки платежа сделки %s attempt=%s/%s: %s",
                            deal.id,
                            attempt,
                            retries,
                            last_error,
                        )
                    if attempt < retries:
                        await asyncio.sleep(backoff * (2 ** (attempt - 1)))
                else:
                    return PositionSendResult(
                        success=False,
                        correlation_id=correlation_id,
                        error=last_error or "exhausted retries",
                    )

        return PositionSendResult(
            success=True,
            correlation_id=correlation_id,
            external_ref=",".join(accepted_refs) if accepted_refs else None,
        )

    async def _auth_headers(self, client: httpx.AsyncClient) -> dict[str, str]:
        if not settings.position_auth_required:
            return {}

        token = await self._service_token(client)
        return {"Authorization": f"Bearer {token}"}

    async def _service_token(self, client: httpx.AsyncClient) -> str:
        if self._token.access_token and self._token.expires_at_monotonic > time.monotonic() + 30:
            return self._token.access_token

        if not settings.position_auth_client_id or not settings.position_auth_client_secret:
            raise RuntimeError(
                "POSITION_AUTH_CLIENT_ID/POSITION_AUTH_CLIENT_SECRET are not configured"
            )

        token_url = f"{settings.idp_base_url.rstrip('/')}/api/v1/oauth/token"
        response = await client.post(
            token_url,
            headers={"Content-Type": "application/x-www-form-urlencoded"},
            data={
                "grant_type": "client_credentials",
                "client_id": settings.position_auth_client_id,
                "client_secret": settings.position_auth_client_secret,
                "scope": settings.position_auth_scope,
            },
        )
        response.raise_for_status()
        payload = response.json()
        token = payload.get("accessToken") or payload.get("access_token")
        if not token:
            raise RuntimeError("IdP token response does not contain accessToken")

        expires_in = int(payload.get("expiresIn") or payload.get("expires_in") or 900)
        self._token.access_token = str(token)
        self._token.expires_at_monotonic = time.monotonic() + max(expires_in, 60)
        return self._token.access_token

    async def positions_report(self, on_date: date, currency_code: str | None = None) -> dict[str, Any]:
        if not settings.position_system_url:
            raise RuntimeError("POSITION_SYSTEM_URL is not configured")

        base_url = settings.position_system_url.rstrip("/")
        params: dict[str, str] = {"date": on_date.isoformat()}
        if currency_code:
            params["currency_code"] = currency_code.upper()

        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.get(
                f"{base_url}/integration/reports/positions",
                params=params,
                headers=await self._auth_headers(client),
            )
            response.raise_for_status()
            return response.json()
