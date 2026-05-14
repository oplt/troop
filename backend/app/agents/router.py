from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Body, Depends, HTTPException, Query
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.app.agents.logging import log_agent_event
from backend.app.agents.memory.base import SqlMemoryStore
from backend.app.agents.tools.registry import ToolSpec, get_tool, list_tools
from backend.app.agents.workspace import list_run_workspace_files, write_artifact
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.memory.models import SemanticMemoryEntry
from backend.modules.orchestration.execution.execution_workflow import (
    ensure_workflow_state,
    mark_step,
)
from backend.modules.orchestration.models import RunEvent, TaskArtifact
from backend.modules.orchestration.router import _agent, _event, _run, _task
from backend.modules.orchestration.schemas import (
    AgentCreate,
    AgentResponse,
    AgentUpdate,
    RunEventResponse,
    TaskCreate,
    TaskResponse,
    TaskRunResponse,
)
from backend.modules.orchestration.services.service import OrchestrationService
from backend.modules.projects.orchestration_models import OrchestratorTask

agents_router = APIRouter()
tools_router = APIRouter()
tasks_router = APIRouter()
runs_router = APIRouter()
memory_router = APIRouter()


class MarkdownImportPayload(BaseModel):
    content: str
    project_id: str | None = None
    existing_agent_id: str | None = None


class ToolListResponse(BaseModel):
    tools: list[ToolSpec]


class MemoryCreate(BaseModel):
    scope: Literal["company", "project", "agent", "task"]
    scope_id: str
    content: str = Field(min_length=1)
    metadata: dict[str, Any] = Field(default_factory=dict)


class MemorySearch(BaseModel):
    scope: Literal["company", "project", "agent", "task"]
    scope_id: str
    query: str = Field(min_length=1)
    limit: int = Field(default=20, ge=1, le=100)


class MemoryResponse(BaseModel):
    id: str
    scope: str
    scope_id: str
    title: str
    body: str
    metadata: dict[str, Any]
    created_at: datetime


class RunArtifactResponse(BaseModel):
    id: str
    run_id: str | None
    task_id: str
    type: str
    name: str
    path_or_url: str | None
    metadata: dict[str, Any]
    created_at: datetime


def _memory(item: SemanticMemoryEntry) -> MemoryResponse:
    scope_id = (
        item.company_id
        or item.project_id
        or item.agent_id
        or item.source_task_id
        or (item.namespace.split(":", 1)[1] if ":" in item.namespace else "")
    )
    return MemoryResponse(
        id=item.id,
        scope=item.scope,
        scope_id=scope_id,
        title=item.title,
        body=item.body,
        metadata=item.metadata_json or {},
        created_at=item.created_at,
    )


def _artifact(item: TaskArtifact) -> RunArtifactResponse:
    return RunArtifactResponse(
        id=item.id,
        run_id=item.run_id,
        task_id=item.task_id,
        type=item.kind,
        name=item.title,
        path_or_url=(item.metadata_json or {}).get("path_or_url"),
        metadata=item.metadata_json or {},
        created_at=item.created_at,
    )


def _plan_for_task(task: OrchestratorTask, agent_ids: list[str]) -> list[dict[str, Any]]:
    actors = agent_ids or ([task.assigned_agent_id] if task.assigned_agent_id else [])
    if not actors:
        actors = ["unassigned"]
    return [
        {
            "id": "understand_task",
            "title": f"Review task: {task.title}",
            "actor": actors[0],
            "status": "pending",
            "metadata": {"source": "deterministic_placeholder_planner"},
        },
        {
            "id": "gather_context",
            "title": "Gather project, task, and memory context",
            "actor": actors[0],
            "status": "pending",
            "metadata": {"tools": ["file_read_stub", "web_search_stub"]},
        },
        {
            "id": "draft_output",
            "title": "Draft final task output and artifacts",
            "actor": actors[-1],
            "status": "pending",
            "metadata": {"requires_human_review": False},
        },
    ]


@agents_router.get("", response_model=list[AgentResponse])
async def list_agent_profiles(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_agent(item) for item in await OrchestrationService(db).list_agents(current_user, project_id)]


@agents_router.post("", response_model=AgentResponse, status_code=201)
async def create_agent_profile(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).create_agent(current_user, payload.model_dump())
    log_agent_event("agent_created", user_id=current_user.id, agent_id=item.id, project_id=item.project_id)
    return _agent(item)


@agents_router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _agent(await OrchestrationService(db).get_agent(current_user, agent_id))


@agents_router.put("/{agent_id}", response_model=AgentResponse)
async def put_agent_profile(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).update_agent(
        current_user,
        agent_id,
        payload.model_dump(exclude_unset=True),
    )
    return _agent(item)


@agents_router.delete("/{agent_id}", status_code=204)
async def delete_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_agent(current_user, agent_id)


@agents_router.post("/import-markdown", response_model=AgentResponse, status_code=201)
async def import_agent_profile_markdown(
    payload: MarkdownImportPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).import_agent_markdown(
        current_user,
        content=payload.content,
        project_id=payload.project_id,
        existing_agent_id=payload.existing_agent_id,
    )
    log_agent_event("agent_imported_markdown", user_id=current_user.id, agent_id=item.id, project_id=item.project_id)
    return _agent(item)


@tools_router.get("", response_model=ToolListResponse)
async def get_tools(enabled_only: bool = False):
    return ToolListResponse(tools=list_tools(enabled_only=enabled_only))


@tools_router.get("/{name}", response_model=ToolSpec)
async def get_tool_spec(name: str):
    tool = get_tool(name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


@tasks_router.post("", response_model=TaskResponse, status_code=201)
async def create_agent_task(
    payload: dict[str, Any] = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project_id = str(payload.pop("project_id", "")).strip()
    if not project_id:
        raise HTTPException(status_code=422, detail="project_id is required.")
    task_payload = TaskCreate.model_validate(payload)
    service = OrchestrationService(db)
    item = await service.create_task(current_user, project_id, task_payload.model_dump())
    log_agent_event("task_created", user_id=current_user.id, task_id=item.id, project_id=project_id)
    return _task(item, task_payload.dependency_ids, None)


@tasks_router.get("", response_model=list[TaskResponse])
async def list_agent_tasks(
    project_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_task(item, [], None) for item in await service.list_tasks(current_user, project_id)]


@tasks_router.get("/{task_id}", response_model=TaskResponse)
async def get_agent_task(
    task_id: str,
    project_id: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).get_task(current_user, project_id, task_id)
    return _task(item, [], None)


@tasks_router.post("/{task_id}/runs", response_model=TaskRunResponse, status_code=201)
async def create_agent_task_run(
    task_id: str,
    payload: dict[str, Any] | None = Body(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    task = await db.get(OrchestratorTask, task_id)
    if task is None:
        raise HTTPException(status_code=404, detail="Task not found")
    await service.get_project(current_user, task.project_id)
    payload = dict(payload or {})
    assigned_ids = [str(item) for item in payload.get("assigned_agent_ids", []) if str(item).strip()]
    if not assigned_ids and task.assigned_agent_id:
        assigned_ids = [task.assigned_agent_id]
    plan_steps = _plan_for_task(task, assigned_ids)
    run = await service.repo.create_run(
        project_id=task.project_id,
        task_id=task.id,
        triggered_by_user_id=current_user.id,
        worker_agent_id=assigned_ids[0] if assigned_ids and assigned_ids[0] != "unassigned" else None,
        run_mode=str(payload.get("run_mode") or "planned_placeholder"),
        status="awaiting_approval",
        input_payload_json={"requested_by": "agent_task_run_api", **payload},
        output_payload_json={},
    )
    run.checkpoint_json = ensure_workflow_state(
        run.checkpoint_json,
        run_mode=run.run_mode,
        steps=plan_steps,
        run_id=run.id,
    )
    run.output_payload_json = {"plan": plan_steps}
    await service.repo.create_run_event(
        run_id=run.id,
        task_id=task.id,
        event_type="plan_generated",
        message="Deterministic placeholder plan generated; awaiting approval.",
        payload_json={"plan": plan_steps},
    )
    await db.commit()
    await db.refresh(run)
    log_agent_event("run_created", user_id=current_user.id, task_id=task.id, run_id=run.id, project_id=task.project_id)
    log_agent_event("plan_generated", user_id=current_user.id, task_id=task.id, run_id=run.id, project_id=task.project_id)
    return _run(run)


@runs_router.get("/{run_id}", response_model=TaskRunResponse)
async def get_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).get_run(current_user, run_id))


@runs_router.get("/{run_id}/steps", response_model=list[RunEventResponse])
async def get_agent_run_steps(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).get_run(current_user, run_id)
    result = await db.execute(
        select(RunEvent)
        .where(RunEvent.run_id == run_id)
        .order_by(RunEvent.created_at.asc())
    )
    return [_event(item) for item in result.scalars().all()]


@runs_router.post("/{run_id}/approve-plan", response_model=TaskRunResponse)
async def approve_agent_run_plan(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    run = await service.get_run(current_user, run_id)
    if run.status != "awaiting_approval":
        raise HTTPException(status_code=409, detail="Run is not awaiting plan approval.")
    run.status = "running"
    run.started_at = datetime.now(UTC)
    steps = list((run.output_payload_json or {}).get("plan") or [])
    await service.repo.create_run_event(
        run_id=run.id,
        task_id=run.task_id,
        event_type="plan_approved",
        message="Plan approved; placeholder execution started.",
        payload_json={"approved_by_user_id": current_user.id},
    )
    log_agent_event("plan_approved", user_id=current_user.id, run_id=run.id, task_id=run.task_id, project_id=run.project_id)
    for index, step in enumerate(steps):
        step_id = str(step.get("id") or f"step_{index}")
        run.checkpoint_json = mark_step(run.checkpoint_json, step_id=step_id, status="in_progress")
        await service.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type="run_step_started",
            message=str(step.get("title") or step_id),
            payload_json={"step_index": index, "step": step},
        )
        run.checkpoint_json = mark_step(run.checkpoint_json, step_id=step_id, status="completed")
        await service.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type="run_step_completed",
            message=str(step.get("title") or step_id),
            payload_json={"step_index": index, "step": step, "output": "placeholder_completed"},
        )
        log_agent_event("run_step_completed", user_id=current_user.id, run_id=run.id, task_id=run.task_id, project_id=run.project_id, step_id=step_id)
    final_output = "Placeholder run completed after human plan approval. Real LLM/tool execution is still disabled."
    path = await write_artifact(db, run.id, "final-output.md", final_output)
    artifact = TaskArtifact(
        task_id=run.task_id,
        run_id=run.id,
        kind="final_output",
        title="final-output.md",
        content=final_output,
        metadata_json={"path_or_url": str(path), "workspace_file": "final-output.md"},
    )
    db.add(artifact)
    run.status = "completed"
    run.completed_at = datetime.now(UTC)
    run.output_payload_json = {**(run.output_payload_json or {}), "final_output": final_output}
    await service.repo.create_run_event(
        run_id=run.id,
        task_id=run.task_id,
        event_type="artifact_created",
        message="Final output artifact created.",
        payload_json={"artifact_name": "final-output.md", "path_or_url": str(path)},
    )
    await db.commit()
    await db.refresh(run)
    log_agent_event("artifact_created", user_id=current_user.id, run_id=run.id, task_id=run.task_id, project_id=run.project_id, path_or_url=str(path))
    return _run(run)


@runs_router.post("/{run_id}/cancel", response_model=TaskRunResponse)
async def cancel_agent_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await OrchestrationService(db).cancel_run(current_user, run_id)
    log_agent_event("run_cancelled", user_id=current_user.id, run_id=run.id, task_id=run.task_id, project_id=run.project_id)
    return _run(run)


@runs_router.get("/{run_id}/artifacts", response_model=list[RunArtifactResponse])
async def list_agent_run_artifacts(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await OrchestrationService(db).get_run(current_user, run_id)
    result = await db.execute(
        select(TaskArtifact)
        .where(TaskArtifact.run_id == run.id)
        .order_by(TaskArtifact.created_at.desc())
    )
    return [_artifact(item) for item in result.scalars().all()]


@runs_router.get("/{run_id}/workspace-files")
async def list_agent_run_workspace_files(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).get_run(current_user, run_id)
    return {"files": await list_run_workspace_files(db, run_id)}


@memory_router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    payload: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await SqlMemoryStore(db, current_user).add_memory(
        payload.scope,
        payload.scope_id,
        payload.content,
        payload.metadata,
    )
    return _memory(item)


@memory_router.get("", response_model=list[MemoryResponse])
async def list_memory(
    scope: Literal["company", "project", "agent", "task"],
    scope_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_memory(item) for item in await SqlMemoryStore(db, current_user).list_memory(scope, scope_id, limit)]


@memory_router.post("/search", response_model=list[MemoryResponse])
async def search_memory(
    payload: MemorySearch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        _memory(item)
        for item in await SqlMemoryStore(db, current_user).search_memory(
            payload.scope,
            payload.scope_id,
            payload.query,
            payload.limit,
        )
    ]
