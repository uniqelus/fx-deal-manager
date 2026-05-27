import json
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from fx_deal_manager.api.dependencies import require_role
from fx_deal_manager.core.database import get_db_session
from fx_deal_manager.domain.models import AuditLogEntry, UserNotificationState
from fx_deal_manager.domain.schemas import NotificationListResponse, NotificationResponse, UserClaims

router = APIRouter(prefix="/notifications", tags=["notifications"])


@router.get("", summary="In-app notifications from audit events")
async def list_notifications(
    user: Annotated[UserClaims, Depends(require_role("TRADER", "POSITIONER", "AUDITOR", "ADMIN"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
    page_size: int = 50,
) -> NotificationListResponse:
    state = await session.get(UserNotificationState, user.user_id)
    last_read_at = state.last_read_at if state else None
    page_size = min(max(page_size, 1), 100)

    total = await session.scalar(select(func.count()).select_from(AuditLogEntry))
    rows = (
        await session.execute(
            select(AuditLogEntry).order_by(AuditLogEntry.created_at.desc()).limit(page_size)
        )
    ).scalars().all()
    items = [_to_notification(row, last_read_at) for row in rows]
    unread_count = sum(1 for item in items if not item.read)
    return NotificationListResponse(items=items, unread_count=unread_count, total=total or 0)


@router.post("/read-all", summary="Mark current notifications as read")
async def read_all_notifications(
    user: Annotated[UserClaims, Depends(require_role("TRADER", "POSITIONER", "AUDITOR", "ADMIN"))],
    session: Annotated[AsyncSession, Depends(get_db_session)],
) -> dict[str, str]:
    state = await session.get(UserNotificationState, user.user_id)
    if state is None:
        state = UserNotificationState(user_id=user.user_id)
        session.add(state)
    state.last_read_at = datetime.now(timezone.utc)
    await session.commit()
    return {"status": "ok"}


def _to_notification(row: AuditLogEntry, last_read_at: datetime | None) -> NotificationResponse:
    payload = _json(row.new_value)
    title = _title(row.action, payload)
    description = _description(row, payload)
    kind = _kind(row.action, payload)
    return NotificationResponse(
        id=row.id,
        title=title,
        description=description,
        kind=kind,
        created_at=row.created_at,
        read=bool(last_read_at and row.created_at <= last_read_at),
        entity_id=row.entity_id,
        entity_type=row.entity_type,
        action=row.action,
        related_url=f"deal-detail.html?id={row.entity_id}" if row.entity_type == "FXDeal" else None,
    )


def _json(value: str | None) -> dict:
    if not value:
        return {}
    try:
        data = json.loads(value)
        return data if isinstance(data, dict) else {}
    except json.JSONDecodeError:
        return {}


def _title(action: str, payload: dict) -> str:
    status = payload.get("status")
    if action == "CREATE":
        return "Создана FX-сделка"
    if action == "VALIDATE":
        return "Сделка прошла контроль"
    if action == "VALIDATE_FAILED":
        return "Контроль сделки не пройден"
    if action == "POSITION_SEND":
        return "Платежи отправлены в ПОЗИЦИИ"
    if action == "STATUS_CHANGE" and status:
        return f"Статус сделки изменён: {status}"
    return action.replace("_", " ").title()


def _description(row: AuditLogEntry, payload: dict) -> str:
    if payload.get("error"):
        return str(payload["error"])
    if payload.get("correlation_id"):
        return f"correlation_id={payload['correlation_id']}"
    return f"{row.entity_type} {str(row.entity_id)[:8]} · {row.created_by}"


def _kind(action: str, payload: dict) -> str:
    if payload.get("error") or action == "VALIDATE_FAILED":
        return "danger"
    if action == "POSITION_SEND":
        return "info"
    if action in {"CREATE", "VALIDATE", "STATUS_CHANGE"}:
        return "success"
    return "info"
