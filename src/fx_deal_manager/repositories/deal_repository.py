from datetime import date
from uuid import UUID

from sqlalchemy import Select, String, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from fx_deal_manager.domain.enums import DealState, DealType, PaymentDirection, ValidationStatus
from fx_deal_manager.domain.models import (
    Counterparty,
    DealStateLookup,
    DealTypeLookup,
    FXDeal,
    Payment,
    PaymentDirectionLookup,
    ValidationStatusLookup,
)


class DealNotFoundError(Exception):
    pass


class LookupCache:
    _deal_states: dict[str, int] | None = None
    _deal_types: dict[str, int] | None = None
    _validation_statuses: dict[str, int] | None = None
    _payment_directions: dict[str, int] | None = None

    @classmethod
    async def payment_direction_id(cls, session: AsyncSession, code: PaymentDirection) -> int:
        if cls._payment_directions is None:
            rows = await session.execute(select(PaymentDirectionLookup))
            cls._payment_directions = {row.code: row.id for row in rows.scalars()}
        return cls._payment_directions[code.value]

    @classmethod
    async def deal_state_id(cls, session: AsyncSession, code: DealState) -> int:
        if cls._deal_states is None:
            rows = await session.execute(select(DealStateLookup))
            cls._deal_states = {row.code: row.id for row in rows.scalars()}
        return cls._deal_states[code.value]

    @classmethod
    async def deal_type_id(cls, session: AsyncSession, code: DealType) -> int:
        if cls._deal_types is None:
            rows = await session.execute(select(DealTypeLookup))
            cls._deal_types = {row.code: row.id for row in rows.scalars()}
        return cls._deal_types[code.value]

    @classmethod
    async def validation_status_id(cls, session: AsyncSession, code: ValidationStatus) -> int:
        if cls._validation_statuses is None:
            rows = await session.execute(select(ValidationStatusLookup))
            cls._validation_statuses = {row.code: row.id for row in rows.scalars()}
        return cls._validation_statuses[code.value]

    @classmethod
    def clear(cls) -> None:
        cls._deal_states = None
        cls._deal_types = None
        cls._validation_statuses = None
        cls._payment_directions = None


class DealRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def replace_payments(self, deal: FXDeal, payments: list[Payment]) -> None:
        deal.payments.clear()
        deal.payments.extend(payments)
        await self._session.flush()

    async def set_validation_status(self, deal: FXDeal, status: ValidationStatus) -> None:
        deal.validation_status_id = await LookupCache.validation_status_id(self._session, status)
        self._session.expire(deal, ["validation_status"])

    async def set_deal_state(self, deal: FXDeal, state: DealState) -> None:
        deal.deal_state_id = await LookupCache.deal_state_id(self._session, state)
        self._session.expire(deal, ["deal_state"])

    async def save_new(self, deal: FXDeal) -> FXDeal:
        self._session.add(deal)
        await self._session.flush()
        return await self.get_by_id(deal.id)

    async def save_existing(self, deal: FXDeal) -> FXDeal:
        await self._session.flush()
        return await self.get_by_id(deal.id)

    async def commit(self) -> None:
        await self._session.commit()

    async def get_by_id(self, deal_id: UUID) -> FXDeal:
        stmt = (
            select(FXDeal)
            .where(FXDeal.id == deal_id)
            .options(
                selectinload(FXDeal.payments).selectinload(Payment.payment_direction),
                selectinload(FXDeal.deal_type),
                selectinload(FXDeal.deal_state),
                selectinload(FXDeal.validation_status),
                selectinload(FXDeal.counterparty),
                selectinload(FXDeal.positioner_solution),
            )
        )
        result = await self._session.execute(stmt)
        deal = result.scalar_one_or_none()
        if deal is None:
            raise DealNotFoundError(str(deal_id))
        return deal

    async def list_deals(
        self,
        *,
        status: DealState | None = None,
        deal_type: DealType | None = None,
        counterparty_id: str | None = None,
        trade_date_from: date | None = None,
        trade_date_to: date | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> tuple[list[FXDeal], int]:
        stmt: Select[tuple[FXDeal]] = select(FXDeal).options(
            selectinload(FXDeal.payments).selectinload(Payment.payment_direction),
            selectinload(FXDeal.deal_type),
            selectinload(FXDeal.deal_state),
            selectinload(FXDeal.validation_status),
            selectinload(FXDeal.counterparty),
        )
        count_stmt = select(func.count()).select_from(FXDeal)

        if status is not None:
            state_id = await LookupCache.deal_state_id(self._session, status)
            stmt = stmt.where(FXDeal.deal_state_id == state_id)
            count_stmt = count_stmt.where(FXDeal.deal_state_id == state_id)

        if deal_type is not None:
            type_id = await LookupCache.deal_type_id(self._session, deal_type)
            stmt = stmt.where(FXDeal.deal_type_id == type_id)
            count_stmt = count_stmt.where(FXDeal.deal_type_id == type_id)

        if counterparty_id is not None:
            stmt = stmt.where(FXDeal.counterparty_id == counterparty_id)
            count_stmt = count_stmt.where(FXDeal.counterparty_id == counterparty_id)

        if trade_date_from is not None:
            stmt = stmt.where(FXDeal.trade_date >= trade_date_from)
            count_stmt = count_stmt.where(FXDeal.trade_date >= trade_date_from)

        if trade_date_to is not None:
            stmt = stmt.where(FXDeal.trade_date <= trade_date_to)
            count_stmt = count_stmt.where(FXDeal.trade_date <= trade_date_to)

        if search:
            search_term = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(
                    FXDeal.counterparty_id.ilike(search_term),
                    func.cast(FXDeal.id, String).ilike(search_term),
                )
            )
            count_stmt = count_stmt.where(
                or_(
                    FXDeal.counterparty_id.ilike(search_term),
                    func.cast(FXDeal.id, String).ilike(search_term),
                )
            )

        total = (await self._session.execute(count_stmt)).scalar_one()
        offset = (page - 1) * page_size
        stmt = stmt.order_by(FXDeal.created_at.desc()).offset(offset).limit(page_size)
        rows = (await self._session.execute(stmt)).scalars().all()
        return list(rows), total

    async def counterparty_exists(self, counterparty_id: str) -> bool:
        result = await self._session.execute(
            select(Counterparty.id).where(
                Counterparty.id == counterparty_id,
                Counterparty.is_active.is_(True),
            )
        )
        return result.scalar_one_or_none() is not None
