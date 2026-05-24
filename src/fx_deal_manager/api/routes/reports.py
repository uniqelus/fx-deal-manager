"""Reports endpoints (FR-019).

Exports filtered deals as JSON or CSV. Available to AUDITOR/ADMIN/POSITIONER.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.enums import DealState, DealType
from fx_deal_manager.domain.schemas import DealListResponse, UserClaims
from fx_deal_manager.services.deal_service import DealService

router = APIRouter(prefix="/reports", tags=["reports"])

ALL_REPORT_ROLES = ("AUDITOR", "POSITIONER", "ADMIN")
CSV_COLUMNS = (
    "deal_id",
    "trade_date",
    "value_date",
    "deal_type",
    "operation",
    "buy_currency",
    "sell_currency",
    "amount",
    "rate",
    "counterparty_id",
    "counterparty_name",
    "status",
    "validation_status",
    "trader_email",
    "positioner_id",
    "created_at",
    "updated_at",
)


async def get_deal_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DealService:
    return DealService(session)


@router.get("/deals", summary="Export deals report (JSON or CSV)", response_model=None)
async def deals_report(
    user: Annotated[UserClaims, Depends(require_role(*ALL_REPORT_ROLES))],
    service: Annotated[DealService, Depends(get_deal_service)],
    status: DealState | None = Query(default=None),
    deal_type: DealType | None = Query(default=None),
    counterparty_id: str | None = Query(default=None),
    trade_date_from: date | None = Query(default=None),
    trade_date_to: date | None = Query(default=None),
    fmt: Literal["json", "csv"] = Query(default="json", alias="format"),
    page_size: int = Query(default=1000, ge=1, le=10000),
) -> DealListResponse | StreamingResponse:
    _ = user
    payload = await service.list_deals(
        status=status,
        deal_type=deal_type,
        counterparty_id=counterparty_id,
        trade_date_from=trade_date_from,
        trade_date_to=trade_date_to,
        search=None,
        page=1,
        page_size=page_size,
    )
    if fmt == "json":
        return payload

    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect="excel")
    writer.writerow(CSV_COLUMNS)
    for deal in payload.items:
        writer.writerow(
            [
                str(deal.id),
                deal.trade_date.isoformat(),
                deal.value_date.isoformat() if deal.value_date else "",
                deal.deal_type.value,
                deal.operation_direction.value,
                deal.buy_currency,
                deal.sell_currency,
                f"{deal.amount}",
                f"{deal.rate}",
                deal.counterparty_id,
                deal.counterparty_name or "",
                deal.status.value,
                deal.validation_status.value,
                deal.trader_email,
                deal.positioner_id or "",
                deal.created_at.isoformat(),
                deal.updated_at.isoformat(),
            ]
        )
    buffer.seek(0)
    filename = f"deals_report_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
