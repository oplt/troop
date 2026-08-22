from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.core.logging import get_logger
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.observability.logging import log_event
from backend.modules.orchestration.presenters import to_task_response
from backend.modules.orchestration.schemas import TaskCreate, TaskResponse
from backend.modules.orchestration.services.service import OrchestrationService

router = APIRouter()
logger = get_logger(__name__)


@router.post("", response_model=TaskResponse, status_code=201)
async def create_agent_task(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    request = dict(payload)
    project_id = str(request.pop("project_id", "")).strip()
    if not project_id:
        raise HTTPException(status_code=422, detail="project_id is required.")
    task_payload = TaskCreate.model_validate(request)
    item = await OrchestrationService(db).create_task(
        current_user,
        project_id,
        task_payload.model_dump(),
    )
    log_event(
        logger,
        "task_created",
        user_id=current_user.id,
        task_id=item.id,
        project_id=project_id,
    )
    return to_task_response(item, task_payload.dependency_ids, None)


@router.get("", response_model=list[TaskResponse])
async def list_agent_tasks(
    project_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        to_task_response(item, [], None)
        for item in await OrchestrationService(db).list_tasks(current_user, project_id)
    ]


@router.get("/{task_id}", response_model=TaskResponse)
async def get_agent_task(
    task_id: str,
    project_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).get_task(current_user, project_id, task_id)
    return to_task_response(item, [], None)
