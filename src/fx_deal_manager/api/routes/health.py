from fastapi import APIRouter

from fx_deal_manager.core.config import settings
from fx_deal_manager.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", summary="Health check")
def health_check() -> dict[str, str]:
    logger.debug("Health check requested")
    return {"status": "ok", "service": settings.app_name}
