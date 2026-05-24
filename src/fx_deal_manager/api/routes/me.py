from typing import Annotated

from fastapi import APIRouter, Depends

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.domain.schemas import MeResponse, UserClaims

router = APIRouter(tags=["auth"])


@router.get("/me", summary="Current authenticated user")
def get_me(user: Annotated[UserClaims, Depends(get_current_user)]) -> MeResponse:
    return MeResponse(
        user_id=user.user_id,
        email=user.email,
        first_name=user.first_name,
        last_name=user.last_name,
        role=user.role,
    )
