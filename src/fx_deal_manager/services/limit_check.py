from decimal import Decimal, ROUND_HALF_UP

from fx_deal_manager.domain.models import DealLimit, FXDeal
from fx_deal_manager.repositories.limit_repository import LimitRepository
from fx_deal_manager.services.validation import ValidationIssue


class LimitCheckService:
    def __init__(self, session) -> None:
        self._repo = LimitRepository(session)

    async def check(self, deal: FXDeal) -> list[ValidationIssue]:
        limits = await self._repo.list_active_limits(deal.counterparty_id)
        if not limits:
            return []

        issues: list[ValidationIssue] = []
        counter_amount = (deal.amount * deal.rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        buy_limit = _find_best_limit(limits, deal.counterparty_id, deal.buy_currency)
        if buy_limit is not None and deal.amount > buy_limit.max_amount:
            issues.append(
                ValidationIssue(
                    "amount",
                    (
                        f"Deal amount {deal.amount} {deal.buy_currency} exceeds limit "
                        f"{buy_limit.max_amount} for counterparty {deal.counterparty_id}"
                    ),
                )
            )

        sell_limit = _find_best_limit(limits, deal.counterparty_id, deal.sell_currency)
        if sell_limit is not None and counter_amount > sell_limit.max_amount:
            issues.append(
                ValidationIssue(
                    "amount",
                    (
                        f"Counter amount {counter_amount} {deal.sell_currency} exceeds limit "
                        f"{sell_limit.max_amount} for counterparty {deal.counterparty_id}"
                    ),
                )
            )

        return issues


def _find_best_limit(
    limits: list[DealLimit], counterparty_id: str, currency_code: str
) -> DealLimit | None:
    matched = [
        limit
        for limit in limits
        if (limit.counterparty_id is None or limit.counterparty_id == counterparty_id)
        and (limit.currency_code is None or limit.currency_code == currency_code)
    ]
    if not matched:
        return None

    def _specificity(limit: DealLimit) -> tuple[int, int]:
        cp_score = 1 if limit.counterparty_id == counterparty_id else 0
        cur_score = 1 if limit.currency_code == currency_code else 0
        return (cp_score, cur_score)

    return max(matched, key=_specificity)
