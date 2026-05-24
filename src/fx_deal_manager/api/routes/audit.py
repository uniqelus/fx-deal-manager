from datetime import datetime
from typing import Annotated
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.schemas import AuditEventListResponse, UserClaims
from fx_deal_manager.services.audit_log_service import AuditLogService

router = APIRouter(prefix="/audit-events", tags=["audit"])

ALL_ROLES = ("TRADER", "POSITIONER", "AUDITOR", "ADMIN")


async def get_audit_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> AuditLogService:
    return AuditLogService(session)


@router.get("", summary="Query audit log events")
async def list_audit_events(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[AuditLogService, Depends(get_audit_service)],
    entity_id: UUID | None = Query(default=None),
    user_id: str | None = Query(default=None, description="Filter by created_by (email substring)"),
    date_from: datetime | None = Query(default=None, alias="from"),
    date_to: datetime | None = Query(default=None, alias="to"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> AuditEventListResponse:
    _ = user
    return await service.list_events(
        entity_id=entity_id,
        user_id=user_id,
        date_from=date_from,
        date_to=date_to,
        page=page,
        page_size=page_size,
    )
