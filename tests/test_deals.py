import os

os.environ.setdefault("AUTO_MIGRATE", "false")

from datetime import date, datetime, timezone
from decimal import Decimal
from uuid import UUID

import pytest
from fastapi.testclient import TestClient

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.api.routes.deals import get_deal_service
from fx_deal_manager.domain.enums import DealState, DealType, OperationDirection, ValidationStatus
from fx_deal_manager.domain.schemas import DealListResponse, DealResponse, UserClaims
from fx_deal_manager.main import app

TRADER = UserClaims(
    user_id="00000000-0000-0000-0000-000000000001",
    email="trader@demo.local",
    first_name="Илья",
    last_name="Смирнов",
    role="TRADER",
    expires_at=9999999999,
)

POSITIONER = UserClaims(
    user_id="00000000-0000-0000-0000-000000000002",
    email="positioner@demo.local",
    first_name="Софья",
    last_name="Борисова",
    role="POSITIONER",
    expires_at=9999999999,
)

DEAL_ID = UUID("11111111-1111-1111-1111-111111111111")
NOW = datetime(2026, 5, 24, 12, 0, tzinfo=timezone.utc)


class FakeDealService:
    def __init__(self) -> None:
        self.last_create_user: UserClaims | None = None

    async def create_deal(self, payload, user: UserClaims) -> DealResponse:
        self.last_create_user = user
        return _sample_deal()

    async def get_deal(self, deal_id: UUID) -> DealResponse:
        if deal_id != DEAL_ID:
            from fastapi import HTTPException

            raise HTTPException(status_code=404, detail="Deal not found")
        return _sample_deal()

    async def list_deals(self, **kwargs) -> DealListResponse:
        return DealListResponse(items=[_sample_deal()], total=1, page=1, page_size=20)

    async def update_deal(self, deal_id, payload, user: UserClaims) -> DealResponse:
        return _sample_deal(amount=Decimal("800000.00"))


def _sample_deal(**overrides) -> DealResponse:
    data = dict(
        id=DEAL_ID,
        trade_date=date(2026, 5, 8),
        value_date=None,
        deal_type=DealType.SPOT,
        operation_direction=OperationDirection.BUY,
        buy_currency="USD",
        sell_currency="RUB",
        amount=Decimal("750000.00"),
        rate=Decimal("92.473200"),
        counterparty_id="VTBR",
        counterparty_name="ПАО Банк ВТБ",
        status=DealState.DRAFT,
        validation_status=ValidationStatus.NOT_VALIDATED,
        trader_id=TRADER.user_id,
        trader_email=TRADER.email,
        positioner_id=None,
        comment=None,
        payments=[],
        created_at=NOW,
        updated_at=NOW,
    )
    data.update(overrides)
    return DealResponse(**data)


@pytest.fixture
def client() -> TestClient:
    fake = FakeDealService()
    app.dependency_overrides[get_current_user] = lambda: TRADER
    app.dependency_overrides[get_deal_service] = lambda: fake
    with TestClient(app) as test_client:
        test_client.fake_service = fake  # type: ignore[attr-defined]
        yield test_client
    app.dependency_overrides.clear()


def test_create_deal_requires_trader_role() -> None:
    app.dependency_overrides[get_current_user] = lambda: POSITIONER
    app.dependency_overrides[get_deal_service] = lambda: FakeDealService()
    try:
        with TestClient(app) as test_client:
            response = test_client.post(
                "/api/v1/deals",
                json={
                    "trade_date": "2026-05-08",
                    "deal_type": "SPOT",
                    "operation_direction": "BUY",
                    "buy_currency": "USD",
                    "sell_currency": "RUB",
                    "amount": "750000.00",
                    "rate": "92.4732",
                    "counterparty_id": "VTBR",
                },
            )
            assert response.status_code == 403
    finally:
        app.dependency_overrides.clear()


def test_create_deal_success(client: TestClient) -> None:
    response = client.post(
        "/api/v1/deals",
        json={
            "trade_date": "2026-05-08",
            "deal_type": "SPOT",
            "operation_direction": "BUY",
            "buy_currency": "USD",
            "sell_currency": "RUB",
            "amount": "750000.00",
            "rate": "92.4732",
            "counterparty_id": "VTBR",
        },
    )
    assert response.status_code == 201
    payload = response.json()
    assert payload["status"] == "DRAFT"
    assert payload["counterparty_id"] == "VTBR"
    assert client.fake_service.last_create_user.email == TRADER.email  # type: ignore[attr-defined]


def test_list_deals(client: TestClient) -> None:
    response = client.get("/api/v1/deals?status=DRAFT&deal_type=SPOT")
    assert response.status_code == 200
    payload = response.json()
    assert payload["total"] == 1
    assert payload["items"][0]["deal_type"] == "SPOT"


def test_get_deal(client: TestClient) -> None:
    response = client.get(f"/api/v1/deals/{DEAL_ID}")
    assert response.status_code == 200
    assert response.json()["id"] == str(DEAL_ID)


def test_patch_deal(client: TestClient) -> None:
    response = client.patch(
        f"/api/v1/deals/{DEAL_ID}",
        json={"amount": "800000.00"},
    )
    assert response.status_code == 200
    assert response.json()["amount"] == "800000.00"
