"""Workflow list/create/publish + run endpoints."""

from __future__ import annotations

from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.core.schemas import RequestModel
from backend.core.sse_streams import live_snapshot_stream
from backend.db.session import SessionLocal, get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.models import (
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
)
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import (
    WorkflowDefinitionResponse,
    WorkflowGenerateRequest,
    WorkflowGenerateResponse,
)
from backend.modules.workforce.services.workflow_environment_service import (
    WorkflowEnvironmentService,
    normalize_environment,
)
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService
from backend.modules.workforce.services.workflow_scaffold_service import WorkflowScaffoldService
from backend.modules.workforce.services.workflow_version_service import WorkflowVersionService

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


class WorkflowDraftUpdateRequest(RequestModel):
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
    environment: str = "prod"


class WorkflowEnvironmentPromoteRequest(RequestModel):
    version_id: str
    connection_bindings: dict[str, dict[str, str]] | None = None


class WorkflowEnvironmentDiffRequest(RequestModel):
    version_id: str
    connection_bindings: dict[str, dict[str, str]] | None = None


class WorkflowTestRunRequest(RequestModel):
    project_id: str | None = None
    task_id: str | None = None
    input: dict = Field(default_factory=dict)
    version_id: str | None = None


class WorkflowRollbackRequest(RequestModel):
    version_id: str


class WorkflowValidationResponse(BaseModel):
    valid: bool
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    infos: list[str] = Field(default_factory=list)
    external_write_nodes: list[dict] = Field(default_factory=list)


class WorkflowDiffResponse(BaseModel):
    nodes_added: list[str] = Field(default_factory=list)
    nodes_removed: list[str] = Field(default_factory=list)
    nodes_changed: list[dict] = Field(default_factory=list)
    edges_added: list[dict] = Field(default_factory=list)
    edges_removed: list[dict] = Field(default_factory=list)
    entry_node_changed: bool = False
    entry_node_before: str | None = None
    entry_node_after: str | None = None
    graph_hash_before: str | None = None
    graph_hash_after: str | None = None
    graph_changed: bool = False
    summary: dict = Field(default_factory=dict)


class WorkflowVersionSummary(BaseModel):
    id: str
    version_number: int
    graph_hash: str | None = None
    entry_node_id: str | None = None
    created_at: object | None = None


class WorkflowDraftGraphResponse(BaseModel):
    nodes: list[dict] = Field(default_factory=list)
    edges: list[dict] = Field(default_factory=list)
    entry_node_id: str | None = None


class WorkflowDetailResponse(WorkflowDefinitionResponse):
    draft: WorkflowDraftGraphResponse | None = None


class WorkflowResumeRequest(RequestModel):
    approval_request_id: str | None = None
    human_input: dict = Field(default_factory=dict)
    # Deprecated: client-asserted approval is ignored; keep for compat parsing only.
    approval_granted: bool | None = None


class WorkflowRunResponse(BaseModel):
    id: str
    workflow_id: str
    workflow_version_id: str
    status: str
    current_node_id: str | None = None
    context_json: dict = Field(default_factory=dict)
    result_json: dict = Field(default_factory=dict)


async def _owned_workflow_run(
    db: AsyncSession,
    *,
    owner_id: str,
    run_id: str,
) -> WorkflowRun:
    result = await db.execute(
        select(WorkflowRun)
        .join(WorkflowDefinition, WorkflowDefinition.id == WorkflowRun.workflow_id)
        .where(
            WorkflowRun.id == run_id,
            WorkflowDefinition.owner_id == owner_id,
        )
    )
    run = result.scalar_one_or_none()
    if run is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workflow run not found")
    return run


async def _workflow_run_steps_snapshot(
    db: AsyncSession,
    *,
    owner_id: str,
    run_id: str,
) -> dict:
    run = await _owned_workflow_run(db, owner_id=owner_id, run_id=run_id)
    result = await db.execute(
        select(WorkflowStepRun)
        .where(WorkflowStepRun.workflow_run_id == run_id)
        .order_by(WorkflowStepRun.created_at.asc())
    )
    steps = result.scalars().all()
    return {
        "run_id": run_id,
        "run_status": run.status,
        "current_node_id": run.current_node_id,
        "steps": [
            {
                "id": step.id,
                "node_id": step.node_id,
                "node_type": step.node_type,
                "status": step.status,
                "retry_count": 0,
                "started_at": step.started_at,
                "finished_at": step.finished_at,
                "error": step.error,
            }
            for step in steps
        ],
    }


async def _with_fresh_workforce_session(callback):
    session = SessionLocal()
    try:
        return await callback(session)
    finally:
        await session.close()


@router.post("/generate", response_model=WorkflowGenerateResponse, status_code=201)
async def generate_workflow_draft(
    payload: WorkflowGenerateRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowGenerateResponse:
    """Generate a typed workflow draft from natural language (never auto-publishes)."""
    from backend.modules.workforce.authz import assert_company_owned
    from backend.modules.workforce.services.provider_resolution import resolve_owner_provider

    await assert_company_owned(db, user.id, payload.company_id)

    provider = None
    if not payload.deterministic:
        provider = await resolve_owner_provider(
            db,
            user.id,
            purpose="workflow_generation",
        )
    effective_use_llm = (
        payload.use_llm if payload.use_llm is not None else provider is not None
    ) and not payload.deterministic

    service = WorkflowScaffoldService(db)
    try:
        result = await service.generate(
            owner_id=user.id,
            prompt=payload.prompt.strip(),
            workflow_id=payload.workflow_id,
            name=payload.name,
            slug=payload.slug,
            company_id=payload.company_id,
            use_llm=effective_use_llm,
            provider=provider,
            model_name=(provider.default_model if provider else None),
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await db.commit()
    return WorkflowGenerateResponse.model_validate(result)


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
    version_service = WorkflowVersionService(db)
    runtime = WorkflowRuntimeService(db)
    if payload.nodes:
        errors = runtime.validate_graph(
            nodes=payload.nodes,
            edges=payload.edges,
            entry_node_id=payload.entry_node_id,
        )
        if errors:
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
        await version_service.ensure_draft(
            definition,
            created_by=user.id,
            nodes=payload.nodes,
            edges=payload.edges,
            entry_node_id=payload.entry_node_id,
        )

    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionResponse.model_validate(definition)


@router.get("/{workflow_id}", response_model=WorkflowDetailResponse)
async def get_workflow(
    workflow_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDetailResponse:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    version_service = WorkflowVersionService(db)
    draft = await version_service.get_draft(definition)
    draft_payload = None
    if draft is not None:
        draft_payload = WorkflowDraftGraphResponse(
            nodes=list(draft.nodes_json or []),
            edges=list(draft.edges_json or []),
            entry_node_id=draft.entry_node_id,
        )
    return WorkflowDetailResponse.model_validate(
        {
            **WorkflowDefinitionResponse.model_validate(definition).model_dump(),
            "draft": draft_payload,
        }
    )


@router.patch("/{workflow_id}/draft", response_model=WorkflowDefinitionResponse)
async def update_workflow_draft(
    workflow_id: str,
    payload: WorkflowDraftUpdateRequest,
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

    version_service = WorkflowVersionService(db)
    try:
        await version_service.update_draft(
            definition,
            nodes=payload.nodes,
            edges=payload.edges,
            entry_node_id=payload.entry_node_id,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

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

    version_service = WorkflowVersionService(db)
    draft = await version_service.get_draft(definition)
    nodes = (
        payload.nodes
        if payload.nodes is not None
        else list((draft.nodes_json if draft else []) or [])
    )
    edges = (
        payload.edges
        if payload.edges is not None
        else list((draft.edges_json if draft else []) or [])
    )
    entry = (
        payload.entry_node_id
        if payload.entry_node_id is not None
        else (draft.entry_node_id if draft else None)
    )
    try:
        published = await version_service.publish_draft(
            definition,
            actor_user_id=user.id,
            nodes=nodes,
            edges=edges,
            entry_node_id=entry,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    try:
        from backend.modules.workforce.integrations.events import TriggerSubscriptionService

        await TriggerSubscriptionService(db).register_published_gmail_triggers(
            owner_id=user.id,
            definition=definition,
            version=published,
        )
        await TriggerSubscriptionService(db).register_published_outlook_triggers(
            owner_id=user.id,
            definition=definition,
            version=published,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionResponse.model_validate(definition)


async def _owned_workflow_definition(
    db: AsyncSession,
    *,
    owner_id: str,
    workflow_id: str,
) -> WorkflowDefinition:
    result = await db.execute(
        select(WorkflowDefinition).where(
            WorkflowDefinition.id == workflow_id,
            WorkflowDefinition.owner_id == owner_id,
        )
    )
    definition = result.scalar_one_or_none()
    if definition is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workflow not found")
    return definition


@router.get("/{workflow_id}/environments")
async def list_workflow_environments(
    workflow_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    return await WorkflowEnvironmentService(db).list_environment_summaries(definition)


@router.get("/{workflow_id}/environments/{environment}")
async def get_workflow_environment_deployment(
    workflow_id: str,
    environment: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    env = normalize_environment(environment)
    service = WorkflowEnvironmentService(db)
    deployment = await service.get_deployment(definition, env)
    if deployment is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="environment deployment not found")
    version = await WorkflowVersionService(db).get_version(deployment.workflow_version_id)
    return {
        "environment": env,
        "deployment_id": deployment.id,
        "workflow_version_id": deployment.workflow_version_id,
        "version_number": version.version_number if version else None,
        "graph_hash": version.graph_hash if version else None,
        "connection_bindings": dict(deployment.connection_bindings_json or {}),
        "deployed_at": deployment.deployed_at,
        "deployed_by": deployment.deployed_by,
    }


@router.post("/{workflow_id}/environments/{environment}/promote")
async def promote_workflow_environment(
    workflow_id: str,
    environment: str,
    payload: WorkflowEnvironmentPromoteRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    service = WorkflowEnvironmentService(db)
    try:
        deployment = await service.promote(
            definition,
            environment=environment,
            version_id=payload.version_id,
            connection_bindings=payload.connection_bindings,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    return {
        "environment": normalize_environment(environment),
        "deployment_id": deployment.id,
        "workflow_version_id": deployment.workflow_version_id,
        "connection_bindings": dict(deployment.connection_bindings_json or {}),
        "deployed_at": deployment.deployed_at,
    }


@router.post("/{workflow_id}/environments/{environment}/rollback")
async def rollback_workflow_environment(
    workflow_id: str,
    environment: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    service = WorkflowEnvironmentService(db)
    try:
        deployment = await service.rollback(
            definition,
            environment=environment,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    await db.commit()
    return {
        "environment": normalize_environment(environment),
        "deployment_id": deployment.id,
        "workflow_version_id": deployment.workflow_version_id,
        "connection_bindings": dict(deployment.connection_bindings_json or {}),
        "deployed_at": deployment.deployed_at,
    }


@router.post("/{workflow_id}/environments/{environment}/diff")
async def diff_workflow_environment_promotion(
    workflow_id: str,
    environment: str,
    payload: WorkflowEnvironmentDiffRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    service = WorkflowEnvironmentService(db)
    try:
        return await service.diff_promotion(
            definition,
            environment=environment,
            candidate_version_id=payload.version_id,
            candidate_bindings=payload.connection_bindings,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc


@router.get("/{workflow_id}/environments/{environment}/history")
async def list_workflow_environment_history(
    workflow_id: str,
    environment: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    return await WorkflowEnvironmentService(db).list_history(definition, environment)


@router.get("/{workflow_id}/validate", response_model=WorkflowValidationResponse)
async def validate_workflow_draft(
    workflow_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowValidationResponse:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    report = await WorkflowVersionService(db).validate_draft(definition)
    return WorkflowValidationResponse.model_validate(report)


@router.get("/{workflow_id}/diff", response_model=WorkflowDiffResponse)
async def diff_workflow_draft(
    workflow_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDiffResponse:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    version_service = WorkflowVersionService(db)
    try:
        diff = await version_service.diff_draft_vs_published(definition)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc
    return WorkflowDiffResponse.model_validate(diff)


@router.get("/{workflow_id}/versions", response_model=list[WorkflowVersionSummary])
async def list_workflow_published_versions(
    workflow_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowVersionSummary]:
    await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    versions = await WorkflowVersionService(db).list_published_versions(workflow_id)
    return [
        WorkflowVersionSummary(
            id=version.id,
            version_number=version.version_number,
            graph_hash=version.graph_hash,
            entry_node_id=version.entry_node_id,
            created_at=version.created_at,
        )
        for version in versions
    ]


@router.post("/{workflow_id}/rollback", response_model=WorkflowDefinitionResponse)
async def rollback_workflow(
    workflow_id: str,
    payload: WorkflowRollbackRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowDefinitionResponse:
    definition = await _owned_workflow_definition(db, owner_id=user.id, workflow_id=workflow_id)
    version_service = WorkflowVersionService(db)
    try:
        rolled_back = await version_service.rollback_to_version(
            definition,
            target_version_id=payload.version_id,
            actor_user_id=user.id,
        )
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    try:
        from backend.modules.workforce.integrations.events import TriggerSubscriptionService

        await TriggerSubscriptionService(db).register_published_gmail_triggers(
            owner_id=user.id,
            definition=definition,
            version=rolled_back,
        )
        await TriggerSubscriptionService(db).register_published_outlook_triggers(
            owner_id=user.id,
            definition=definition,
            version=rolled_back,
        )
    except ValueError as exc:
        await db.rollback()
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

    await db.commit()
    await db.refresh(definition)
    return WorkflowDefinitionResponse.model_validate(definition)


@router.post("/{workflow_id}/test-runs", response_model=WorkflowRunResponse)
async def start_workflow_test_run(
    workflow_id: str,
    payload: WorkflowTestRunRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> WorkflowRunResponse:
    from backend.modules.workforce.authz import assert_project_owned, assert_task_owned

    await assert_project_owned(db, user.id, payload.project_id)
    await assert_task_owned(db, user.id, payload.task_id)
    runtime = WorkflowRuntimeService(db)
    try:
        run = await runtime.start_test_run(
            user.id,
            workflow_id,
            project_id=payload.project_id,
            task_id=payload.task_id,
            input_json=payload.input,
            version_id=payload.version_id,
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
            environment=payload.environment,
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
            user.id,
            run_id,
            approval_request_id=payload.approval_request_id,
            human_input=payload.human_input or {},
            actor_user_id=user.id,
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


@router.get("/runs/{run_id}")
async def get_workflow_run(
    run_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    run = await _owned_workflow_run(db, owner_id=user.id, run_id=run_id)
    return {
        "id": run.id,
        "workflow_id": run.workflow_id,
        "workflow_version_id": run.workflow_version_id,
        "project_id": run.project_id,
        "task_id": run.task_id,
        "status": run.status,
        "current_node_id": run.current_node_id,
        "context_json": run.context_json or {},
        "result_json": run.result_json or {},
        "created_at": run.created_at,
        "updated_at": run.updated_at,
    }


@router.get("/runs/{run_id}/steps")
async def list_workflow_run_steps(
    run_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    await _owned_workflow_run(db, owner_id=user.id, run_id=run_id)
    result = await db.execute(
        select(WorkflowStepRun)
        .where(WorkflowStepRun.workflow_run_id == run_id)
        .order_by(WorkflowStepRun.created_at.asc())
    )
    return [
        {
            "id": step.id,
            "workflow_run_id": step.workflow_run_id,
            "node_id": step.node_id,
            "node_type": step.node_type,
            "status": step.status,
            "input_json": step.input_json or {},
            "output_json": step.output_json or {},
            "error": step.error,
            "retry_count": 0,
            "started_at": step.started_at,
            "finished_at": step.finished_at,
            "created_at": step.created_at,
        }
        for step in result.scalars().all()
    ]


@router.get("/runs/{run_id}/stream")
async def workflow_run_stream(
    run_id: str,
    request: Request,
    user: User = Depends(get_authenticated_user),
):
    return await live_snapshot_stream(
        lambda: _with_fresh_workforce_session(
            lambda db: _workflow_run_steps_snapshot(db, owner_id=user.id, run_id=run_id)
        ),
        request=request,
        stream_name="workflow_run",
    )
