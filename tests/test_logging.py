from fx_deal_manager.core.logging import get_logger, setup_logging


def test_setup_logging() -> None:
    setup_logging("DEBUG")
    logger = get_logger("fx_deal_manager.test")
    assert logger.level == 0  # NOTSET — level inherited from root

    setup_logging("INFO")
