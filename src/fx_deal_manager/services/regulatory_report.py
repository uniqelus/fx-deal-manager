import json
from dataclasses import dataclass
from datetime import date
from typing import Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.domain.enums import DealState, DealType, OperationDirection, ValidationStatus
from fx_deal_manager.domain.models import Currency, FXDeal, NostroAccount
from fx_deal_manager.repositories.deal_repository import DealRepository
from fx_deal_manager.repositories.nsi_repository import NsiRepository
from fx_deal_manager.services.audit_log_service import AuditLogService


@dataclass(frozen=True)
class RegulatoryNsiError:
    deal_id: str
    field: str
    message: str

    def as_dict(self) -> dict[str, str]:
        return {
            "deal_id": self.deal_id,
            "field": self.field,
            "message": self.message,
        }


class RegulatoryReportIncompleteError(Exception):
    def __init__(self, errors: list[RegulatoryNsiError]) -> None:
        self.errors = errors
        super().__init__("Regulatory report NSI validation failed")


class RegulatoryReportService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._deals = DealRepository(session)
        self._nsi = NsiRepository(session)
        self._audit = AuditLogService(session)

    async def generate(
        self,
        *,
        trade_date_from: date | None,
        trade_date_to: date | None,
        counterparty_id: str | None = None,
        created_by: str,
    ) -> list[dict[str, Any]]:
        deals = await self._deals.list_deals_for_regulatory_report(
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            counterparty_id=counterparty_id,
        )
        currencies = await self._nsi.currencies_by_code()
        nostro_by_number = await self._nsi.nostro_by_account_number()
        nostro_by_id = await self._nsi.nostro_by_id()

        errors = self._validate_nsi(deals, currencies, nostro_by_number, nostro_by_id)
        if errors:
            await self._audit.log(
                entity_id=deals[0].id if deals else UUID(int=0),
                entity_type="RegulatoryReport",
                action="REGULATORY_REPORT_FAILED",
                created_by=created_by,
                new_value=json.dumps([error.as_dict() for error in errors]),
            )
            await self._deals.commit()
            raise RegulatoryReportIncompleteError(errors)

        return [
            self._serialize_deal(deal, currencies, nostro_by_number, nostro_by_id) for deal in deals
        ]

    def _resolve_nostro(
        self,
        account_code: str,
        nostro_by_number: dict[str, NostroAccount],
        nostro_by_id: dict[str, NostroAccount],
    ) -> NostroAccount | None:
        return nostro_by_number.get(account_code) or nostro_by_id.get(account_code)

    def _validate_nsi(
        self,
        deals: list[FXDeal],
        currencies: dict[str, Currency],
        nostro_by_number: dict[str, NostroAccount],
        nostro_by_id: dict[str, NostroAccount],
    ) -> list[RegulatoryNsiError]:
        errors: list[RegulatoryNsiError] = []
        for deal in deals:
            if deal.validation_status.code != ValidationStatus.VALID.value:
                continue

            deal_id = str(deal.id)
            counterparty = deal.counterparty
            if counterparty is None:
                errors.append(
                    RegulatoryNsiError(deal_id, "counterparty_id", "Counterparty is missing in NSI")
                )
            else:
                if not counterparty.id:
                    errors.append(
                        RegulatoryNsiError(deal_id, "counterparty.id", "Counterparty id is required")
                    )
                if not counterparty.name:
                    errors.append(
                        RegulatoryNsiError(deal_id, "counterparty.name", "Counterparty name is required")
                    )
                if not counterparty.bic:
                    errors.append(
                        RegulatoryNsiError(deal_id, "counterparty.bic", "Counterparty BIC is required")
                    )

            if deal.buy_currency not in currencies:
                errors.append(
                    RegulatoryNsiError(
                        deal_id,
                        "buy_currency",
                        f"Currency '{deal.buy_currency}' is not in NSI",
                    )
                )
            if deal.sell_currency not in currencies:
                errors.append(
                    RegulatoryNsiError(
                        deal_id,
                        "sell_currency",
                        f"Currency '{deal.sell_currency}' is not in NSI",
                    )
                )

            for payment in deal.payments:
                if not payment.account_code:
                    errors.append(
                        RegulatoryNsiError(
                            deal_id,
                            "payment.account_code",
                            "Payment account_code is required for regulatory export",
                        )
                    )
                    continue
                nostro = self._resolve_nostro(payment.account_code, nostro_by_number, nostro_by_id)
                if nostro is None:
                    errors.append(
                        RegulatoryNsiError(
                            deal_id,
                            "payment.account_code",
                            f"Nostro account '{payment.account_code}' is not in NSI",
                        )
                    )
                elif not nostro.is_active:
                    errors.append(
                        RegulatoryNsiError(
                            deal_id,
                            "payment.account_code",
                            f"Nostro account '{payment.account_code}' is inactive",
                        )
                    )

        return errors

    def _serialize_deal(
        self,
        deal: FXDeal,
        currencies: dict[str, Currency],
        nostro_by_number: dict[str, NostroAccount],
        nostro_by_id: dict[str, NostroAccount],
    ) -> dict[str, Any]:
        counterparty = deal.counterparty
        buy_currency = currencies[deal.buy_currency]
        sell_currency = currencies[deal.sell_currency]
        payments: list[dict[str, Any]] = []
        for payment in deal.payments:
            nostro = self._resolve_nostro(payment.account_code or "", nostro_by_number, nostro_by_id)
            payments.append(
                {
                    "direction": payment.payment_direction.code,
                    "amount": f"{payment.amount}",
                    "currency": payment.currency_code,
                    "value_date": payment.value_date.isoformat() if payment.value_date else None,
                    "account_code": payment.account_code,
                    "account_number": nostro.account_number if nostro else None,
                    "bank_name": nostro.bank_name if nostro else None,
                }
            )

        return {
            "deal_id": str(deal.id),
            "trade_date": deal.trade_date.isoformat(),
            "value_date": deal.value_date.isoformat() if deal.value_date else None,
            "deal_type": DealType(deal.deal_type.code).value,
            "operation_direction": OperationDirection(deal.operation_direction).value,
            "buy_currency": {
                "code": buy_currency.code,
                "name": buy_currency.name,
                "decimal_places": buy_currency.decimal_places,
            },
            "sell_currency": {
                "code": sell_currency.code,
                "name": sell_currency.name,
                "decimal_places": sell_currency.decimal_places,
            },
            "amount": f"{deal.amount}",
            "rate": f"{deal.rate}",
            "status": DealState(deal.deal_state.code).value,
            "validation_status": ValidationStatus(deal.validation_status.code).value,
            "trader_id": deal.trader_id,
            "trader_email": deal.trader_email,
            "positioner_id": deal.positioner_id,
            "counterparty": {
                "id": counterparty.id if counterparty else deal.counterparty_id,
                "name": counterparty.name if counterparty else None,
                "bic": counterparty.bic if counterparty else None,
                "country": counterparty.country if counterparty else None,
                "is_active": counterparty.is_active if counterparty else None,
            },
            "payments": payments,
        }
