import os

os.environ.setdefault("AUTO_MIGRATE", "false")

import pytest
from httpx import ASGITransport, AsyncClient

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.domain.schemas import UserClaims
from fx_deal_manager.main import app

TRADER = UserClaims(
    user_id="00000000-0000-0000-0000-000000000001",
    email="integration-trader@demo.local",
    first_name="Test",
    last_name="Trader",
    role="TRADER",
    expires_at=9999999999,
)


@pytest.fixture(scope="session")
def integration_enabled() -> bool:
    return os.getenv("RUN_INTEGRATION_TESTS", "").lower() in ("1", "true", "yes")


@pytest.fixture
async def integration_client(integration_enabled: bool):
    if not integration_enabled:
        pytest.skip("Set RUN_INTEGRATION_TESTS=1 with running PostgreSQL")
    app.dependency_overrides[get_current_user] = lambda: TRADER
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield client
    app.dependency_overrides.clear()
