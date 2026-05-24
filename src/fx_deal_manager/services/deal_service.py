import json
from datetime import date, timedelta
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.exceptions import ValidationFailedError
from fx_deal_manager.domain.enums import (
    DealState,
    DealType,
    OperationDirection,
    PaymentDirection,
    ValidationStatus,
)
from fx_deal_manager.domain.models import FXDeal, Payment
from fx_deal_manager.domain.schemas import (
    DealCreateRequest,
    DealListResponse,
    DealResponse,
    DealUpdateRequest,
    PaymentResponse,
    UserClaims,
)
from fx_deal_manager.repositories.deal_repository import (
    DealNotFoundError,
    DealRepository,
    LookupCache,
)
from fx_deal_manager.repositories.nsi_repository import NsiRepository
from fx_deal_manager.services.audit_log_service import AuditLogService
from fx_deal_manager.services.nostro_assignment import NostroAssignmentService
from fx_deal_manager.services.payment_calculator import PaymentCalculator
from fx_deal_manager.services.settlement import SettlementService
from fx_deal_manager.services.validation import ValidationIssue, ValidationService


class DealService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DealRepository(session)
        self._nsi = NsiRepository(session)
        self._validation = ValidationService()
        self._audit = AuditLogService(session)

    async def create_deal(self, payload: DealCreateRequest, user: UserClaims) -> DealResponse:
        if not await self._repo.counterparty_exists(payload.counterparty_id):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"Counterparty '{payload.counterparty_id}' not found or inactive",
            )

        deal = FXDeal(
            trade_date=payload.trade_date,
            value_date=payload.value_date,
            amount=payload.amount,
            rate=payload.rate,
            buy_currency=payload.buy_currency,
            sell_currency=payload.sell_currency,
            operation_direction=payload.operation_direction.value,
            counterparty_id=payload.counterparty_id,
            deal_type_id=await LookupCache.deal_type_id(self._session, payload.deal_type),
            deal_state_id=await LookupCache.deal_state_id(self._session, DealState.DRAFT),
            validation_status_id=await LookupCache.validation_status_id(
                self._session, ValidationStatus.NOT_VALIDATED
            ),
            trader_id=user.user_id,
            trader_email=user.email,
            comment=payload.comment,
        )
        created = await self._repo.save_new(deal)
        await self._audit.log(
            entity_id=created.id,
            entity_type="FXDeal",
            action="CREATE",
            created_by=user.email,
            new_value=json.dumps({"status": DealState.DRAFT.value}),
        )
        await self._repo.commit()
        return _to_response(created)

    async def update_deal(
        self, deal_id: UUID, payload: DealUpdateRequest, user: UserClaims
    ) -> DealResponse:
        try:
            deal = await self._repo.get_by_id(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found") from exc

        if deal.deal_state.code != DealState.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only DRAFT deals can be edited",
            )
        if deal.trader_id != user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the deal creator can edit this deal",
            )

        updates = payload.model_dump(exclude_unset=True)
        if "counterparty_id" in updates:
            if not await self._repo.counterparty_exists(updates["counterparty_id"]):
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"Counterparty '{updates['counterparty_id']}' not found or inactive",
                )
            deal.counterparty_id = updates["counterparty_id"]

        if "trade_date" in updates:
            deal.trade_date = updates["trade_date"]
        if "value_date" in updates:
            deal.value_date = updates["value_date"]
        if "amount" in updates:
            deal.amount = updates["amount"]
        if "rate" in updates:
            deal.rate = updates["rate"]
        if "buy_currency" in updates:
            deal.buy_currency = updates["buy_currency"]
        if "sell_currency" in updates:
            deal.sell_currency = updates["sell_currency"]
        if "operation_direction" in updates:
            deal.operation_direction = updates["operation_direction"].value
        if "deal_type" in updates:
            deal.deal_type_id = await LookupCache.deal_type_id(self._session, updates["deal_type"])
        if "comment" in updates:
            deal.comment = updates["comment"]

        await self._repo.set_validation_status(deal, ValidationStatus.NOT_VALIDATED)
        await self._repo.replace_payments(deal, [])

        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="UPDATE",
            created_by=user.email,
            new_value=json.dumps(updates, default=str),
        )
        await self._repo.commit()
        return _to_response(updated)

    async def get_deal(self, deal_id: UUID) -> DealResponse:
        try:
            deal = await self._repo.get_by_id(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found") from exc
        return _to_response(deal)

    async def list_deals(
        self,
        *,
        status: DealState | None = None,
        deal_type: DealType | None = None,
        counterparty_id: str | None = None,
        trade_date_from: date | None = None,
        trade_date_to: date | None = None,
        search: str | None = None,
        page: int = 1,
        page_size: int = 20,
    ) -> DealListResponse:
        deals, total = await self._repo.list_deals(
            status=status,
            deal_type=deal_type,
            counterparty_id=counterparty_id,
            trade_date_from=trade_date_from,
            trade_date_to=trade_date_to,
            search=search,
            page=page,
            page_size=page_size,
        )
        return DealListResponse(
            items=[_to_response(deal) for deal in deals],
            total=total,
            page=page,
            page_size=page_size,
        )

    async def validate_deal(self, deal_id: UUID, user: UserClaims) -> DealResponse:
        try:
            deal = await self._repo.get_by_id(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found") from exc

        if deal.trader_id != user.user_id and user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the deal creator can validate this deal",
            )

        counterparty = await self._nsi.get_counterparty(deal.counterparty_id)
        currencies = await self._nsi.currencies_by_code()
        issues = self._validation.validate(deal, counterparty=counterparty, currencies=currencies)

        if issues:
            await self._repo.set_validation_status(deal, ValidationStatus.INVALID)
            await self._audit.log(
                entity_id=deal.id,
                entity_type="FXDeal",
                action="VALIDATE_FAILED",
                created_by=user.email,
                new_value=json.dumps([issue.__dict__ for issue in issues]),
            )
            await self._repo.commit()
            raise ValidationFailedError(issues)

        deal_type = DealType(deal.deal_type.code)
        calendar = await self._nsi.load_calendar(
            deal.trade_date,
            deal.trade_date + timedelta(days=30),
        )
        try:
            value_date = SettlementService.calculate_value_date(
                deal.trade_date,
                deal_type,
                calendar,
                deal.value_date,
            )
        except ValueError as exc:
            raise ValidationFailedError(
                [ValidationIssue("value_date", str(exc))]
            ) from exc

        calculated = PaymentCalculator.calculate(deal, value_date)
        nostro_map = await self._nsi.nostro_by_currency()
        assigned, nostro_errors = NostroAssignmentService.assign(calculated, nostro_map)
        if nostro_errors:
            await self._repo.set_validation_status(deal, ValidationStatus.INVALID)
            await self._audit.log(
                entity_id=deal.id,
                entity_type="FXDeal",
                action="VALIDATE_FAILED",
                created_by=user.email,
                new_value=json.dumps([error.__dict__ for error in nostro_errors]),
            )
            await self._repo.commit()
            raise ValidationFailedError(
                [ValidationIssue(error.field, error.message) for error in nostro_errors]
            )

        payment_rows: list[Payment] = []
        for calc, account_code in assigned:
            payment_rows.append(
                Payment(
                    deal_id=deal.id,
                    amount=calc.amount,
                    currency_code=calc.currency_code,
                    account_code=account_code,
                    payment_direction_id=await LookupCache.payment_direction_id(
                        self._session, calc.payment_direction
                    ),
                    value_date=calc.value_date,
                )
            )

        deal.value_date = value_date
        await self._repo.set_validation_status(deal, ValidationStatus.VALID)
        await self._repo.replace_payments(deal, payment_rows)
        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="VALIDATE",
            created_by=user.email,
            new_value=json.dumps(
                {
                    "validation_status": ValidationStatus.VALID.value,
                    "value_date": value_date.isoformat(),
                    "payments": len(payment_rows),
                }
            ),
        )
        await self._repo.commit()
        return _to_response(updated)


def _to_response(deal: FXDeal) -> DealResponse:
    return DealResponse(
        id=deal.id,
        trade_date=deal.trade_date,
        value_date=deal.value_date,
        deal_type=DealType(deal.deal_type.code),
        operation_direction=OperationDirection(deal.operation_direction),
        buy_currency=deal.buy_currency,
        sell_currency=deal.sell_currency,
        amount=deal.amount,
        rate=deal.rate,
        counterparty_id=deal.counterparty_id,
        counterparty_name=deal.counterparty.name if deal.counterparty else None,
        status=DealState(deal.deal_state.code),
        validation_status=ValidationStatus(deal.validation_status.code),
        trader_id=deal.trader_id,
        trader_email=deal.trader_email,
        positioner_id=deal.positioner_id,
        comment=deal.comment,
        payments=[
            PaymentResponse(
                id=payment.id,
                amount=payment.amount,
                currency_code=payment.currency_code,
                account_code=payment.account_code,
                payment_direction=PaymentDirection(payment.payment_direction.code),
                value_date=payment.value_date,
            )
            for payment in deal.payments
        ],
        created_at=deal.created_at,
        updated_at=deal.updated_at,
    )
