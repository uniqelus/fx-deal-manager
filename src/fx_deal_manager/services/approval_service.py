import json
from uuid import UUID

from fastapi import HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.exceptions import ValidationFailedError
from fx_deal_manager.domain.enums import (
    ApprovalDecision,
    DealState,
    ValidationStatus,
)
from fx_deal_manager.domain.models import FXDeal, PositionerSolution
from fx_deal_manager.domain.schemas import DealResponse, UserClaims
from fx_deal_manager.integrations.position_client import PositionSystemAdapter
from fx_deal_manager.repositories.deal_repository import DealNotFoundError, DealRepository
from fx_deal_manager.services.audit_log_service import AuditLogService
from fx_deal_manager.services.deal_service import _to_response
from fx_deal_manager.services.limit_check import LimitCheckService


class ApprovalService:
    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._repo = DealRepository(session)
        self._audit = AuditLogService(session)
        self._limit_check = LimitCheckService(session)
        self._position = PositionSystemAdapter()

    async def submit_deal(self, deal_id: UUID, user: UserClaims) -> DealResponse:
        deal = await self._load_deal(deal_id)
        self._require_trader(deal, user)
        if deal.deal_state.code != DealState.DRAFT.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Deal is not in DRAFT")
        if deal.validation_status.code != ValidationStatus.VALID.value:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Deal must be validated before submit",
            )

        limit_issues = await self._limit_check.check(deal)
        if limit_issues:
            await self._repo.set_validation_status(deal, ValidationStatus.INVALID)
            await self._audit.log(
                entity_id=deal.id,
                entity_type="FXDeal",
                action="VALIDATE_FAILED",
                created_by=user.email,
                new_value=json.dumps([issue.__dict__ for issue in limit_issues]),
            )
            await self._repo.commit()
            raise ValidationFailedError(limit_issues)

        old_status = deal.deal_state.code
        await self._repo.set_deal_state(deal, DealState.WAITING_FOR_POSITIONER)
        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="STATUS_CHANGE",
            created_by=user.email,
            old_value=json.dumps({"status": old_status}),
            new_value=json.dumps({"status": DealState.WAITING_FOR_POSITIONER.value}),
        )
        await self._repo.commit()
        return _to_response(updated)

    async def approve_deal(self, deal_id: UUID, user: UserClaims) -> DealResponse:
        deal = await self._load_deal(deal_id)
        self._require_positioner(user)
        if deal.deal_state.code != DealState.WAITING_FOR_POSITIONER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Deal is not waiting for positioner",
            )
        if deal.trader_id == user.user_id:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Self-approval is not allowed",
            )

        old_status = deal.deal_state.code
        deal.positioner_id = user.user_id
        await self._repo.set_deal_state(deal, DealState.APPROVED)
        await self._save_solution(deal, user, ApprovalDecision.APPROVE, None)

        send_result = await self._position.send_deal(deal)
        await self._audit.log(
            entity_id=deal.id,
            entity_type="FXDeal",
            action="POSITION_SEND",
            created_by=user.email,
            new_value=json.dumps(
                {
                    "correlation_id": send_result.correlation_id,
                    "success": send_result.success,
                    "external_ref": send_result.external_ref,
                    "error": send_result.error,
                }
            ),
        )

        if not send_result.success:
            await self._repo.commit()
            raise HTTPException(
                status_code=status.HTTP_502_BAD_GATEWAY,
                detail=f"Position system rejected deal: {send_result.error}",
            )

        await self._repo.set_deal_state(deal, DealState.EXECUTED)
        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="STATUS_CHANGE",
            created_by=user.email,
            old_value=json.dumps({"status": old_status}),
            new_value=json.dumps(
                {
                    "status": DealState.EXECUTED.value,
                    "correlation_id": send_result.correlation_id,
                    "external_ref": send_result.external_ref,
                }
            ),
        )
        await self._repo.commit()
        return _to_response(updated)

    async def return_deal(self, deal_id: UUID, comment: str, user: UserClaims) -> DealResponse:
        return await self._positioner_decision(
            deal_id, user, ApprovalDecision.RETURN_FOR_EDIT, comment
        )

    async def reject_deal(self, deal_id: UUID, comment: str | None, user: UserClaims) -> DealResponse:
        return await self._positioner_decision(deal_id, user, ApprovalDecision.REJECT, comment)

    async def take_for_edit(self, deal_id: UUID, user: UserClaims) -> DealResponse:
        deal = await self._load_deal(deal_id)
        self._require_trader(deal, user)
        if deal.deal_state.code != DealState.REJECTED.value:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Deal is not rejected")

        old_status = deal.deal_state.code
        await self._repo.set_deal_state(deal, DealState.DRAFT)
        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="STATUS_CHANGE",
            created_by=user.email,
            old_value=json.dumps({"status": old_status}),
            new_value=json.dumps({"status": DealState.DRAFT.value}),
        )
        await self._repo.commit()
        return _to_response(updated)

    async def cancel_deal(
        self, deal_id: UUID, comment: str | None, user: UserClaims
    ) -> DealResponse:
        deal = await self._load_deal(deal_id)
        self._require_trader(deal, user)
        if deal.deal_state.code != DealState.DRAFT.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only DRAFT deals can be cancelled",
            )

        old_status = deal.deal_state.code
        await self._repo.set_deal_state(deal, DealState.CANCELLED)
        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="STATUS_CHANGE",
            created_by=user.email,
            old_value=json.dumps({"status": old_status}),
            new_value=json.dumps({"status": DealState.CANCELLED.value, "comment": comment}),
        )
        await self._repo.commit()
        return _to_response(updated)

    async def get_queue(self, page: int = 1, page_size: int = 20) -> list[DealResponse]:
        deals, _ = await self._repo.list_deals(
            status=DealState.WAITING_FOR_POSITIONER,
            page=page,
            page_size=page_size,
        )
        return [_to_response(deal) for deal in deals]

    async def _positioner_decision(
        self,
        deal_id: UUID,
        user: UserClaims,
        decision: ApprovalDecision,
        comment: str | None,
    ) -> DealResponse:
        deal = await self._load_deal(deal_id)
        self._require_positioner(user)
        if deal.deal_state.code != DealState.WAITING_FOR_POSITIONER.value:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Deal is not waiting for positioner",
            )
        if decision == ApprovalDecision.RETURN_FOR_EDIT and not comment:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Comment is required when returning for edit",
            )

        old_status = deal.deal_state.code
        deal.positioner_id = user.user_id
        await self._repo.set_deal_state(deal, DealState.REJECTED)
        await self._save_solution(deal, user, decision, comment)
        updated = await self._repo.save_existing(deal)
        await self._audit.log(
            entity_id=updated.id,
            entity_type="FXDeal",
            action="STATUS_CHANGE",
            created_by=user.email,
            old_value=json.dumps({"status": old_status}),
            new_value=json.dumps(
                {"status": DealState.REJECTED.value, "decision": decision.value, "comment": comment}
            ),
        )
        await self._repo.commit()
        return _to_response(updated)

    async def _save_solution(
        self,
        deal: FXDeal,
        user: UserClaims,
        decision: ApprovalDecision,
        comment: str | None,
    ) -> None:
        if deal.positioner_solution is not None:
            deal.positioner_solution.decision = decision.value
            deal.positioner_solution.comment = comment
            deal.positioner_solution.positioner_id = user.user_id
        else:
            self._session.add(
                PositionerSolution(
                    deal_id=deal.id,
                    decision=decision.value,
                    comment=comment,
                    positioner_id=user.user_id,
                )
            )

    async def _load_deal(self, deal_id: UUID) -> FXDeal:
        try:
            return await self._repo.get_by_id(deal_id)
        except DealNotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Deal not found") from exc

    @staticmethod
    def _require_trader(deal: FXDeal, user: UserClaims) -> None:
        if deal.trader_id != user.user_id and user.role != "ADMIN":
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only the deal creator can perform this action",
            )

    @staticmethod
    def _require_positioner(user: UserClaims) -> None:
        if user.role not in ("POSITIONER", "ADMIN"):
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Positioner role required",
            )
