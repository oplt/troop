"""Workflow list/create/publish + run endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.models import WorkflowDefinition, WorkflowVersion
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import WorkflowDefinitionResponse
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService

router = APIRouter(prefix="/workflows")


class WorkflowCreateRequest(RequestModel):
    slug: str
    name: str
    description: str = ""
    category: str = "general"
    company_id: str | None = None
    is_template: bool = False
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    entry_node_id: str | None = None


class WorkflowPublishRequest(RequestModel):
    nodes: list[dict] | None = None
    edges: list[dict] | None = None
    entry_node_id: str | None = None


class WorkflowStartRequest(RequestModel):
    project_id: str | None = None
    task_id: str | None = None
    input: dict = Field(default_factory=dict)


class WorkflowResumeRequest(RequestModel):
    approval_granted: bool = False


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_version_id: str
    status: str
    current_node_id: str | None = None
    context_json: dict = Field(default_factory=dict)
    result_json: dict = Field(default_factory=dict)


@router.get("", response_model=list[WorkflowDefinitionResponse])
async def list_workflows(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowDefinitionResponse]:
    repo = WorkforceRepository(db)
    workflows = await repo.list_workflows(user.id)
    return [WorkflowDefinitionResponse.model_validate(w) for w in workflows]


@router.post("", response_model=WorkflowDefinitionResponse, status_code=201)
async def create_workflow(
    payload: WorkflowCreateRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    runtime = WorkflowRuntimeService(db)
    errors = runtime.validate_graph(
        nodes=payload.nodes,
        edges=payload.edges,
        entry_node_id=payload.entry_node_id,
    )
    if payload.nodes and errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": errors})

    definition = WorkflowDefinition(
        id=str(uuid4()),
        owner_id=user.id,
        company_id=payload.company_id,
        slug=payload.slug,
        name=payload.name,
        description=payload.description,
        category=payload.category,
        status="draft",
        is_template=payload.is_template,
    )
    db.add(definition)
    await db.flush()

    if payload.nodes:
        version = WorkflowVersion(
            id=str(uuid4()),
            workflow_id=definition.id,
            version_number=1,
            nodes_json=payload.nodes,
            edges_json=payload.edges,
            entry_node_id=payload.entry_node_id,
            is_published=False,
            created_by=user.id,
        )
        db.add(version)
        await db.flush()
        definition.current_version_id = version.id

    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionResponse.model_validate(definition)


@router.post("/{workflow_id}/publish", response_model=WorkflowDefinitionResponse)
async def publish_workflow(
    workflow_id: str,
    payload: WorkflowPublishRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.owner_id == user.id,
        )
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workflow not found")

    version = None
    if definition.current_version_id:
        version = await db.get(WorkflowVersion, definition.current_version_id)

    nodes = payload.nodes if payload.nodes is not None else list((version.nodes_json if version else []) or [])
    edges = payload.edges if payload.edges is not None else list((version.edges_json if version else []) or [])
    entry = (
        payload.entry_node_id
        if payload.entry_node_id is not None
        else (version.entry_node_id if version else None)
    )
    runtime = WorkflowRuntimeService(db)
    errors = runtime.validate_graph(nodes=nodes, edges=edges, entry_node_id=entry)
    if errors:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"errors": errors})

    next_number = (version.version_number + 1) if version and version.is_published else (
        version.version_number if version else 1
    )
    if version and not version.is_published:
        version.nodes_json = nodes
        version.edges_json = edges
        version.entry_node_id = entry
        version.is_published = True
        published = version
    else:
        published = WorkflowVersion(
            id=str(uuid4()),
            workflow_id=definition.id,
            version_number=next_number,
            nodes_json=nodes,
            edges_json=edges,
            entry_node_id=entry,
            is_published=True,
            created_by=user.id,
        )
        db.add(published)
        await db.flush()
        definition.current_version_id = published.id

    definition.status = "active"
    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionResponse.model_validate(definition)


@router.post("/{workflow_id}/runs", response_model=WorkflowRunResponse)
async def start_workflow_run(
    workflow_id: str,
    payload: WorkflowStartRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunResponse:
    from backend.modules.workforce.authz import assert_project_owned, assert_task_owned

    await assert_project_owned(db, user.id, payload.project_id)
    await assert_task_owned(db, user.id, payload.task_id)
    runtime = WorkflowRuntimeService(db)
    try:
        run = await runtime.start_run(
            user.id,
            workflow_id,
            project_id=payload.project_id,
            task_id=payload.task_id,
            input_json=payload.input,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        status=run.status,
        current_node_id=run.current_node_id,
        context_json=run.context_json or {},
        result_json=run.result_json or {},
    )


@router.post("/runs/{run_id}/resume", response_model=WorkflowRunResponse)
async def resume_workflow_run(
    run_id: str,
    payload: WorkflowResumeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunResponse:
    runtime = WorkflowRuntimeService(db)
    try:
        run = await runtime.resume_run(
            user.id, run_id, approval_granted=payload.approval_granted
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WorkflowRunResponse(
        id=run.id,
        workflow_id=run.workflow_id,
        workflow_version_id=run.workflow_version_id,
        status=run.status,
        current_node_id=run.current_node_id,
        context_json=run.context_json or {},
        result_json=run.result_json or {},
    )
