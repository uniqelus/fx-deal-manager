from decimal import Decimal
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.models import DealStateLookup, FXDeal
from fx_deal_manager.domain.schemas import QuoteResponse, UserClaims

router = APIRouter(prefix="/quotes", tags=["quotes"])


@router.get("", summary="Last-trade FX quotes")
async def list_quotes(
    user: Annotated[UserClaims, Depends(require_role("TRADER", "POSITIONER", "ADMIN", "AUDITOR"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> list[QuoteResponse]:
    _ = user
    stmt = (
        select(FXDeal)
        .join(DealStateLookup, DealStateLookup.id == FXDeal.deal_state_id)
        .where(DealStateLookup.code != "CANCELLED")
        .options(selectinload(FXDeal.deal_state))
        .order_by(FXDeal.updated_at.desc())
        .limit(300)
    )
    deals = list((await session.execute(stmt)).scalars().all())
    latest: dict[str, FXDeal] = {}
    previous: dict[str, FXDeal] = {}
    for deal in deals:
        pair = f"{deal.buy_currency}/{deal.sell_currency}"
        if pair not in latest:
            latest[pair] = deal
        elif pair not in previous:
            previous[pair] = deal

    quotes: list[QuoteResponse] = []
    for pair, deal in sorted(latest.items()):
        prev = previous.get(pair)
        delta = Decimal("0")
        if prev and prev.rate:
            delta = ((deal.rate - prev.rate) / prev.rate * Decimal("100")).quantize(Decimal("0.0001"))
        quotes.append(
            QuoteResponse(
                pair=pair,
                base_currency=deal.buy_currency,
                quote_currency=deal.sell_currency,
                mid=deal.rate,
                bid=deal.rate,
                ask=deal.rate,
                spread=Decimal("0"),
                delta_percent=delta,
                source="LAST_FX_DEAL",
                updated_at=deal.updated_at,
            )
        )
    return quotes
