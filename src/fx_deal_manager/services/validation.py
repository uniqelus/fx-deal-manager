from dataclasses import dataclass
from decimal import Decimal

from fx_deal_manager.domain.enums import DealState, DealType
from fx_deal_manager.domain.models import Counterparty, Currency, FXDeal


@dataclass(frozen=True)
class ValidationIssue:
    field: str
    message: str


class ValidationService:
    def validate(
        self,
        deal: FXDeal,
        *,
        counterparty: Counterparty | None,
        currencies: dict[str, Currency],
    ) -> list[ValidationIssue]:
        issues: list[ValidationIssue] = []

        if deal.deal_state.code != DealState.DRAFT.value:
            issues.append(ValidationIssue("status", "Only DRAFT deals can be validated"))

        if deal.buy_currency == deal.sell_currency:
            issues.append(ValidationIssue("buy_currency", "Buy and sell currencies must differ"))

        if deal.amount <= 0:
            issues.append(ValidationIssue("amount", "Amount must be positive"))
        if deal.rate <= 0:
            issues.append(ValidationIssue("rate", "Rate must be positive"))

        buy = currencies.get(deal.buy_currency)
        if buy is None:
            issues.append(
                ValidationIssue("buy_currency", f"Currency '{deal.buy_currency}' is not in NSI")
            )
        elif not _decimals_valid(deal.amount, buy.decimal_places):
            issues.append(
                ValidationIssue(
                    "amount",
                    f"Amount precision exceeds {buy.decimal_places} decimals for {deal.buy_currency}",
                )
            )

        sell = currencies.get(deal.sell_currency)
        if sell is None:
            issues.append(
                ValidationIssue("sell_currency", f"Currency '{deal.sell_currency}' is not in NSI")
            )

        if counterparty is None:
            issues.append(
                ValidationIssue(
                    "counterparty_id",
                    f"Counterparty '{deal.counterparty_id}' is not in NSI",
                )
            )
        elif not counterparty.is_active:
            issues.append(
                ValidationIssue(
                    "counterparty_id",
                    f"Counterparty '{deal.counterparty_id}' is inactive",
                )
            )

        if deal.deal_type.code == DealType.FORWARD.value and deal.value_date is None:
            issues.append(
                ValidationIssue("value_date", "Value date is required for FORWARD deals")
            )

        return issues


def _decimals_valid(value: Decimal, max_places: int) -> bool:
    normalized = value.normalize()
    exponent = normalized.as_tuple().exponent
    if isinstance(exponent, int) and exponent < 0:
        return abs(exponent) <= max_places
    return True
