from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from fx_deal_manager.api.middleware import RequestLoggingMiddleware
from fx_deal_manager.api.exceptions import (
    RegulatoryReportIncompleteError,
    ValidationFailedError,
    regulatory_report_incomplete_handler,
    validation_failed_handler,
)
from fx_deal_manager.api.routes import (
    audit_router,
    deals_router,
    health_router,
    me_router,
    notifications_router,
    nsi_router,
    positions_router,
    quotes_router,
    reports_router,
)
from fx_deal_manager.core.config import settings
from fx_deal_manager.core.database import engine
from fx_deal_manager.core.logging import get_logger, setup_logging
from fx_deal_manager.core.migrations import run_migrations_async

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(_app: FastAPI) -> AsyncIterator[None]:
    setup_logging(settings.effective_log_level)
    logger.info("Starting %s v%s", settings.app_name, settings.app_version)
    try:
        if settings.auto_migrate:
            await run_migrations_async()
    except Exception:
        logger.exception("Database migration failed")
        raise
    yield
    await engine.dispose()
    logger.info("Shutting down %s", settings.app_name)


def create_app() -> FastAPI:
    app = FastAPI(
        title=settings.app_name,
        version=settings.app_version,
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.add_middleware(RequestLoggingMiddleware)
    app.add_exception_handler(ValidationFailedError, validation_failed_handler)
    app.add_exception_handler(RegulatoryReportIncompleteError, regulatory_report_incomplete_handler)
    app.include_router(health_router, prefix="/api/v1")
    app.include_router(me_router, prefix="/api/v1")
    app.include_router(deals_router, prefix="/api/v1")
    app.include_router(nsi_router, prefix="/api/v1")
    app.include_router(positions_router, prefix="/api/v1")
    app.include_router(quotes_router, prefix="/api/v1")
    app.include_router(notifications_router, prefix="/api/v1")
    app.include_router(audit_router, prefix="/api/v1")
    app.include_router(reports_router, prefix="/api/v1")
    return app


app = create_app()
