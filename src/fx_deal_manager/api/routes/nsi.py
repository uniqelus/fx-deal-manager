from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.schemas import (
    CounterpartyResponse,
    CurrencyResponse,
    NostroAccountResponse,
    NsiSyncResponse,
    UserClaims,
)
from fx_deal_manager.services.nsi_service import NsiService

router = APIRouter(prefix="/nsi", tags=["nsi"])

ALL_ROLES = ("TRADER", "POSITIONER", "AUDITOR", "ADMIN")


async def get_nsi_service(
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> NsiService:
    return NsiService(session)


@router.get("/counterparties", summary="List active counterparties")
async def list_counterparties(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[NsiService, Depends(get_nsi_service)],
) -> list[CounterpartyResponse]:
    _ = user
    return await service.list_counterparties()


@router.get("/currencies", summary="List currencies")
async def list_currencies(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[NsiService, Depends(get_nsi_service)],
) -> list[CurrencyResponse]:
    _ = user
    return await service.list_currencies()


@router.get("/nostro-accounts", summary="List active nostro accounts")
async def list_nostro_accounts(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[NsiService, Depends(get_nsi_service)],
    currency_code: str | None = Query(default=None),
) -> list[NostroAccountResponse]:
    _ = user
    return await service.list_nostro_accounts(currency_code)


@router.post("/sync", summary="Sync NSI from external system (stub)")
async def sync_nsi(
    user: Annotated[UserClaims, Depends(require_role("ADMIN"))],
    service: Annotated[NsiService, Depends(get_nsi_service)],
) -> NsiSyncResponse:
    _ = user
    return await service.sync_from_external()
