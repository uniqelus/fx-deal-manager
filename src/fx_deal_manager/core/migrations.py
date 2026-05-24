import asyncio
from logging import getLogger

from alembic import command
from alembic.config import Config

logger = getLogger(__name__)


def run_migrations() -> None:
    alembic_cfg = Config("alembic.ini")
    command.upgrade(alembic_cfg, "head")
    logger.info("Database migrations applied")


async def run_migrations_async() -> None:
    await asyncio.to_thread(run_migrations)
