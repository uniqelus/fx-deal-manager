from datetime import datetime
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.domain.schemas import AuditEventListResponse, AuditEventResponse
from fx_deal_manager.repositories.audit_repository import AuditRepository


class AuditLogService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = AuditRepository(session)

    async def log(
        self,
        *,
        entity_id: UUID,
        entity_type: str,
        action: str,
        created_by: str,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> None:
        await self._repo.append(
            entity_id=entity_id,
            entity_type=entity_type,
            action=action,
            created_by=created_by,
            old_value=old_value,
            new_value=new_value,
        )

    async def list_events(
        self,
        *,
        entity_id: UUID | None = None,
        user_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditEventListResponse:
        rows, total = await self._repo.list_events(
            entity_id=entity_id,
            user_id=user_id,
            date_from=date_from,
            date_to=date_to,
            page=page,
            page_size=page_size,
        )
        return AuditEventListResponse(
            items=[AuditEventResponse.model_validate(row) for row in rows],
            total=total,
            page=page,
            page_size=page_size,
        )
