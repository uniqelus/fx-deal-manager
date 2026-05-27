from datetime import date
from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.models import DealStateLookup, FXDeal, Payment, PaymentDirectionLookup
from fx_deal_manager.domain.schemas import (
    FxPositionAccountResponse,
    FxPositionCurrencyResponse,
    FxPositionsResponse,
    UserClaims,
)
from fx_deal_manager.integrations.position_client import PositionSystemAdapter

router = APIRouter(prefix="/positions", tags=["positions"])


@router.get("", summary="NOSTRO balances and open FX exposure")
async def positions_overview(
    user: Annotated[UserClaims, Depends(require_role("POSITIONER", "ADMIN", "AUDITOR"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    on_date: date = Query(default_factory=date.today, alias="date"),
) -> FxPositionsResponse:
    _ = user
    exposure = await _open_exposure_by_currency(session)
    accounts: list[FxPositionAccountResponse] = []

    try:
        blob = await PositionSystemAdapter().positions_report(on_date)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(
            status_code=status.HTTP_502_BAD_GATEWAY,
            detail=f"POSITIONS-ASUBANK contract unavailable: {exc}",
        ) from exc

    for row in blob.get("positions") or []:
        if not isinstance(row, dict):
            continue
        accounts.append(
            FxPositionAccountResponse(
                account_number=str(row.get("account_number") or ""),
                name=row.get("name") or row.get("account_name"),
                currency_code=str(row.get("currency_code") or "").upper(),
                opening_balance=_dec(row.get("opening_balance")),
                turnover_in=_dec(row.get("turnover_in")),
                turnover_out=_dec(row.get("turnover_out")),
                current_position=_dec(row.get("current_position")),
                source="POSITIONS-ASUBANK",
            )
        )

    totals: dict[str, Decimal] = {}
    for account in accounts:
        totals.setdefault(account.currency_code, Decimal("0"))
        totals[account.currency_code] += account.current_position or Decimal("0")
    for currency_code in exposure:
        totals.setdefault(currency_code, Decimal("0"))

    currencies = [
        FxPositionCurrencyResponse(
            currency_code=currency_code,
            current_position=current,
            open_exposure=exposure.get(currency_code, Decimal("0")),
            projected_position=current + exposure.get(currency_code, Decimal("0")),
        )
        for currency_code, current in sorted(totals.items())
        if currency_code
    ]
    return FxPositionsResponse(date=on_date, source="POSITIONS-ASUBANK", accounts=accounts, currencies=currencies)


async def _open_exposure_by_currency(session: AsyncSession) -> dict[str, Decimal]:
    stmt = (
        select(Payment.currency_code, Payment.amount, PaymentDirectionLookup.code)
        .join(FXDeal, FXDeal.id == Payment.deal_id)
        .join(DealStateLookup, DealStateLookup.id == FXDeal.deal_state_id)
        .join(PaymentDirectionLookup, PaymentDirectionLookup.id == Payment.payment_direction_id)
        .where(DealStateLookup.code.in_(("DRAFT", "WAITING_FOR_POSITIONER", "APPROVED")))
    )
    exposure: dict[str, Decimal] = {}
    for currency_code, amount, direction in (await session.execute(stmt)).all():
        sign = Decimal("1") if direction == "IN" else Decimal("-1")
        exposure[currency_code] = exposure.get(currency_code, Decimal("0")) + (amount * sign)
    return exposure


def _dec(value) -> Decimal | None:
    if value is None or value == "":
        return None
    return Decimal(str(value))
