from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.models import UserPreference
from fx_deal_manager.domain.schemas import MeProfileResponse, MeProfileUpdateRequest, UserClaims

router = APIRouter(tags=["auth"])


@router.get("/me", summary="Current authenticated user")
async def get_me(
    user: Annotated[UserClaims, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MeProfileResponse:
    pref = await session.get(UserPreference, user.user_id)
    return _profile(user, pref)


@router.patch("/me", summary="Update current user's local FX preferences")
async def update_me(
    payload: MeProfileUpdateRequest,
    user: Annotated[UserClaims, Depends(get_current_user)],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> MeProfileResponse:
    pref = await session.get(UserPreference, user.user_id)
    if pref is None:
        pref = UserPreference(user_id=user.user_id, email=user.email)
        session.add(pref)
    pref.email = user.email
    if payload.phone is not None:
        pref.phone = payload.phone
    if payload.department is not None:
        pref.department = payload.department
    await session.commit()
    await session.refresh(pref)
    return _profile(user, pref)


def _profile(user: UserClaims, pref: UserPreference | None) -> MeProfileResponse:
    return MeProfileResponse(
        user_id=user.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
        phone=pref.phone if pref else None,
        department=(pref.department if pref and pref.department else _default_department(user.role)),
    )


def _default_department(role: str) -> str:
    return {
        "TRADER": "FX-деск",
        "POSITIONER": "Казначейство",
        "AUDITOR": "Внутренний аудит",
        "ADMIN": "Администрирование",
    }.get(role, "FX")
