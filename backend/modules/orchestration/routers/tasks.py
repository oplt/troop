from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.core.config import settings
from backend.core.pagination import build_cursor_page, token_from_created_at_id
from backend.core.schemas import CursorPageResponse
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import resolve_query_limit
from backend.modules.orchestration.presenters import to_task_list_item
from backend.modules.orchestration.schemas import MyTaskListItem
from backend.modules.orchestration.services.service import OrchestrationService

router = APIRouter(prefix="/tasks", tags=["orchestration-tasks"])


@router.get("/my", response_model=CursorPageResponse[MyTaskListItem])
async def list_my_tasks(
    limit: int = Query(
        settings.ORCHESTRATION_LIST_TASKS_DEFAULT_LIMIT,
        ge=1,
        le=settings.CURSOR_PAGE_MAX_LIMIT,
    ),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    effective_limit = resolve_query_limit(
        limit,
        default=settings.ORCHESTRATION_LIST_TASKS_DEFAULT_LIMIT,
        maximum=settings.CURSOR_PAGE_MAX_LIMIT,
    )
    rows, dependencies = await OrchestrationService(db).repo.list_my_tasks_with_dependencies(
        current_user.id,
        current_user.id,
        limit=effective_limit,
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
    )
    page, next_cursor = build_cursor_page(
        rows,
        effective_limit,
        token_from_row=lambda row: token_from_created_at_id(row[0]),
    )
    return CursorPageResponse(
        items=[
            MyTaskListItem(
                **to_task_list_item(task, dependencies.get(task.id, [])).model_dump(),
                project_name=project_name,
            )
            for task, project_name in page
        ],
        next_cursor=next_cursor,
    )
