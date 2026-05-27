from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.domain.schemas import (
    CounterpartyResponse,
    CurrencyResponse,
    NostroAccountResponse,
)
from fx_deal_manager.repositories.nsi_repository import NsiRepository


class NsiService:
    def __init__(self, session: AsyncSession) -> None:
        self._repo = NsiRepository(session)

    async def list_counterparties(self) -> list[CounterpartyResponse]:
        rows = await self._repo.list_counterparties(active_only=True)
        return [CounterpartyResponse.model_validate(row) for row in rows]

    async def list_currencies(self) -> list[CurrencyResponse]:
        rows = await self._repo.list_currencies()
        return [CurrencyResponse.model_validate(row) for row in rows]

    async def list_nostro_accounts(
        self, currency_code: str | None = None
    ) -> list[NostroAccountResponse]:
        rows = await self._repo.list_nostro_accounts(
            currency_code=currency_code.upper() if currency_code else None,
            active_only=True,
        )
        return [NostroAccountResponse.model_validate(row) for row in rows]

