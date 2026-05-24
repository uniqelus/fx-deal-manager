from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.domain.models import BusinessCalendar, Counterparty, Currency, NostroAccount


class NsiRepository:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_counterparties(self, *, active_only: bool = True) -> list[Counterparty]:
        stmt = select(Counterparty).order_by(Counterparty.id)
        if active_only:
            stmt = stmt.where(Counterparty.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def get_counterparty(self, counterparty_id: str) -> Counterparty | None:
        return await self._session.get(Counterparty, counterparty_id)

    async def list_currencies(self) -> list[Currency]:
        stmt = select(Currency).order_by(Currency.code)
        return list((await self._session.execute(stmt)).scalars().all())

    async def currencies_by_code(self) -> dict[str, Currency]:
        return {currency.code: currency for currency in await self.list_currencies()}

    async def list_nostro_accounts(
        self, *, currency_code: str | None = None, active_only: bool = True
    ) -> list[NostroAccount]:
        stmt = select(NostroAccount).order_by(NostroAccount.id)
        if currency_code is not None:
            stmt = stmt.where(NostroAccount.currency_code == currency_code.upper())
        if active_only:
            stmt = stmt.where(NostroAccount.is_active.is_(True))
        return list((await self._session.execute(stmt)).scalars().all())

    async def nostro_by_currency(self) -> dict[str, NostroAccount]:
        accounts = await self.list_nostro_accounts(active_only=True)
        result: dict[str, NostroAccount] = {}
        for account in accounts:
            result.setdefault(account.currency_code, account)
        return result

    async def load_calendar(self, start: date, end: date) -> dict[date, bool]:
        stmt = select(BusinessCalendar).where(
            BusinessCalendar.calendar_date >= start,
            BusinessCalendar.calendar_date <= end,
        )
        rows = (await self._session.execute(stmt)).scalars().all()
        calendar = {row.calendar_date: row.is_business_day for row in rows}

        current = start
        while current <= end:
            calendar.setdefault(current, current.weekday() < 5)
            current += timedelta(days=1)
        return calendar
