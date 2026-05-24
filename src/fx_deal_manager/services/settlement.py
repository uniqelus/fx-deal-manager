from datetime import date, timedelta

from fx_deal_manager.domain.enums import DealType


class SettlementService:
    @staticmethod
    def calculate_value_date(
        trade_date: date,
        deal_type: DealType,
        calendar: dict[date, bool],
        explicit_value_date: date | None = None,
    ) -> date:
        if deal_type == DealType.FORWARD:
            if explicit_value_date is None:
                raise ValueError("FORWARD deals require an explicit value date")
            if not calendar.get(explicit_value_date, False):
                raise ValueError(f"{explicit_value_date} is not a business day")
            return explicit_value_date

        offset = {
            DealType.TOD: 0,
            DealType.TOM: 1,
            DealType.SPOT: 2,
        }[deal_type]
        return _add_business_days(trade_date, offset, calendar)


def _add_business_days(start: date, business_days: int, calendar: dict[date, bool]) -> date:
    if business_days == 0:
        current = start
        while not calendar.get(current, False):
            current += timedelta(days=1)
            if (current - start).days > 366:
                raise ValueError(f"No business day found on or after {start}")
        return current

    current = start
    added = 0
    while added < business_days:
        current += timedelta(days=1)
        if calendar.get(current, False):
            added += 1
        if (current - start).days > 366:
            raise ValueError(f"Could not add {business_days} business days from {start}")
    return current
