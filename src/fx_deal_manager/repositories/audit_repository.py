from datetime import datetime
from uuid import UUID

from sqlalchemy import Select, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.domain.models import AuditLogEntry


class AuditRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def append(
        self,
        *,
        entity_id: UUID,
        entity_type: str,
        action: str,
        created_by: str,
        old_value: str | None = None,
        new_value: str | None = None,
    ) -> AuditLogEntry:
        entry = AuditLogEntry(
            entity_id=entity_id,
            entity_type=entity_type,
            action=action,
            old_value=old_value,
            new_value=new_value,
            created_by=created_by,
        )
        self._session.add(entry)
        await self._session.flush()
        return entry

    async def list_events(
        self,
        *,
        entity_id: UUID | None = None,
        user_id: str | None = None,
        date_from: datetime | None = None,
        date_to: datetime | None = None,
        page: int = 1,
        page_size: int = 50,
    ) -> tuple[list[AuditLogEntry], int]:
        stmt: Select[tuple[AuditLogEntry]] = select(AuditLogEntry).order_by(
            AuditLogEntry.created_at.desc()
        )
        count_stmt = select(func.count()).select_from(AuditLogEntry)

        if entity_id is not None:
            stmt = stmt.where(AuditLogEntry.entity_id == entity_id)
            count_stmt = count_stmt.where(AuditLogEntry.entity_id == entity_id)
        if user_id is not None:
            stmt = stmt.where(AuditLogEntry.created_by.ilike(f"%{user_id}%"))
            count_stmt = count_stmt.where(AuditLogEntry.created_by.ilike(f"%{user_id}%"))
        if date_from is not None:
            stmt = stmt.where(AuditLogEntry.created_at >= date_from)
            count_stmt = count_stmt.where(AuditLogEntry.created_at >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditLogEntry.created_at <= date_to)
            count_stmt = count_stmt.where(AuditLogEntry.created_at <= date_to)

        total = (await self._session.execute(count_stmt)).scalar_one()
        offset = (page - 1) * page_size
        rows = (await self._session.execute(stmt.offset(offset).limit(page_size))).scalars().all()
        return list(rows), total
