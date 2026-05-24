from fastapi import APIRouter
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.core.config import settings
from fx_deal_manager.core.database import engine
from fx_deal_manager.core.logging import get_logger

router = APIRouter(tags=["health"])
logger = get_logger(__name__)


@router.get("/health", summary="Health check")
async def health_check() -> dict[str, str]:
    logger.debug("Health check requested")
    db_status = "ok"
    try:
        async with AsyncSession(engine) as session:
            await session.execute(text("SELECT 1"))
    except Exception:
        logger.exception("Database health check failed")
        db_status = "unavailable"

    return {
        "status": "ok" if db_status == "ok" else "degraded",
        "service": settings.app_name,
        "database": db_status,
    }
