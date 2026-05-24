from datetime import date
from decimal import Decimal
from types import SimpleNamespace

from fx_deal_manager.domain.enums import DealType, OperationDirection, PaymentDirection
from fx_deal_manager.services.payment_calculator import PaymentCalculator
from fx_deal_manager.services.settlement import SettlementService
from fx_deal_manager.services.validation import ValidationService


def _deal(**overrides):
    defaults = {
        "deal_state": SimpleNamespace(code="DRAFT"),
        "deal_type": SimpleNamespace(code="SPOT"),
        "buy_currency": "USD",
        "sell_currency": "RUB",
        "amount": Decimal("100000.00"),
        "rate": Decimal("92.50"),
        "counterparty_id": "VTBR",
        "value_date": None,
    }
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def test_validation_rejects_same_currency() -> None:
    deal = _deal(buy_currency="USD", sell_currency="USD")
    issues = ValidationService().validate(
        deal,
        counterparty=SimpleNamespace(is_active=True),
        currencies={"USD": SimpleNamespace(decimal_places=2)},
    )
    assert any(issue.field == "buy_currency" for issue in issues)


def test_validation_rejects_inactive_counterparty() -> None:
    deal = _deal()
    issues = ValidationService().validate(
        deal,
        counterparty=SimpleNamespace(is_active=False),
        currencies={
            "USD": SimpleNamespace(decimal_places=2),
            "RUB": SimpleNamespace(decimal_places=2),
        },
    )
    assert any(issue.field == "counterparty_id" for issue in issues)


def test_settlement_spot_t_plus_two() -> None:
    calendar = {
        date(2026, 5, 8): True,
        date(2026, 5, 9): False,
        date(2026, 5, 10): False,
        date(2026, 5, 11): True,
        date(2026, 5, 12): True,
    }
    value_date = SettlementService.calculate_value_date(
        date(2026, 5, 8), DealType.SPOT, calendar
    )
    assert value_date == date(2026, 5, 12)


def test_settlement_tod_rolls_to_business_day() -> None:
    calendar = {date(2026, 5, 9): False, date(2026, 5, 10): False, date(2026, 5, 11): True}
    value_date = SettlementService.calculate_value_date(
        date(2026, 5, 9), DealType.TOD, calendar
    )
    assert value_date == date(2026, 5, 11)


def test_payment_calculator_buy() -> None:
    deal = _deal(operation_direction=OperationDirection.BUY.value)
    payments = PaymentCalculator.calculate(deal, date(2026, 5, 12))
    assert len(payments) == 2
    assert payments[0].payment_direction == PaymentDirection.IN
    assert payments[0].currency_code == "USD"
    assert payments[0].amount == Decimal("100000.00")
    assert payments[1].payment_direction == PaymentDirection.OUT
    assert payments[1].currency_code == "RUB"
    assert payments[1].amount == Decimal("9250000.00")


def test_payment_calculator_sell() -> None:
    deal = _deal(operation_direction=OperationDirection.SELL.value)
    payments = PaymentCalculator.calculate(deal, date(2026, 5, 12))
    assert payments[0].payment_direction == PaymentDirection.OUT
    assert payments[0].currency_code == "USD"
    assert payments[1].payment_direction == PaymentDirection.IN
    assert payments[1].currency_code == "RUB"
