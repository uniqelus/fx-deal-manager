import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import get_bearer_token, require_role
from fx_deal_manager.core.config import settings
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.schemas import (
    CounterpartyResponse,
    CurrencyResponse,
    NostroAccountResponse,
    UserClaims,
)
from fx_deal_manager.integrations import nsi_client
from fx_deal_manager.services.nsi_service import NsiService

logger = logging.getLogger(__name__)

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
    token: Annotated[str | None, Depends(get_bearer_token)],
) -> list[CounterpartyResponse]:
    _ = user
    if settings.nsi_base_url and token:
        try:
            return await nsi_client.fetch_counterparties(token)
        except Exception as exc:  # noqa: BLE001 - degrade to local NSI on upstream failure
            logger.warning("NSI upstream counterparties failed, using local: %s", exc)
    return await service.list_counterparties()


@router.get("/currencies", summary="List currencies")
async def list_currencies(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[NsiService, Depends(get_nsi_service)],
    token: Annotated[str | None, Depends(get_bearer_token)],
) -> list[CurrencyResponse]:
    _ = user
    if settings.nsi_base_url and token:
        try:
            return await nsi_client.fetch_currencies(token)
        except Exception as exc:  # noqa: BLE001 - degrade to local NSI on upstream failure
            logger.warning("NSI upstream currencies failed, using local: %s", exc)
    return await service.list_currencies()


@router.get("/nostro-accounts", summary="List active nostro accounts")
async def list_nostro_accounts(
    user: Annotated[UserClaims, Depends(require_role(*ALL_ROLES))],
    service: Annotated[NsiService, Depends(get_nsi_service)],
    token: Annotated[str | None, Depends(get_bearer_token)],
    currency_code: str | None = Query(default=None),
) -> list[NostroAccountResponse]:
    _ = user
    if settings.nsi_base_url and token:
        try:
            return await nsi_client.fetch_nostro_accounts(token, currency_code)
        except Exception as exc:  # noqa: BLE001 - degrade to local NSI on upstream failure
            logger.warning("NSI upstream accounts failed, using local: %s", exc)
    return await service.list_nostro_accounts(currency_code)
