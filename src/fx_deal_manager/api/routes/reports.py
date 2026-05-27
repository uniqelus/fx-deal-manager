"""Reports endpoints (FR-019, FR-021).

Exports filtered deals as JSON or CSV. Available to AUDITOR/ADMIN/POSITIONER.
Regulatory export with full NSI — AUDITOR/ADMIN only.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.enums import DealState, DealType
from fx_deal_manager.domain.schemas import DealListResponse, UserClaims
from fx_deal_manager.services.deal_service import DealService
from fx_deal_manager.services.regulatory_report import RegulatoryReportService

router = APIRouter(prefix="/reports", tags=["reports"])

ALL_REPORT_ROLES = ("AUDITOR", "POSITIONER", "ADMIN")
REGULATORY_REPORT_ROLES = ("AUDITOR", "ADMIN")
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


REGULATORY_CSV_COLUMNS = (
    "deal_id",
    "trade_date",
    "value_date",
    "deal_type",
    "operation_direction",
    "amount",
    "rate",
    "status",
    "validation_status",
    "trader_email",
    "positioner_id",
    "counterparty_id",
    "counterparty_name",
    "counterparty_bic",
    "counterparty_country",
    "counterparty_is_active",
    "buy_currency_code",
    "buy_currency_name",
    "buy_currency_decimal_places",
    "sell_currency_code",
    "sell_currency_name",
    "sell_currency_decimal_places",
    "payment_direction",
    "payment_amount",
    "payment_currency",
    "payment_value_date",
    "payment_account_code",
    "nostro_account_number",
    "nostro_bank_name",
)


async def get_regulatory_report_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> RegulatoryReportService:
    return RegulatoryReportService(session)


@router.get(
    "/regulatory-deals",
    summary="Regulatory deals export with NSI (FR-021)",
    response_model=None,
)
async def regulatory_deals_report(
    user: Annotated[UserClaims, Depends(require_role(*REGULATORY_REPORT_ROLES))],
    service: Annotated[RegulatoryReportService, Depends(get_regulatory_report_service)],
    trade_date_from: date | None = Query(default=None),
    trade_date_to: date | None = Query(default=None),
    counterparty_id: str | None = Query(default=None),
    fmt: Literal["json", "csv"] = Query(default="json", alias="format"),
) -> JSONResponse | StreamingResponse:
    items = await service.generate(
        trade_date_from=trade_date_from,
        trade_date_to=trade_date_to,
        counterparty_id=counterparty_id,
        created_by=user.email,
    )
    if fmt == "json":
        return JSONResponse(content={"items": items})

    buffer = io.StringIO()
    writer = csv.writer(buffer, dialect="excel")
    writer.writerow(REGULATORY_CSV_COLUMNS)
    for deal in items:
        counterparty = deal["counterparty"]
        buy_currency = deal["buy_currency"]
        sell_currency = deal["sell_currency"]
        for payment in deal["payments"]:
            writer.writerow(
                [
                    deal["deal_id"],
                    deal["trade_date"],
                    deal["value_date"] or "",
                    deal["deal_type"],
                    deal["operation_direction"],
                    deal["amount"],
                    deal["rate"],
                    deal["status"],
                    deal["validation_status"],
                    deal["trader_email"],
                    deal["positioner_id"] or "",
                    counterparty["id"],
                    counterparty["name"] or "",
                    counterparty["bic"] or "",
                    counterparty["country"] or "",
                    counterparty["is_active"],
                    buy_currency["code"],
                    buy_currency["name"],
                    buy_currency["decimal_places"],
                    sell_currency["code"],
                    sell_currency["name"],
                    sell_currency["decimal_places"],
                    payment["direction"],
                    payment["amount"],
                    payment["currency"],
                    payment["value_date"] or "",
                    payment["account_code"] or "",
                    payment["account_number"] or "",
                    payment["bank_name"] or "",
                ]
            )
    buffer.seek(0)
    filename = f"regulatory_deals_{date.today().isoformat()}.csv"
    return StreamingResponse(
        iter([buffer.getvalue()]),
        media_type="text/csv; charset=utf-8",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
