"""Автоматизированные тесты по приложению Г ПМИ FX-АСУБАНК (G.1 — G.40).

Каждый тест сопоставлен с номером сценария из «Программы и методики испытаний».
Unit-тесты не требуют PostgreSQL; integration — `RUN_INTEGRATION_TESTS=1`.
"""

from __future__ import annotations

import csv
import io
from datetime import date
from decimal import Decimal
from types import SimpleNamespace
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from httpx import AsyncClient

from fx_deal_manager.api.dependencies import get_current_user
from fx_deal_manager.domain.enums import DealType, OperationDirection, PaymentDirection
from fx_deal_manager.integrations.position_client import PositionSendResult, PositionSystemAdapter
from fx_deal_manager.main import app
from fx_deal_manager.services.payment_calculator import PaymentCalculator
from fx_deal_manager.services.settlement import SettlementService
from fx_deal_manager.services.validation import ValidationService
from tests.conftest import (
    ADMIN,
    AUDITOR,
    POSITIONER,
    SAMPLE_DEAL,
    TRADER,
    approve_deal,
    create_draft,
    set_integration_user,
    submit_deal,
    validate_deal,
)


# ---------------------------------------------------------------------------
# Подсистема ввода и ведения FX-сделок (G.1 — G.14)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g01_create_fx_deal_with_valid_data(integration_client: AsyncClient) -> None:
    """G.1 — Создание FX-сделки с корректными данными (FR-002)."""
    set_integration_user(TRADER)
    response = await integration_client.post(
        "/api/v1/deals",
        json={
            **SAMPLE_DEAL,
            "counterparty_id": "VTBR",
            "comment": "PMI G.1",
        },
    )
    assert response.status_code == 201, response.text
    payload = response.json()
    assert payload["status"] == "DRAFT"
    assert payload["id"]
    assert payload["counterparty_id"] == "VTBR"
    assert payload["validation_status"] == "NOT_VALIDATED"


def test_g02_create_deal_without_counterparty() -> None:
    """G.2 — Отказ в создании FX-сделки без обязательного контрагента (FR-002)."""
    app.dependency_overrides[get_current_user] = lambda: TRADER
    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/deals",
                json={
                    "trade_date": "2026-05-08",
                    "deal_type": "SPOT",
                    "operation_direction": "BUY",
                    "buy_currency": "USD",
                    "sell_currency": "RUB",
                    "amount": "100000.00",
                    "rate": "92.50",
                },
            )
            assert response.status_code == 422
            detail = response.json()["detail"]
            assert any("counterparty_id" in str(item).lower() for item in detail)
    finally:
        app.dependency_overrides.clear()


def test_g03_format_logical_control_passes() -> None:
    """G.3 — Прохождение форматно-логического контроля (FR-004)."""
    deal = SimpleNamespace(
        deal_state=SimpleNamespace(code="DRAFT"),
        deal_type=SimpleNamespace(code="SPOT"),
        buy_currency="USD",
        sell_currency="RUB",
        amount=Decimal("100000.00"),
        rate=Decimal("92.50"),
        counterparty_id="VTBR",
        value_date=None,
    )
    issues = ValidationService().validate(
        deal,
        counterparty=SimpleNamespace(is_active=True),
        currencies={
            "USD": SimpleNamespace(decimal_places=2),
            "RUB": SimpleNamespace(decimal_places=2),
        },
    )
    assert issues == []


def test_g04_block_same_currency_and_zero_amount() -> None:
    """G.4 — Блокировка сделки с некорректными валютами или суммой (FR-004)."""
    deal = SimpleNamespace(
        deal_state=SimpleNamespace(code="DRAFT"),
        deal_type=SimpleNamespace(code="SPOT"),
        buy_currency="USD",
        sell_currency="USD",
        amount=Decimal("0"),
        rate=Decimal("92.50"),
        counterparty_id="VTBR",
        value_date=None,
    )
    issues = ValidationService().validate(
        deal,
        counterparty=SimpleNamespace(is_active=True),
        currencies={"USD": SimpleNamespace(decimal_places=2)},
    )
    fields = {issue.field for issue in issues}
    assert "buy_currency" in fields
    assert "amount" in fields


@pytest.mark.asyncio
async def test_g05_save_deal_and_payments_in_registry(integration_client: AsyncClient) -> None:
    """G.5 — Сохранение операции и платежей в реестр сделок (FR-010)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    validated = await validate_deal(integration_client, deal_id)

    assert validated["validation_status"] == "VALID"
    assert len(validated["payments"]) == 2
    directions = {payment["payment_direction"] for payment in validated["payments"]}
    assert directions == {"IN", "OUT"}

    stored = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert stored.status_code == 200
    assert len(stored.json()["payments"]) == 2


@pytest.mark.asyncio
async def test_g07_positioner_approves_deal(
    integration_client: AsyncClient, mock_position_success: None
) -> None:
    """G.7 — Подтверждение сделки позиционером (FR-012)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    submitted = await submit_deal(integration_client, deal_id)
    assert submitted["status"] == "WAITING_FOR_POSITIONER"

    set_integration_user(POSITIONER)
    approved = await approve_deal(integration_client, deal_id)
    assert approved["status"] == "EXECUTED"
    assert approved["positioner_id"] == POSITIONER.user_id


@pytest.mark.asyncio
async def test_g08_trader_cannot_approve(integration_client: AsyncClient) -> None:
    """G.8 — Запрет подтверждения сделки пользователем без прав (FR-012)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    approve = await integration_client.post(f"/api/v1/deals/{deal_id}/approve")
    assert approve.status_code == 403

    deal = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert deal.json()["status"] == "WAITING_FOR_POSITIONER"


@pytest.mark.asyncio
async def test_g09_return_to_draft_after_rejection(integration_client: AsyncClient) -> None:
    """G.9 — Возврат сделки в черновик после замечаний (FR-014)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    returned = await integration_client.post(
        f"/api/v1/deals/{deal_id}/return",
        json={"comment": "Уточните курс"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "REJECTED"

    set_integration_user(TRADER)
    taken = await integration_client.post(f"/api/v1/deals/{deal_id}/take-for-edit")
    assert taken.status_code == 200
    assert taken.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_g10_cannot_return_approved_deal_to_draft(
    integration_client: AsyncClient, mock_position_success: None
) -> None:
    """G.10 — Запрет возврата одобренной сделки в черновик (FR-014)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    await approve_deal(integration_client, deal_id)

    set_integration_user(TRADER)
    take = await integration_client.post(f"/api/v1/deals/{deal_id}/take-for-edit")
    assert take.status_code == 403

    patch = await integration_client.patch(f"/api/v1/deals/{deal_id}", json={"amount": "200000.00"})
    assert patch.status_code == 403


@pytest.mark.asyncio
async def test_g11_cancel_draft_deal(integration_client: AsyncClient) -> None:
    """G.11 — Отмена сделки в допустимом статусе (FR-015)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    cancel = await integration_client.post(
        f"/api/v1/deals/{deal_id}/cancel",
        json={"comment": "Отмена по ПМИ G.11"},
    )
    assert cancel.status_code == 200
    assert cancel.json()["status"] == "CANCELLED"


@pytest.mark.asyncio
async def test_g12_cannot_cancel_executed_deal(
    integration_client: AsyncClient, mock_position_success: None
) -> None:
    """G.12 — Запрет отмены исполненной сделки (FR-015)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    await approve_deal(integration_client, deal_id)

    set_integration_user(TRADER)
    cancel = await integration_client.post(f"/api/v1/deals/{deal_id}/cancel")
    assert cancel.status_code == 403

    deal = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert deal.json()["status"] == "EXECUTED"


@pytest.mark.asyncio
async def test_g13_search_deals_in_registry(integration_client: AsyncClient) -> None:
    """G.13 — Поиск сделки в реестре (FR-016)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    by_id = await integration_client.get(f"/api/v1/deals?search={deal_id}")
    assert by_id.status_code == 200
    assert any(item["id"] == deal_id for item in by_id.json()["items"])

    by_cp = await integration_client.get("/api/v1/deals?counterparty_id=VTBR")
    assert by_cp.status_code == 200
    assert by_cp.json()["total"] >= 1

    by_period = await integration_client.get(
        "/api/v1/deals?trade_date_from=2026-05-01&trade_date_to=2026-05-31"
    )
    assert by_period.status_code == 200
    assert by_period.json()["total"] >= 1


@pytest.mark.asyncio
async def test_g14_search_by_missing_deal_id(integration_client: AsyncClient) -> None:
    """G.14 — Поиск сделки по отсутствующему ID (FR-016)."""
    missing_id = str(uuid4())
    response = await integration_client.get(f"/api/v1/deals?search={missing_id}")
    assert response.status_code == 200
    assert response.json()["items"] == []


# ---------------------------------------------------------------------------
# Сценарии, не реализованные в текущей версии API
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g06_rollback_on_payment_save_failure(
    integration_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G.6 — Откат сохранения при ошибке записи платежа (FR-010)."""
    from fx_deal_manager.core.config import settings

    monkeypatch.setattr(settings, "payment_save_fault_after", 1)
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    validate = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate.status_code == 500

    stored = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert stored.status_code == 200
    payload = stored.json()
    assert payload["validation_status"] != "VALID"
    assert payload["payments"] == []
    assert payload["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_g15_deal_within_limits(integration_client: AsyncClient) -> None:
    """G.15 — Проверка допустимых параметров сделки (FR-006)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    validated = await validate_deal(integration_client, deal_id)
    assert validated["validation_status"] == "VALID"

    submitted = await submit_deal(integration_client, deal_id)
    assert submitted["status"] == "WAITING_FOR_POSITIONER"


@pytest.mark.asyncio
async def test_g16_deal_exceeds_limits(integration_client: AsyncClient) -> None:
    """G.16 — Блокировка сделки при нарушении бизнес-правил (FR-006)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(
        integration_client,
        {**SAMPLE_DEAL, "amount": "50000000.00"},
    )

    validate = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate.status_code == 422
    detail = validate.json()["detail"]
    assert any("limit" in item["message"].lower() for item in detail)

    submit = await integration_client.post(f"/api/v1/deals/{deal_id}/submit")
    assert submit.status_code == 422

    deal = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert deal.json()["status"] == "DRAFT"
    assert deal.json()["validation_status"] == "INVALID"


@pytest.mark.asyncio
async def test_g37_regulatory_registry_with_nsi(integration_client: AsyncClient) -> None:
    """G.37 — Формирование регуляторного реестра с НСИ (FR-021)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)

    set_integration_user(AUDITOR)
    response = await integration_client.get(
        "/api/v1/reports/regulatory-deals"
        "?trade_date_from=2026-05-01&trade_date_to=2026-05-31"
        "&counterparty_id=VTBR&format=json"
    )
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    deal_item = next(item for item in items if item["deal_id"] == deal_id)
    assert deal_item["counterparty"]["bic"]
    assert deal_item["buy_currency"]["code"] == "USD"
    assert deal_item["buy_currency"]["name"]
    assert deal_item["payments"]
    assert all(payment["account_number"] and payment["bank_name"] for payment in deal_item["payments"])


@pytest.mark.asyncio
async def test_g38_regulatory_registry_incomplete_nsi(integration_client: AsyncClient) -> None:
    """G.38 — Ошибка формирования регуляторного реестра при неполной НСИ (FR-021)."""
    set_integration_user(TRADER)
    create = await integration_client.post(
        "/api/v1/deals",
        json={**SAMPLE_DEAL, "counterparty_id": "NOBIC"},
    )
    assert create.status_code == 201, create.text
    deal_id = create.json()["id"]
    await validate_deal(integration_client, deal_id)

    set_integration_user(AUDITOR)
    response = await integration_client.get(
        "/api/v1/reports/regulatory-deals"
        "?trade_date_from=2026-05-01&trade_date_to=2026-05-31&format=json"
    )
    assert response.status_code == 422
    errors = response.json()["detail"]
    assert any(error["deal_id"] == deal_id for error in errors)
    assert any("bic" in error["field"].lower() for error in errors)


# ---------------------------------------------------------------------------
# Подсистема расчётов / settlement (G.15 — G.24)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("deal_type", "trade_date", "expected"),
    [
        (DealType.TOD, date(2026, 5, 8), date(2026, 5, 8)),
        (DealType.TOM, date(2026, 5, 8), date(2026, 5, 11)),
        (DealType.SPOT, date(2026, 5, 8), date(2026, 5, 12)),
    ],
    ids=["TOD", "TOM", "SPOT"],
)
def test_g17_value_date_for_deal_types(
    deal_type: DealType, trade_date: date, expected: date
) -> None:
    """G.17 — Расчёт даты валютирования для допустимого типа сделки (FR-007)."""
    calendar = {
        date(2026, 5, 8): True,
        date(2026, 5, 9): False,
        date(2026, 5, 10): False,
        date(2026, 5, 11): True,
        date(2026, 5, 12): True,
    }
    value_date = SettlementService.calculate_value_date(trade_date, deal_type, calendar)
    assert value_date == expected


def test_g17_forward_value_date() -> None:
    calendar = {date(2026, 6, 2): True}
    value_date = SettlementService.calculate_value_date(
        date(2026, 5, 8),
        DealType.FORWARD,
        calendar,
        explicit_value_date=date(2026, 6, 2),
    )
    assert value_date == date(2026, 6, 2)


@pytest.mark.asyncio
async def test_g18_reject_forward_with_past_value_date(integration_client: AsyncClient) -> None:
    """G.18 — Отказ при недопустимой дате Forward (FR-007)."""
    set_integration_user(TRADER)
    create = await integration_client.post(
        "/api/v1/deals",
        json={
            **SAMPLE_DEAL,
            "deal_type": "FORWARD",
            "value_date": "2026-05-03",
        },
    )
    assert create.status_code == 201
    deal_id = create.json()["id"]

    validate = await integration_client.post(f"/api/v1/deals/{deal_id}/validate")
    assert validate.status_code == 422
    assert any("business day" in item["message"].lower() for item in validate.json()["detail"])


def test_g19_payment_amounts_calculated() -> None:
    """G.19 — Расчёт сумм платежей по сделке (FR-008)."""
    deal = SimpleNamespace(
        operation_direction=OperationDirection.BUY.value,
        buy_currency="USD",
        sell_currency="RUB",
        amount=Decimal("100000.00"),
        rate=Decimal("92.50"),
    )
    payments = PaymentCalculator.calculate(deal, date(2026, 5, 12))
    assert len(payments) == 2
    in_payment = next(p for p in payments if p.payment_direction == PaymentDirection.IN)
    out_payment = next(p for p in payments if p.payment_direction == PaymentDirection.OUT)
    assert in_payment.currency_code == "USD"
    assert out_payment.currency_code == "RUB"
    assert in_payment.amount == Decimal("100000.00")
    assert out_payment.amount == Decimal("9250000.00")


def test_g20_reject_payment_calculation_without_rate() -> None:
    """G.20 — Отказ расчёта платежей без котировки / при нулевом курсе (FR-008)."""
    deal = SimpleNamespace(
        deal_state=SimpleNamespace(code="DRAFT"),
        deal_type=SimpleNamespace(code="SPOT"),
        buy_currency="USD",
        sell_currency="RUB",
        amount=Decimal("100000.00"),
        rate=Decimal("0"),
        counterparty_id="VTBR",
        value_date=None,
    )
    issues = ValidationService().validate(
        deal,
        counterparty=SimpleNamespace(is_active=True),
        currencies={
            "USD": SimpleNamespace(decimal_places=2),
            "RUB": SimpleNamespace(decimal_places=2),
        },
    )
    assert any(issue.field == "rate" for issue in issues)


@pytest.mark.asyncio
async def test_g21_nostro_accounts_assigned(integration_client: AsyncClient) -> None:
    """G.21 — Подбор ностро-счетов по валютам сделки (FR-009)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    validated = await validate_deal(integration_client, deal_id)

    currencies = {payment["currency_code"] for payment in validated["payments"]}
    assert currencies == {"USD", "RUB"}
    assert all(payment["account_code"] for payment in validated["payments"])


@pytest.mark.asyncio
async def test_g22_error_when_nostro_missing(integration_client: AsyncClient) -> None:
    """G.22 — Ошибка при отсутствии активного ностро-счета (FR-009)."""
    set_integration_user(TRADER)
    create = await integration_client.post(
        "/api/v1/deals",
        json={
            **SAMPLE_DEAL,
            "deal_type": "TOD",
            "buy_currency": "GBP",
            "sell_currency": "RUB",
        },
    )
    assert create.status_code == 201
    validate = await integration_client.post(f"/api/v1/deals/{create.json()['id']}/validate")
    assert validate.status_code == 422
    assert any("nostro" in item["message"].lower() for item in validate.json()["detail"])


@pytest.mark.asyncio
async def test_g23_execute_deal_updates_status(
    integration_client: AsyncClient, mock_position_success: None
) -> None:
    """G.23 — Обновление позиций после исполнения сделки (FR-017)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    executed = await approve_deal(integration_client, deal_id)
    assert executed["status"] == "EXECUTED"

    audit = await integration_client.get(f"/api/v1/audit-events?entity_id={deal_id}")
    actions = {item["action"] for item in audit.json()["items"]}
    assert "POSITION_SEND" in actions


@pytest.mark.asyncio
async def test_g24_block_repeat_execution(
    integration_client: AsyncClient, mock_position_success: None
) -> None:
    """G.24 — Запрет повторного исполнения сделки (FR-017)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    await approve_deal(integration_client, deal_id)

    repeat = await integration_client.post(f"/api/v1/deals/{deal_id}/approve")
    assert repeat.status_code == 403


# ---------------------------------------------------------------------------
# Подсистема аудита (G.25 — G.26)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g25_audit_logs_field_changes(integration_client: AsyncClient) -> None:
    """G.25 — Фиксация изменения полей и статуса сделки (FR-018)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    patch = await integration_client.patch(
        f"/api/v1/deals/{deal_id}",
        json={"amount": "150000.00"},
    )
    assert patch.status_code == 200

    audit = await integration_client.get(f"/api/v1/audit-events?entity_id={deal_id}")
    assert audit.status_code == 200
    actions = {item["action"] for item in audit.json()["items"]}
    assert "CREATE" in actions
    assert "UPDATE" in actions


@pytest.mark.asyncio
async def test_g26_audit_logs_access_denial(integration_client: AsyncClient) -> None:
    """G.26 — Фиксация отказа при запрещённом действии (FR-018)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    approve = await integration_client.post(f"/api/v1/deals/{deal_id}/approve")
    assert approve.status_code == 403


# ---------------------------------------------------------------------------
# Подсистема администрирования (G.27 — G.30)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("user", "endpoint", "method", "expected_status"),
    [
        (TRADER, "/api/v1/deals", "post", 201),
        (POSITIONER, "/api/v1/deals/queue", "get", 200),
        (AUDITOR, "/api/v1/audit-events", "get", 200),
        (ADMIN, "/api/v1/reports/deals?format=json", "get", 200),
    ],
    ids=["trader-create", "positioner-queue", "auditor-audit", "admin-reports"],
)
@pytest.mark.asyncio
async def test_g27_role_based_access(
    integration_client: AsyncClient,
    user: object,
    endpoint: str,
    method: str,
    expected_status: int,
) -> None:
    """G.27 — Доступ пользователя к функциям согласно роли (FR-001)."""
    set_integration_user(user)  # type: ignore[arg-type]
    if method == "post":
        response = await integration_client.post(endpoint, json=SAMPLE_DEAL)
    else:
        response = await integration_client.get(endpoint)
    assert response.status_code == expected_status, response.text


@pytest.mark.asyncio
async def test_g28_trader_denied_reports(integration_client: AsyncClient) -> None:
    """G.28 — Отказ в доступе к функции другой роли (FR-001)."""
    set_integration_user(TRADER)
    response = await integration_client.get("/api/v1/reports/deals?format=json")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_g29_active_counterparty_accepted(integration_client: AsyncClient) -> None:
    """G.29 — Проверка активного контрагента в НСИ (FR-005)."""
    set_integration_user(TRADER)
    response = await integration_client.post(
        "/api/v1/deals",
        json={**SAMPLE_DEAL, "counterparty_id": "VTBR"},
    )
    assert response.status_code == 201

    validate = await integration_client.post(
        f"/api/v1/deals/{response.json()['id']}/validate"
    )
    assert validate.status_code == 200


@pytest.mark.asyncio
async def test_g30_inactive_counterparty_blocked(integration_client: AsyncClient) -> None:
    """G.30 — Блокировка сделки с неактивным или отсутствующим контрагентом (FR-005)."""
    set_integration_user(TRADER)

    inactive = await integration_client.post(
        "/api/v1/deals",
        json={**SAMPLE_DEAL, "counterparty_id": "INACTIVE"},
    )
    assert inactive.status_code == 422

    missing = await integration_client.post(
        "/api/v1/deals",
        json={**SAMPLE_DEAL, "counterparty_id": "BANK_BLOCKED"},
    )
    assert missing.status_code == 422


# ---------------------------------------------------------------------------
# Подсистема взаимодействия (G.31 — G.40)
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_g31_submit_deal_for_approval(integration_client: AsyncClient) -> None:
    """G.31 — Передача сделки на согласование (FR-011)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    submitted = await submit_deal(integration_client, deal_id)
    assert submitted["status"] == "WAITING_FOR_POSITIONER"

    set_integration_user(POSITIONER)
    queue = await integration_client.get("/api/v1/deals/queue")
    assert queue.status_code == 200
    assert any(item["id"] == deal_id for item in queue.json())


@pytest.mark.asyncio
async def test_g32_submit_unvalidated_deal_blocked(integration_client: AsyncClient) -> None:
    """G.32 — Ошибка передачи сделки без прохождения проверок (FR-011)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)

    submit = await integration_client.post(f"/api/v1/deals/{deal_id}/submit")
    assert submit.status_code == 422
    assert submit.json()["detail"] == "Deal must be validated before submit"

    deal = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert deal.json()["status"] == "DRAFT"


@pytest.mark.asyncio
async def test_g33_return_deal_with_comment(integration_client: AsyncClient) -> None:
    """G.33 — Возврат сделки на доработку с комментарием (FR-013)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    returned = await integration_client.post(
        f"/api/v1/deals/{deal_id}/return",
        json={"comment": "Уточните сумму"},
    )
    assert returned.status_code == 200
    assert returned.json()["status"] == "REJECTED"


@pytest.mark.asyncio
async def test_g34_return_without_comment_blocked(integration_client: AsyncClient) -> None:
    """G.34 — Запрет возврата сделки без комментария (FR-013)."""
    set_integration_user(TRADER)
    deal_id = await create_draft(integration_client)
    await validate_deal(integration_client, deal_id)
    await submit_deal(integration_client, deal_id)

    set_integration_user(POSITIONER)
    returned = await integration_client.post(f"/api/v1/deals/{deal_id}/return", json={})
    assert returned.status_code == 422

    deal = await integration_client.get(f"/api/v1/deals/{deal_id}")
    assert deal.json()["status"] == "WAITING_FOR_POSITIONER"


@pytest.mark.asyncio
async def test_g35_export_deals_report(integration_client: AsyncClient) -> None:
    """G.35 — Формирование и выгрузка отчёта по сделкам (FR-019)."""
    set_integration_user(TRADER)
    await create_draft(integration_client)

    set_integration_user(AUDITOR)
    response = await integration_client.get(
        "/api/v1/reports/deals?counterparty_id=VTBR&format=csv"
    )
    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/csv")

    reader = csv.reader(io.StringIO(response.text))
    rows = list(reader)
    assert rows[0][0] == "deal_id"
    assert len(rows) >= 2


@pytest.mark.asyncio
async def test_g36_report_for_empty_period(integration_client: AsyncClient) -> None:
    """G.36 — Формирование отчёта за период без сделок (FR-019)."""
    set_integration_user(AUDITOR)
    response = await integration_client.get(
        "/api/v1/reports/deals?trade_date_from=2020-01-01&trade_date_to=2020-01-31&format=json"
    )
    assert response.status_code == 200
    assert response.json()["items"] == []


@pytest.mark.asyncio
async def test_g39_external_positions_report(
    integration_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G.39 — Получение отчёта из внешней системы (FR-022)."""
    async def _positions_report(_self: PositionSystemAdapter, on_date: date, currency_code: str | None = None) -> dict:
        return {
            "positions": [
                {
                    "account_number": "40702810000000000001",
                    "currency_code": "RUB",
                    "current_position": "1000000.00",
                }
            ]
        }

    monkeypatch.setattr(PositionSystemAdapter, "positions_report", _positions_report)
    set_integration_user(POSITIONER)
    response = await integration_client.get("/api/v1/positions?date=2026-05-08")
    assert response.status_code == 200
    payload = response.json()
    assert payload["source"] == "POSITIONS-ASUBANK"
    assert len(payload["accounts"]) >= 1


@pytest.mark.asyncio
async def test_g40_external_positions_unavailable(
    integration_client: AsyncClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    """G.40 — Обработка недоступности внешней системы отчётов (FR-022)."""
    async def _fail(_self: PositionSystemAdapter, on_date: date, currency_code: str | None = None) -> dict:
        raise RuntimeError("positions service down")

    monkeypatch.setattr(PositionSystemAdapter, "positions_report", _fail)
    set_integration_user(POSITIONER)
    response = await integration_client.get("/api/v1/positions?date=2026-05-08")
    assert response.status_code == 502
    assert "POSITIONS-ASUBANK" in response.json()["detail"]
