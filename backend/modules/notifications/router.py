from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.core.config import settings
from backend.core.pagination import build_cursor_page, token_from_created_at_id
from backend.core.schemas import CursorPageResponse
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.notifications.repository import NotificationsRepository
from backend.modules.notifications.schemas import (
    NotificationListItem,
    NotificationPreferenceResponse,
    NotificationPreferenceUpdate,
)
from backend.modules.orchestration._helpers import resolve_query_limit
from backend.modules.orchestration.presenters import to_notification_list_item

router = APIRouter()


@router.get("", response_model=CursorPageResponse[NotificationListItem])
async def list_notifications(
    limit: int = Query(
        settings.NOTIFICATIONS_LIST_DEFAULT_LIMIT,
        ge=1,
        le=settings.NOTIFICATIONS_LIST_MAX_LIMIT,
    ),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    effective_limit = resolve_query_limit(
        limit,
        default=settings.NOTIFICATIONS_LIST_DEFAULT_LIMIT,
        maximum=settings.NOTIFICATIONS_LIST_MAX_LIMIT,
    )
    repo = NotificationsRepository(db)
    rows = await repo.list_for_user(
        current_user.id,
        limit=effective_limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    page, next_cursor = build_cursor_page(
        rows,
        effective_limit,
        token_from_row=token_from_created_at_id,
    )
    return CursorPageResponse(
        items=[to_notification_list_item(n) for n in page],
        next_cursor=next_cursor,
    )


@router.get("/unread-count")
async def unread_notifications_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    return {"count": await repo.count_unread_for_user(current_user.id)}


@router.patch("/{notification_id}/read", status_code=204)
async def mark_read(
    notification_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    n = await repo.get_by_id(notification_id)
    if not n or n.user_id != current_user.id:
        raise HTTPException(status_code=404, detail="Notification not found")
    await repo.mark_read(n)
    await db.commit()


@router.patch("/read-all", status_code=204)
async def mark_all_read(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    await repo.mark_all_read(current_user.id)
    await db.commit()


@router.get("/preferences", response_model=NotificationPreferenceResponse)
async def get_preferences(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    prefs = await repo.get_or_create_preferences(current_user.id)
    await db.commit()
    return NotificationPreferenceResponse(
        email_enabled=prefs.email_enabled,
        push_enabled=prefs.push_enabled,
        marketing_enabled=prefs.marketing_enabled,
    )


@router.put("/preferences", response_model=NotificationPreferenceResponse)
async def update_preferences(
    payload: NotificationPreferenceUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    repo = NotificationsRepository(db)
    prefs = await repo.get_or_create_preferences(current_user.id)
    if payload.email_enabled is not None:
        prefs.email_enabled = payload.email_enabled
    if payload.push_enabled is not None:
        prefs.push_enabled = payload.push_enabled
    if payload.marketing_enabled is not None:
        prefs.marketing_enabled = payload.marketing_enabled
    await db.commit()
    return NotificationPreferenceResponse(
        email_enabled=prefs.email_enabled,
        push_enabled=prefs.push_enabled,
        marketing_enabled=prefs.marketing_enabled,
    )
