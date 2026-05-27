from sqlalchemy import or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.domain.models import DealLimit


class LimitRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active_limits(self, counterparty_id: str) -> list[DealLimit]:
        stmt = (
            select(DealLimit)
            .where(
                DealLimit.is_active.is_(True),
                or_(
                    DealLimit.counterparty_id.is_(None),
                    DealLimit.counterparty_id == counterparty_id,
                ),
            )
            .order_by(DealLimit.id)
        )
        return list((await self._session.execute(stmt)).scalars().all())
