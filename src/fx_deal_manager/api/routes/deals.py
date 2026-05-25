from datetime import date
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.enums import DealState, DealType
from fx_deal_manager.domain.schemas import (
    DealCreateRequest,
    DealListResponse,
    DealResponse,
    DealUpdateRequest,
    PositionerCommentRequest,
    UserClaims,
)
from fx_deal_manager.services.approval_service import ApprovalService
from fx_deal_manager.services.deal_service import DealService

router = APIRouter(prefix="/deals", tags=["deals"])

ALL_ROLES = ("TRADER", "POSITIONER", "AUDITOR", "ADMIN")


async def get_deal_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> DealService:
    return DealService(session)


async def get_approval_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> ApprovalService:
    return ApprovalService(session)


@router.post("", status_code=201, summary="Create FX deal (DRAFT)")
async def create_deal(
    payload: DealCreateRequest,
    user: Annotated[UserClaims, Depends(require_role("TRADER", "ADMIN"))],
    service: Annotated[DealService, Depends(get_deal_service)],
) -> DealResponse:
    return await service.create_deal(payload, user)


@router.get("", summary="List deals with filters")
async def list_deals(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[DealService, Depends(get_deal_service)],
    status: DealState | None = Query(default=None, alias="status"),
    deal_type: DealType | None = Query(default=None, alias="deal_type"),
    counterparty_id: str | None = Query(default=None),
    trade_date_from: date | None = Query(default=None),
    trade_date_to: date | None = Query(default=None),
    search: str | None = Query(default=None, description="Search by deal ID or counterparty"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> DealListResponse:
    _ = user
    return await service.list_deals(
        status=status,
        deal_type=deal_type,
        counterparty_id=counterparty_id,
        trade_date_from=trade_date_from,
        trade_date_to=trade_date_to,
        search=search,
        page=page,
        page_size=page_size,
    )


@router.get("/queue", summary="Positioner approval queue")
async def get_queue(
    user: Annotated[UserClaims, Depends(require_role("POSITIONER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> list[DealResponse]:
    _ = user
    return await service.get_queue(page=page, page_size=page_size)


@router.get("/{deal_id}", summary="Get deal by ID")
async def get_deal(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[DealService, Depends(get_deal_service)],
) -> DealResponse:
    _ = user
    return await service.get_deal(deal_id)


@router.patch("/{deal_id}", summary="Update deal (DRAFT only, creator only)")
async def update_deal(
    deal_id: UUID,
    payload: DealUpdateRequest,
    user: Annotated[UserClaims, Depends(require_role("TRADER", "ADMIN"))],
    service: Annotated[DealService, Depends(get_deal_service)],
) -> DealResponse:
    return await service.update_deal(deal_id, payload, user)


@router.post("/{deal_id}/validate", summary="Validate deal and calculate payments")
async def validate_deal(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role("TRADER", "ADMIN"))],
    service: Annotated[DealService, Depends(get_deal_service)],
) -> DealResponse:
    return await service.validate_deal(deal_id, user)


@router.post("/{deal_id}/submit", summary="Submit deal for positioner approval")
async def submit_deal(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role("TRADER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> DealResponse:
    return await service.submit_deal(deal_id, user)


@router.post("/{deal_id}/approve", summary="Approve deal and send to position system")
async def approve_deal(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role("POSITIONER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> DealResponse:
    return await service.approve_deal(deal_id, user)


@router.post("/{deal_id}/return", summary="Return deal for edit")
async def return_deal(
    deal_id: UUID,
    payload: PositionerCommentRequest,
    user: Annotated[UserClaims, Depends(require_role("POSITIONER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> DealResponse:
    return await service.return_deal(deal_id, payload.comment, user)


@router.post("/{deal_id}/reject", summary="Reject deal")
async def reject_deal(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role("POSITIONER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
    payload: PositionerCommentRequest | None = None,
) -> DealResponse:
    comment = payload.comment if payload else None
    return await service.reject_deal(deal_id, comment, user)


@router.post("/{deal_id}/take-for-edit", summary="Take rejected deal back to DRAFT")
async def take_for_edit(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role("TRADER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
) -> DealResponse:
    return await service.take_for_edit(deal_id, user)


@router.post("/{deal_id}/cancel", summary="Cancel a DRAFT deal (FR-015)")
async def cancel_deal(
    deal_id: UUID,
    user: Annotated[UserClaims, Depends(require_role("TRADER", "ADMIN"))],
    service: Annotated[ApprovalService, Depends(get_approval_service)],
    payload: PositionerCommentRequest | None = None,
) -> DealResponse:
    comment = payload.comment if payload else None
    return await service.cancel_deal(deal_id, comment, user)
