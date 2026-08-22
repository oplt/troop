from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.compat.schemas import RunArtifactResponse, artifact_response
from backend.api.deps.auth import get_current_user
from backend.core.logging import get_logger
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.observability.logging import log_event
from backend.modules.orchestration.presenters import to_event_response, to_run_response
from backend.modules.orchestration.schemas import RunEventResponse, TaskRunResponse
from backend.modules.orchestration.services.execution_domain import ExecutionService
from backend.modules.orchestration.services.planned_runs import (
    PlanApprovalConflictError,
    PlannedRunNotFoundError,
    PlannedRunService,
    PlannedRunTaskNotFoundError,
)
from backend.modules.orchestration.workspace import WorkspacePathError, WorkspaceSizeError
from backend.modules.orchestration.workspace.service import RunWorkspaceError

router = APIRouter()
logger = get_logger(__name__)


def _planned_run_http_error(exc: Exception) -> HTTPException:
    if isinstance(exc, (PlannedRunTaskNotFoundError, PlannedRunNotFoundError)):
        return HTTPException(status_code=404, detail=str(exc))
    if isinstance(exc, PlanApprovalConflictError):
        return HTTPException(status_code=409, detail=str(exc))
    if isinstance(exc, (WorkspacePathError, WorkspaceSizeError, RunWorkspaceError)):
        return HTTPException(status_code=400, detail=str(exc))
    return HTTPException(status_code=500, detail="Planned run operation failed")


@router.post("/tasks/{task_id}/runs", response_model=TaskRunResponse, status_code=201)
async def create_agent_task_run(
    task_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        run = await PlannedRunService(db).create_planned_run(current_user, task_id, payload)
    except (PlannedRunTaskNotFoundError, PlannedRunNotFoundError) as exc:
        raise _planned_run_http_error(exc) from exc
    return to_run_response(run)


@router.get("/runs/{run_id}", response_model=TaskRunResponse)
async def get_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        run = await PlannedRunService(db).get_run(current_user, run_id)
    except PlannedRunNotFoundError as exc:
        raise _planned_run_http_error(exc) from exc
    return to_run_response(run)


@router.get("/runs/{run_id}/steps", response_model=list[RunEventResponse])
async def get_agent_run_steps(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        events = await PlannedRunService(db).list_run_events(current_user, run_id)
    except PlannedRunNotFoundError as exc:
        raise _planned_run_http_error(exc) from exc
    return [to_event_response(item) for item in events]


@router.post("/runs/{run_id}/approve-plan", response_model=TaskRunResponse)
async def approve_agent_run_plan(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        run = await PlannedRunService(db).approve_plan(current_user, run_id)
    except (
        PlannedRunNotFoundError,
        PlanApprovalConflictError,
        WorkspacePathError,
        WorkspaceSizeError,
        RunWorkspaceError,
    ) as exc:
        raise _planned_run_http_error(exc) from exc
    return to_run_response(run)


@router.post("/runs/{run_id}/cancel", response_model=TaskRunResponse)
async def cancel_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await ExecutionService(db).cancel_run(current_user, run_id)
    log_event(
        logger,
        "run_cancelled",
        user_id=current_user.id,
        run_id=run.id,
        task_id=run.task_id,
        project_id=run.project_id,
        status=run.status,
    )
    return to_run_response(run)


@router.get("/runs/{run_id}/artifacts", response_model=list[RunArtifactResponse])
async def list_agent_run_artifacts(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        artifacts = await PlannedRunService(db).list_run_artifacts(current_user, run_id)
    except PlannedRunNotFoundError as exc:
        raise _planned_run_http_error(exc) from exc
    return [artifact_response(item) for item in artifacts]


@router.get("/runs/{run_id}/workspace-files")
async def list_agent_run_workspace_files(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    try:
        files = await PlannedRunService(db).list_workspace_files(current_user, run_id)
    except (PlannedRunNotFoundError, RunWorkspaceError, WorkspacePathError) as exc:
        raise _planned_run_http_error(exc) from exc
    return {
        "files": [
            {"name": item.name, "path": item.path, "size_bytes": item.size_bytes} for item in files
        ]
    }
