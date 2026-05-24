from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP

from fx_deal_manager.domain.enums import OperationDirection, PaymentDirection
from fx_deal_manager.domain.models import FXDeal


@dataclass(frozen=True)
class CalculatedPayment:
    amount: Decimal
    currency_code: str
    payment_direction: PaymentDirection
    value_date: date


class PaymentCalculator:
    @staticmethod
    def calculate(deal: FXDeal, value_date: date) -> list[CalculatedPayment]:
        counter_amount = (deal.amount * deal.rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        direction = OperationDirection(deal.operation_direction)

        if direction == OperationDirection.BUY:
            return [
                CalculatedPayment(deal.amount, deal.buy_currency, PaymentDirection.IN, value_date),
                CalculatedPayment(
                    counter_amount, deal.sell_currency, PaymentDirection.OUT, value_date
                ),
            ]

        return [
            CalculatedPayment(deal.amount, deal.buy_currency, PaymentDirection.OUT, value_date),
            CalculatedPayment(
                counter_amount, deal.sell_currency, PaymentDirection.IN, value_date
            ),
        ]
