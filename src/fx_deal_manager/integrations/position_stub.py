import asyncio
import uuid
from dataclasses import dataclass

import httpx

from fx_deal_manager.core.config import settings
from fx_deal_manager.core.logging import get_logger
from fx_deal_manager.domain.models import FXDeal

logger = get_logger(__name__)


@dataclass(frozen=True)
class PositionSendResult:
    success: bool
    correlation_id: str
    external_ref: str | None = None
    error: str | None = None


class PositionSystemAdapter:
    async def send_deal(self, deal: FXDeal) -> PositionSendResult:
        correlation_id = str(uuid.uuid4())
        payload = _build_payload(deal, correlation_id)
        retries = settings.position_send_retries
        backoff = settings.position_send_backoff_seconds

        for attempt in range(1, retries + 1):
            try:
                result = await self._send_once(payload, correlation_id)
                logger.info(
                    "Position stub accepted deal %s correlation_id=%s attempt=%s",
                    deal.id,
                    correlation_id,
                    attempt,
                )
                return result
            except Exception as exc:
                logger.warning(
                    "Position send failed deal=%s correlation_id=%s attempt=%s/%s: %s",
                    deal.id,
                    correlation_id,
                    attempt,
                    retries,
                    exc,
                )
                if attempt == retries:
                    return PositionSendResult(
                        success=False,
                        correlation_id=correlation_id,
                        error=str(exc),
                    )
                await asyncio.sleep(backoff * (2 ** (attempt - 1)))

        return PositionSendResult(
            success=False,
            correlation_id=correlation_id,
            error="Position send exhausted retries",
        )

    async def _send_once(self, payload: dict, correlation_id: str) -> PositionSendResult:
        if settings.position_system_url:
            async with httpx.AsyncClient(timeout=10.0) as client:
                response = await client.post(
                    settings.position_system_url.rstrip("/") + "/deals",
                    json=payload,
                    headers={"X-Correlation-Id": correlation_id},
                )
                response.raise_for_status()
                body = response.json()
                return PositionSendResult(
                    success=True,
                    correlation_id=correlation_id,
                    external_ref=body.get("externalRef") or body.get("id"),
                )

        return InProcessPositionStub.receive(payload, correlation_id)


class InProcessPositionStub:
    _received: list[dict] = []

    @classmethod
    def receive(cls, payload: dict, correlation_id: str) -> PositionSendResult:
        record = {"correlation_id": correlation_id, **payload}
        cls._received.append(record)
        logger.info("In-process position stub stored deal correlation_id=%s", correlation_id)
        return PositionSendResult(
            success=True,
            correlation_id=correlation_id,
            external_ref=f"STUB-{correlation_id[:8]}",
        )

    @classmethod
    def reset(cls) -> None:
        cls._received.clear()

    @classmethod
    def all_received(cls) -> list[dict]:
        return list(cls._received)


def _build_payload(deal: FXDeal, correlation_id: str) -> dict:
    return {
        "dealId": str(deal.id),
        "correlationId": correlation_id,
        "tradeDate": deal.trade_date.isoformat(),
        "valueDate": deal.value_date.isoformat() if deal.value_date else None,
        "dealType": deal.deal_type.code,
        "operationDirection": deal.operation_direction,
        "buyCurrency": deal.buy_currency,
        "sellCurrency": deal.sell_currency,
        "amount": str(deal.amount),
        "rate": str(deal.rate),
        "counterpartyId": deal.counterparty_id,
        "payments": [
            {
                "amount": str(payment.amount),
                "currency": payment.currency_code,
                "direction": payment.payment_direction.code,
                "accountCode": payment.account_code,
                "valueDate": payment.value_date.isoformat() if payment.value_date else None,
            }
            for payment in deal.payments
        ],
    }
