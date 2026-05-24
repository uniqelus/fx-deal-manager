def main() -> None:
    import uvicorn

    from fx_deal_manager.core.config import settings
    from fx_deal_manager.core.logging import setup_logging

    setup_logging(settings.effective_log_level)

    uvicorn.run(
        "fx_deal_manager.main:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level=settings.effective_log_level.lower(),
    )
