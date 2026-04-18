import asyncio
import json
from datetime import datetime
from typing import Any

from fastapi import APIRouter, Body, Depends, File, Form, Query, UploadFile
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.schemas import (
    ActiveRunSummary,
    AgentCreate,
    AgentFromTemplateRequest,
    AgentInheritancePreview,
    AgentLintSummary,
    AgentMarkdownValidationResponse,
    AgentMemoryEntryResponse,
    AgentResolvedProfile,
    AgentResponse,
    AgentTemplateResponse,
    AgentTemplateCreate,
    AgentTemplateUpdate,
    AgentTestRunRequest,
    AgentTestRunResponse,
    AgentUpdate,
    AgentVersionResponse,
    ApprovalDecision,
    ApprovalResponse,
    BrainstormCreate,
    BrainstormDiscourseInsightsResponse,
    BrainstormMessageResponse,
    BrainstormParticipantResponse,
    BrainstormResponse,
    CostAggregationResponse,
    DagParallelStartPayload,
    DagParallelStartResult,
    DagReadyTaskItem,
    EvalRecordCreate,
    EvalLeaderboardEntryResponse,
    EvalRecordResponse,
    EpisodicArchiveManifestResponse,
    EpisodicSearchResponse,
    EvalRecordUpdate,
    ExecutionInsightsResponse,
    ExecutionSnapshotMeta,
    GateConfigResponse,
    GateConfigUpdate,
    KnowledgeSearchResultResponse,
    MemorySettingsPatch,
    MemorySettingsResponse,
    PendingSemanticWriteResponse,
    MergeResolveRunPayload,
    MemoryIngestJobResponse,
    ModelCapabilityResponse,
    OverviewResponse,
    PendingApprovalSummary,
    PendingGithubSyncSummary,
    PortfolioControlPlaneResponse,
    PortfolioExecutionPolicyResponse,
    PortfolioExecutionPolicyUpdate,
    PortfolioProjectSummary,
    ProceduralPlaybookCreate,
    ProceduralPlaybookResponse,
    ProceduralPlaybookUpdate,
    PromoteWorkingMemoryRequest,
    ProjectCreate,
    ProjectDecisionCreate,
    ProjectDecisionResponse,
    ProjectDocumentResponse,
    ProjectMilestoneCreate,
    ProjectMilestoneResponse,
    ProjectMilestoneUpdate,
    ProjectRepositoryLinkCreate,
    ProjectRepositoryLinkResponse,
    ProjectResponse,
    ProjectUpdate,
    ProviderCompareRequest,
    ProviderCompareResponse,
    ProviderConfigCreate,
    ProviderConfigResponse,
    ProviderConfigUpdate,
    ProviderModelListResponse,
    ReplayRunRequest,
    RunCostSummaryResponse,
    RunEventResponse,
    RunEventTailItem,
    RunExecutionSnapshotResponse,
    RunTraceStep,
    RuntimeInfoResponse,
    SemanticConflictGroupResponse,
    SemanticMemoryEntryCreate,
    SemanticMemoryLinkCreate,
    SemanticMemoryLinkResponse,
    SemanticMergeRequest,
    SemanticMemoryEntryResponse,
    SemanticMemoryEntryUpdate,
    SkillPackResponse,
    SkillPackCreate,
    SkillPackUpdate,
    TaskAcceptanceCheckResponse,
    TaskArtifactCreate,
    TaskArtifactResponse,
    TaskCommentCreate,
    TaskCommentResponse,
    TaskCreate,
    TaskDecomposeRequest,
    TaskExecutionSnapshotResponse,
    TaskMemoryCoordinationPatch,
    TaskMemoryCoordinationResponse,
    TaskResponse,
    TaskRunCreate,
    TaskRunResponse,
    TaskTimelineEntry,
    TaskUpdate,
    TeamTemplateCreate,
    TeamTemplateResponse,
    TeamTemplateUpdate,
    WorkflowSignalRequest,
    WorkflowTemplateResponse,
    WorkingMemoryPatch,
    WorkingMemoryResponse,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.service import OrchestrationService
from backend.modules.orchestration.workflow_templates import BUILTIN_WORKFLOW_TEMPLATES

router = APIRouter()
public_router = APIRouter()


def _agent(item) -> AgentResponse:
    inheritance_payload = getattr(item, "__orchestration_inheritance__", None)
    lint_payload = getattr(item, "__orchestration_lint__", None)
    return AgentResponse(
        id=item.id,
        project_id=item.project_id,
        parent_agent_id=item.parent_agent_id,
        reviewer_agent_id=item.reviewer_agent_id,
        provider_config_id=item.provider_config_id,
        parent_template_slug=item.parent_template_slug,
        name=item.name,
        slug=item.slug,
        description=item.description,
        role=item.role,
        system_prompt=item.system_prompt,
        mission_markdown=item.mission_markdown,
        rules_markdown=item.rules_markdown,
        output_contract_markdown=item.output_contract_markdown,
        source_markdown=item.source_markdown,
        capabilities=item.capabilities_json,
        allowed_tools=item.allowed_tools_json,
        skills=item.skills_json,
        model_policy=item.model_policy_json,
        visibility=item.visibility,
        is_active=item.is_active,
        tags=item.tags_json,
        budget=item.budget_json,
        timeout_seconds=item.timeout_seconds,
        retry_limit=item.retry_limit,
        memory_policy=item.memory_policy_json,
        output_schema=item.output_schema_json,
        inheritance=(
            AgentInheritancePreview(
                parent_template_slug=inheritance_payload.get("parent_template_slug"),
                inherited_fields=inheritance_payload.get("inherited_fields", {}),
                overridden_fields=inheritance_payload.get("overridden_fields", {}),
                effective=AgentResolvedProfile(**inheritance_payload.get("effective", {})),
            )
            if inheritance_payload
            else None
        ),
        lint=AgentLintSummary(**lint_payload) if lint_payload else None,
        metadata=item.metadata_json or {},
        version=item.version,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _provider(item) -> ProviderConfigResponse:
    return ProviderConfigResponse(
        id=item.id,
        project_id=item.project_id,
        name=item.name,
        provider_type=item.provider_type,
        base_url=item.base_url,
        api_key_hint=item.api_key_hint,
        organization=item.organization,
        default_model=item.default_model,
        fallback_model=item.fallback_model,
        temperature=item.temperature,
        max_tokens=item.max_tokens,
        timeout_seconds=item.timeout_seconds,
        is_default=item.is_default,
        is_enabled=item.is_enabled,
        metadata=item.metadata_json,
        last_healthcheck_status=item.last_healthcheck_status,
        last_healthcheck_latency_ms=item.last_healthcheck_latency_ms,
        is_healthy=item.is_healthy,
        last_healthcheck_at=item.last_healthcheck_at,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _model_capability(item) -> ModelCapabilityResponse:
    return ModelCapabilityResponse(
        id=item.id,
        provider_type=item.provider_type,
        model_slug=item.model_slug,
        display_name=item.display_name,
        supports_tools=item.supports_tools,
        supports_vision=item.supports_vision,
        max_context_tokens=item.max_context_tokens,
        cost_per_1k_input=item.cost_per_1k_input,
        cost_per_1k_output=item.cost_per_1k_output,
        metadata=item.metadata_json,
        is_active=item.is_active,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _project(item) -> ProjectResponse:
    return ProjectResponse(
        id=item.id,
        name=item.name,
        slug=item.slug,
        description=item.description,
        status=item.status,
        goals_markdown=item.goals_markdown,
        settings=item.settings_json,
        memory_scope=item.memory_scope,
        knowledge_summary=item.knowledge_summary,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _project_repo(item) -> ProjectRepositoryLinkResponse:
    return ProjectRepositoryLinkResponse(
        id=item.id,
        github_repository_id=item.github_repository_id,
        provider=item.provider,
        owner_name=item.owner_name,
        repo_name=item.repo_name,
        full_name=item.full_name,
        default_branch=item.default_branch,
        repository_url=item.repository_url,
        metadata=item.metadata_json,
    )


def _task(
    item,
    dependency_ids: list[str],
    github_summary: dict[str, Any] | None = None,
) -> TaskResponse:
    gh_num = gh_url = gh_repo = None
    if github_summary:
        raw_n = github_summary.get("issue_number")
        gh_num = int(raw_n) if raw_n is not None else None
        u = github_summary.get("issue_url")
        gh_url = str(u) if u else None
        rfn = github_summary.get("repository_full_name")
        gh_repo = str(rfn) if rfn else None
    return TaskResponse(
        id=item.id,
        project_id=item.project_id,
        created_by_user_id=item.created_by_user_id,
        assigned_agent_id=item.assigned_agent_id,
        reviewer_agent_id=item.reviewer_agent_id,
        github_issue_link_id=item.github_issue_link_id,
        github_issue_number=gh_num,
        github_issue_url=gh_url,
        github_repository_full_name=gh_repo,
        parent_task_id=item.parent_task_id,
        title=item.title,
        description=item.description,
        source=item.source,
        task_type=item.task_type,
        priority=item.priority,
        status=item.status,
        acceptance_criteria=item.acceptance_criteria,
        due_date=item.due_date,
        response_sla_hours=getattr(item, "response_sla_hours", None),
        labels=item.labels_json,
        result_summary=item.result_summary,
        result_payload=item.result_payload_json,
        position=item.position,
        metadata=item.metadata_json,
        dependency_ids=dependency_ids,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


async def _tasks_to_responses(
    service: OrchestrationService,
    tasks: list,
    *,
    deps_by_id: dict[str, list[str]] | None = None,
) -> list[TaskResponse]:
    link_ids = [t.github_issue_link_id for t in tasks if t.github_issue_link_id]
    summaries = await service.github_issue_summaries_for_link_ids(link_ids)
    result: list[TaskResponse] = []
    for t in tasks:
        deps: list[str] = [] if deps_by_id is None else deps_by_id.get(t.id, [])
        gh = summaries.get(t.github_issue_link_id) if t.github_issue_link_id else None
        result.append(_task(t, deps, gh))
    return result


def _run(item) -> TaskRunResponse:
    return TaskRunResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        triggered_by_user_id=item.triggered_by_user_id,
        orchestrator_agent_id=item.orchestrator_agent_id,
        worker_agent_id=item.worker_agent_id,
        reviewer_agent_id=item.reviewer_agent_id,
        provider_config_id=item.provider_config_id,
        brainstorm_id=item.brainstorm_id,
        run_mode=item.run_mode,
        status=item.status,
        model_name=item.model_name,
        attempt_number=item.attempt_number,
        token_input=item.token_input,
        token_output=item.token_output,
        token_total=item.token_total,
        estimated_cost_micros=item.estimated_cost_micros,
        latency_ms=item.latency_ms,
        error_message=item.error_message,
        retry_count=item.retry_count,
        checkpoint_json=item.checkpoint_json,
        input_payload=item.input_payload_json,
        output_payload=item.output_payload_json,
        created_at=item.created_at,
        started_at=item.started_at,
        completed_at=item.completed_at,
        cancelled_at=item.cancelled_at,
    )


def _task_execution_snapshot(raw: dict[str, Any]) -> TaskExecutionSnapshotResponse:
    return TaskExecutionSnapshotResponse(
        meta=ExecutionSnapshotMeta(**raw["meta"]),
        project_id=raw["project_id"],
        task_id=raw["task_id"],
        task_status=raw["task_status"],
        task_title=raw["task_title"],
        has_active_run=raw["has_active_run"],
        active_runs=[ActiveRunSummary(**x) for x in raw["active_runs"]],
        pending_approvals=[PendingApprovalSummary(**x) for x in raw["pending_approvals"]],
        pending_github_sync=[PendingGithubSyncSummary(**x) for x in raw["pending_github_sync"]],
        metadata_views=raw["metadata_views"],
        routing_explainability=raw.get("routing_explainability") or {},
        acceptance_summary=raw.get("acceptance_summary") or {},
        execution_memory=raw.get("execution_memory") or {},
        changed_artifacts=raw.get("changed_artifacts") or [],
        last_run_id=raw["last_run_id"],
        focal_run_id=raw["focal_run_id"],
        checkpoint_excerpt=raw["checkpoint_excerpt"],
        recent_events_tail=[RunEventTailItem(**x) for x in raw["recent_events_tail"]],
        trace=[RunTraceStep(**x) for x in raw.get("trace", [])],
        durable_workflow=raw.get("durable_workflow") or {},
    )


def _run_execution_snapshot(raw: dict[str, Any]) -> RunExecutionSnapshotResponse:
    return RunExecutionSnapshotResponse(
        meta=ExecutionSnapshotMeta(**raw["meta"]),
        project_id=raw["project_id"],
        run=_run(raw["run"]),
        task_id=raw["task_id"],
        pending_approvals=[PendingApprovalSummary(**x) for x in raw["pending_approvals"]],
        pending_github_sync=[PendingGithubSyncSummary(**x) for x in raw["pending_github_sync"]],
        routing_explainability=raw.get("routing_explainability") or {},
        execution_memory=raw.get("execution_memory") or {},
        changed_artifacts=raw.get("changed_artifacts") or [],
        checkpoint_excerpt=raw["checkpoint_excerpt"],
        recent_events_tail=[RunEventTailItem(**x) for x in raw["recent_events_tail"]],
        trace=[RunTraceStep(**x) for x in raw.get("trace", [])],
        durable_workflow=raw.get("durable_workflow") or {},
        resumable=bool(raw.get("resumable", False)),
    )


def _semantic_entry(item) -> SemanticMemoryEntryResponse:
    return SemanticMemoryEntryResponse(
        id=item.id,
        owner_id=item.owner_id,
        scope=item.scope,
        project_id=item.project_id,
        agent_id=item.agent_id,
        entry_type=item.entry_type,
        namespace=item.namespace,
        title=item.title,
        body=item.body,
        metadata=item.metadata_json or {},
        source_chunk_id=item.source_chunk_id,
        source_task_id=item.source_task_id,
        source_run_id=item.source_run_id,
        provenance=item.provenance_json or {},
        created_by_user_id=item.created_by_user_id,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _procedural_playbook(item) -> ProceduralPlaybookResponse:
    return ProceduralPlaybookResponse(
        id=item.id,
        owner_id=item.owner_id,
        project_id=item.project_id,
        slug=item.slug,
        title=item.title,
        body_md=item.body_md,
        version=item.version,
        tags=list(item.tags_json or []),
        namespace=item.namespace,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _working_memory_payload(wm: dict[str, Any]) -> WorkingMemoryResponse:
    return WorkingMemoryResponse(
        schema_version=str(wm.get("schema_version") or "1.0"),
        objective=str(wm.get("objective") or ""),
        accepted_plan=str(wm.get("accepted_plan") or ""),
        latest_findings=str(wm.get("latest_findings") or ""),
        temp_notes=str(wm.get("temp_notes") or ""),
        open_questions=str(wm.get("open_questions") or ""),
        discussion_summary=str(wm.get("discussion_summary") or ""),
        artifact_refs=list(wm.get("artifact_refs") or []),
        updated_at=str(wm.get("updated_at") or ""),
    )


def _event(item) -> RunEventResponse:
    return RunEventResponse(
        id=item.id,
        run_id=item.run_id,
        task_id=item.task_id,
        level=item.level,
        event_type=item.event_type,
        message=item.message,
        payload=item.payload_json,
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        cost_usd_micros=item.cost_usd_micros,
        created_at=item.created_at,
    )


def _eval(item) -> EvalRecordResponse:
    return EvalRecordResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        name=item.name,
        run_a_id=item.run_a_id,
        run_b_id=item.run_b_id,
        agent_a_id=item.agent_a_id,
        agent_b_id=item.agent_b_id,
        model_a=item.model_a,
        model_b=item.model_b,
        winner=item.winner,
        score_a=item.score_a,
        score_b=item.score_b,
        criteria_met_a=item.criteria_met_a,
        criteria_met_b=item.criteria_met_b,
        notes=item.notes,
        metadata_json=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _brainstorm(item) -> BrainstormResponse:
    extras = getattr(item, "__orchestration_view__", {})
    return BrainstormResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        initiator_user_id=item.initiator_user_id,
        moderator_agent_id=item.moderator_agent_id,
        topic=item.topic,
        status=item.status,
        mode=extras.get("mode", (item.stop_conditions_json or {}).get("mode", "exploration")),
        output_type=extras.get("output_type", (item.stop_conditions_json or {}).get("output_type", "implementation_plan")),
        max_rounds=item.max_rounds,
        stop_conditions=item.stop_conditions_json,
        participant_count=extras.get("participant_count", 0),
        current_round=extras.get("current_round", 0),
        consensus_status=extras.get("consensus_status", "open"),
        latest_round_summary=extras.get("latest_round_summary"),
        summary=item.summary,
        final_recommendation=item.final_recommendation,
        decision_log=item.decision_log_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _brainstorm_participant(item) -> BrainstormParticipantResponse:
    return BrainstormParticipantResponse(
        id=item.id,
        brainstorm_id=item.brainstorm_id,
        agent_id=item.agent_id,
        order_index=item.order_index,
        stance=item.stance,
        created_at=item.created_at,
    )


def _brainstorm_message(item) -> BrainstormMessageResponse:
    return BrainstormMessageResponse(
        id=item.id,
        brainstorm_id=item.brainstorm_id,
        agent_id=item.agent_id,
        round_number=item.round_number,
        message_type=item.message_type,
        content=item.content,
        metadata=item.metadata_json,
        created_at=item.created_at,
    )


def _approval(item) -> ApprovalResponse:
    return ApprovalResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        run_id=item.run_id,
        issue_link_id=item.issue_link_id,
        requested_by_user_id=item.requested_by_user_id,
        approved_by_user_id=item.approved_by_user_id,
        approval_type=item.approval_type,
        status=item.status,
        reason=item.reason,
        payload=item.payload_json,
        created_at=item.created_at,
        resolved_at=item.resolved_at,
    )


def _document(item) -> ProjectDocumentResponse:
    return ProjectDocumentResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        uploaded_by_user_id=item.uploaded_by_user_id,
        filename=item.filename,
        content_type=item.content_type,
        source_text=item.source_text,
        object_key=item.object_key,
        size_bytes=item.size_bytes,
        summary_text=item.summary_text,
        ingestion_status=item.ingestion_status,
        chunk_count=item.chunk_count,
        ttl_days=item.ttl_days,
        expires_at=item.expires_at,
        deleted_at=item.deleted_at,
        metadata=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _memory(item) -> AgentMemoryEntryResponse:
    return AgentMemoryEntryResponse(
        id=item.id,
        owner_id=item.owner_id,
        agent_id=item.agent_id,
        project_id=item.project_id,
        source_run_id=item.source_run_id,
        key=item.key,
        value_text=item.value_text,
        scope=item.scope,
        status=item.status,
        approved_by_user_id=item.approved_by_user_id,
        ttl_days=item.ttl_days,
        expires_at=item.expires_at,
        deleted_at=item.deleted_at,
        metadata=item.metadata_json,
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def _project_decision(item) -> ProjectDecisionResponse:
    return ProjectDecisionResponse(
        id=item.id,
        project_id=item.project_id,
        task_id=item.task_id,
        brainstorm_id=item.brainstorm_id,
        title=item.title,
        decision=item.decision,
        rationale=item.rationale,
        author_label=item.author_label,
        created_at=item.created_at,
    )


@router.get("/overview", response_model=OverviewResponse)
async def overview(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    data = await service.get_overview(current_user)
    return OverviewResponse(
        projects=[_project(item) for item in data["projects"]],
        agents=[_agent(item) for item in data["agents"]],
        active_runs=[_run(item) for item in data["active_runs"]],
        pending_approvals=[_approval(item) for item in data["pending_approvals"]],
        github_events=[_github_sync_event(item) for item in data["github_events"]],
    )


@router.get("/runtime-info", response_model=RuntimeInfoResponse)
async def orchestration_runtime_info(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await OrchestrationService(db).get_runtime_info(current_user)
    return RuntimeInfoResponse(**data)


@router.get("/memory-metrics")
async def orchestration_memory_metrics(
    current_user: User = Depends(get_current_user),
):
    del current_user  # authenticated; metrics are process-global for now
    from backend.modules.orchestration.memory_metrics import snapshot_memory_metrics

    return snapshot_memory_metrics()


@router.get("/portfolio", response_model=list[PortfolioProjectSummary])
async def orchestration_portfolio(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).summarize_portfolio(current_user)
    return [PortfolioProjectSummary(**row) for row in rows]


@router.get("/portfolio/control-plane", response_model=PortfolioControlPlaneResponse)
async def orchestration_portfolio_control_plane(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).portfolio_control_plane(current_user)
    return PortfolioControlPlaneResponse(**payload)


@router.get("/portfolio/execution-policy", response_model=PortfolioExecutionPolicyResponse)
async def orchestration_portfolio_execution_policy(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).get_portfolio_execution_policy(current_user)
    return PortfolioExecutionPolicyResponse(**payload)


@router.put("/portfolio/execution-policy", response_model=PortfolioExecutionPolicyResponse)
async def update_orchestration_portfolio_execution_policy(
    payload: PortfolioExecutionPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await OrchestrationService(db).update_portfolio_execution_policy(
        current_user,
        payload.model_dump(exclude_none=True),
    )
    return PortfolioExecutionPolicyResponse(**data)


async def _live_snapshot_stream(snapshot_factory):
    last_signature: str | None = None

    async def event_stream():
        nonlocal last_signature
        for tick in range(900):
            snapshot = await snapshot_factory()
            payload = json.dumps(snapshot, default=str, sort_keys=True)
            if payload != last_signature:
                last_signature = payload
                yield f"event: snapshot\ndata: {payload}\n\n"
            elif tick % 10 == 0:
                yield "event: heartbeat\ndata: {}\n\n"
            await asyncio.sleep(2)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.get("/portfolio/stream")
async def orchestration_portfolio_stream(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return await _live_snapshot_stream(lambda: service.portfolio_live_snapshot(current_user))


@router.get("/hierarchy/stream")
async def hierarchy_stream(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return await _live_snapshot_stream(lambda: service.hierarchy_live_snapshot(current_user))


@router.post("/agents/validate-markdown", response_model=AgentMarkdownValidationResponse)
async def validate_markdown(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    content = (await file.read()).decode("utf-8")
    normalized, errors, warnings = await service.validate_agent_markdown(current_user, content)
    return AgentMarkdownValidationResponse(
        valid=not errors,
        normalized=normalized,
        errors=errors,
        warnings=warnings,
        activation_ready=not errors,
    )


@router.get("/agents", response_model=list[AgentResponse])
async def list_agents(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    items = await service.list_agents(current_user, project_id)
    for item in items:
        item.__orchestration_inheritance__ = await service.resolve_agent_inheritance(item)
        item.__orchestration_lint__ = await service.summarize_agent_lint(current_user, item)
    return [_agent(item) for item in items]


@router.post("/agents", response_model=AgentResponse, status_code=201)
async def create_agent(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.create_agent(current_user, payload.model_dump())
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.post("/agents/import", response_model=AgentResponse, status_code=201)
async def import_agent(
    file: UploadFile = File(...),
    project_id: str | None = Form(default=None),
    existing_agent_id: str | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    content = (await file.read()).decode("utf-8")
    service = OrchestrationService(db)
    item = await service.import_agent_markdown(
        current_user,
        content=content,
        project_id=project_id,
        existing_agent_id=existing_agent_id,
    )
    item.__orchestration_inheritance__ = await service.resolve_agent_inheritance(item)
    item.__orchestration_lint__ = await service.summarize_agent_lint(current_user, item)
    return _agent(item)


@router.get("/agents/templates", response_model=list[AgentTemplateResponse])
async def list_agent_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    templates = await OrchestrationService(db).list_agent_templates()
    return [AgentTemplateResponse(**t) for t in templates]


@router.get("/agents/skills", response_model=list[SkillPackResponse])
async def list_skill_catalog(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [SkillPackResponse(**item) for item in await OrchestrationService(db).list_skill_catalog()]


@router.post("/agents/skills", response_model=SkillPackResponse, status_code=201)
async def create_skill_pack(
    payload: SkillPackCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).create_skill_pack(payload.model_dump(exclude_none=True))
    return SkillPackResponse(**result)


@router.patch("/agents/skills/{slug}", response_model=SkillPackResponse)
async def update_skill_pack(
    slug: str,
    payload: SkillPackUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).update_skill_pack(slug, payload.model_dump(exclude_unset=True))
    return SkillPackResponse(**result)


@router.delete("/agents/skills/{slug}", status_code=204)
async def delete_skill_pack(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_skill_pack(slug)


@router.post("/agents/from-template/{template_slug}", response_model=AgentResponse, status_code=201)
async def create_agent_from_template(
    template_slug: str,
    payload: AgentFromTemplateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.create_agent_from_template(
        current_user, template_slug, payload.model_dump(exclude_unset=True)
    )
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.post("/agents/templates", response_model=AgentTemplateResponse, status_code=201)
async def create_agent_template(
    payload: AgentTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).create_agent_template(payload.model_dump(exclude_none=True))
    return AgentTemplateResponse(**result)


@router.patch("/agents/templates/{slug}", response_model=AgentTemplateResponse)
async def update_agent_template(
    slug: str,
    payload: AgentTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).update_agent_template(
        slug, payload.model_dump(exclude_unset=True, exclude_none=True)
    )
    return AgentTemplateResponse(**result)


@router.delete("/agents/templates/{slug}", status_code=204)
async def delete_agent_template(
    slug: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_agent_template(slug)


@router.get("/teams/templates", response_model=list[TeamTemplateResponse])
async def list_team_templates(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    items = await OrchestrationService(db).list_team_templates()
    return [TeamTemplateResponse(**item) for item in items]


@router.post("/teams/templates", response_model=TeamTemplateResponse, status_code=201)
async def create_team_template(
    payload: TeamTemplateCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).create_team_template(payload.model_dump(exclude_none=True))
    return TeamTemplateResponse(**result)


@router.patch("/teams/templates/{template_id}", response_model=TeamTemplateResponse)
async def update_team_template(
    template_id: str,
    payload: TeamTemplateUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).update_team_template(
        template_id, payload.model_dump(exclude_unset=True)
    )
    return TeamTemplateResponse(**result)


@router.delete("/teams/templates/{template_id}", status_code=204)
async def delete_team_template(
    template_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_team_template(template_id)


@router.get("/agents/{agent_id}", response_model=AgentResponse)
async def get_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.get_agent(current_user, agent_id)
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.patch("/agents/{agent_id}", response_model=AgentResponse)
async def update_agent(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.update_agent(current_user, agent_id, payload.model_dump(exclude_unset=True))
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.post("/agents/{agent_id}/duplicate", response_model=AgentResponse, status_code=201)
async def duplicate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.duplicate_agent(current_user, agent_id)
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.post("/agents/{agent_id}/activate", response_model=AgentResponse)
async def activate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.set_agent_active_state(current_user, agent_id, True)
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.post("/agents/{agent_id}/deactivate", response_model=AgentResponse)
async def deactivate_agent(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    agent = await service.set_agent_active_state(current_user, agent_id, False)
    agent.__orchestration_inheritance__ = await service.resolve_agent_inheritance(agent)
    agent.__orchestration_lint__ = await service.summarize_agent_lint(current_user, agent)
    return _agent(agent)


@router.post("/agents/{agent_id}/test-run", response_model=AgentTestRunResponse)
async def test_run_agent(
    agent_id: str,
    payload: AgentTestRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).test_run_agent(
        current_user, agent_id, payload.model_dump()
    )
    return AgentTestRunResponse(**result)


@router.get("/agents/{agent_id}/versions", response_model=list[AgentVersionResponse])
async def list_agent_versions(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [AgentVersionResponse.model_validate(item) for item in await OrchestrationService(db).list_agent_versions(current_user, agent_id)]


@router.get("/projects", response_model=list[ProjectResponse])
async def list_projects(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_project(item) for item in await OrchestrationService(db).list_projects(current_user)]


@router.post("/projects", response_model=ProjectResponse, status_code=201)
async def create_project(
    payload: ProjectCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project(await OrchestrationService(db).create_project(current_user, payload.model_dump()))


@router.get("/projects/{project_id}", response_model=ProjectResponse)
async def get_project(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project(await OrchestrationService(db).get_project(current_user, project_id))


@router.patch("/projects/{project_id}", response_model=ProjectResponse)
async def update_project(
    project_id: str,
    payload: ProjectUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project(await OrchestrationService(db).update_project(current_user, project_id, payload.model_dump(exclude_unset=True)))


@router.get("/projects/{project_id}/gate-config", response_model=GateConfigResponse)
async def get_gate_config(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).get_gate_config(current_user, project_id)


@router.patch("/projects/{project_id}/gate-config", response_model=GateConfigResponse)
async def update_gate_config(
    project_id: str,
    payload: GateConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).update_gate_config(current_user, project_id, payload.autonomy_level, payload.approval_gates)


@router.get("/projects/{project_id}/memory-settings", response_model=MemorySettingsResponse)
async def get_project_memory_settings(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await OrchestrationService(db).get_project_memory_settings(current_user, project_id)
    return MemorySettingsResponse(**data)


@router.patch("/projects/{project_id}/memory-settings", response_model=MemorySettingsResponse)
async def patch_project_memory_settings(
    project_id: str,
    payload: MemorySettingsPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await OrchestrationService(db).update_project_memory_settings(
        current_user, project_id, payload.model_dump(exclude_unset=True)
    )
    return MemorySettingsResponse(**data)


@router.get("/projects/{project_id}/semantic-memory", response_model=list[SemanticMemoryEntryResponse])
async def list_semantic_memory(
    project_id: str,
    q: str | None = None,
    vec_q: str | None = None,
    entry_type: str | None = None,
    namespace_prefix: str | None = None,
    limit: int = Query(100, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_semantic_memory_entries_for_project(
        current_user,
        project_id,
        q=q,
        vec_q=vec_q,
        entry_type=entry_type,
        namespace_prefix=namespace_prefix,
        limit=limit,
    )
    return [_semantic_entry(item) for item in rows]


@router.post(
    "/projects/{project_id}/semantic-memory",
    responses={201: {"model": SemanticMemoryEntryResponse}, 202: {"model": PendingSemanticWriteResponse}},
)
async def create_semantic_memory(
    project_id: str,
    payload: SemanticMemoryEntryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).create_semantic_memory_entry_for_project(
        current_user, project_id, payload.model_dump()
    )
    if isinstance(item, ApprovalRequest):
        return JSONResponse(
            status_code=202,
            content=PendingSemanticWriteResponse(
                approval_id=item.id, approval_type=item.approval_type
            ).model_dump(),
        )
    return _semantic_entry(item)


@router.post(
    "/projects/{project_id}/semantic-memory/promote-from-working-memory",
    response_model=SemanticMemoryEntryResponse,
    status_code=201,
)
async def promote_working_memory_to_semantic(
    project_id: str,
    payload: PromoteWorkingMemoryRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).promote_working_memory_to_semantic_entry(
        current_user,
        project_id,
        run_id=payload.run_id,
        entry_type=payload.entry_type,
        title=payload.title,
    )
    return _semantic_entry(item)


@router.get(
    "/projects/{project_id}/semantic-memory/conflicts",
    response_model=list[SemanticConflictGroupResponse],
)
async def list_semantic_memory_conflicts(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_semantic_memory_conflicts(current_user, project_id)
    return [SemanticConflictGroupResponse(**r) for r in rows]


@router.post(
    "/projects/{project_id}/semantic-memory/merge",
    response_model=SemanticMemoryEntryResponse,
)
async def merge_semantic_memory_entries(
    project_id: str,
    payload: SemanticMergeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).merge_semantic_memory_entries_for_project(
        current_user,
        project_id,
        canonical_entry_id=payload.canonical_entry_id,
        merge_entry_ids=payload.merge_entry_ids,
        link_relation=payload.link_relation,
    )
    return _semantic_entry(item)


@router.post(
    "/projects/{project_id}/semantic-memory/links",
    response_model=SemanticMemoryLinkResponse,
    status_code=201,
)
async def create_semantic_memory_link(
    project_id: str,
    payload: SemanticMemoryLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    row = await OrchestrationService(db).create_semantic_memory_link_for_project(
        current_user,
        project_id,
        from_entry_id=payload.from_entry_id,
        to_entry_id=payload.to_entry_id,
        relation_type=payload.relation_type,
        metadata=payload.metadata,
    )
    return SemanticMemoryLinkResponse(
        id=row.id,
        owner_id=row.owner_id,
        project_id=row.project_id,
        from_entry_id=row.from_entry_id,
        to_entry_id=row.to_entry_id,
        relation_type=row.relation_type,
        metadata=row.metadata_json or {},
        created_at=row.created_at,
    )


@router.delete("/projects/{project_id}/semantic-memory/links/{link_id}", status_code=204)
async def delete_semantic_memory_link(
    project_id: str,
    link_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_semantic_memory_link_for_project(
        current_user, project_id, link_id
    )
    return Response(status_code=204)


@router.get(
    "/projects/{project_id}/semantic-memory/{entry_id}/links",
    response_model=list[SemanticMemoryLinkResponse],
)
async def list_semantic_memory_links(
    project_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_semantic_memory_links_for_entry(
        current_user, project_id, entry_id
    )
    return [
        SemanticMemoryLinkResponse(
            id=r.id,
            owner_id=r.owner_id,
            project_id=r.project_id,
            from_entry_id=r.from_entry_id,
            to_entry_id=r.to_entry_id,
            relation_type=r.relation_type,
            metadata=r.metadata_json or {},
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.get("/projects/{project_id}/semantic-memory/{entry_id}", response_model=SemanticMemoryEntryResponse)
async def get_semantic_memory(
    project_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).get_semantic_memory_entry_for_project(
        current_user, project_id, entry_id
    )
    return _semantic_entry(item)


@router.patch(
    "/projects/{project_id}/semantic-memory/{entry_id}",
    responses={200: {"model": SemanticMemoryEntryResponse}, 202: {"model": PendingSemanticWriteResponse}},
)
async def update_semantic_memory(
    project_id: str,
    entry_id: str,
    payload: SemanticMemoryEntryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).update_semantic_memory_entry_for_project(
        current_user,
        project_id,
        entry_id,
        payload.model_dump(exclude_unset=True),
    )
    if isinstance(item, ApprovalRequest):
        return JSONResponse(
            status_code=202,
            content=PendingSemanticWriteResponse(
                approval_id=item.id, approval_type=item.approval_type
            ).model_dump(),
        )
    return _semantic_entry(item)


@router.delete(
    "/projects/{project_id}/semantic-memory/{entry_id}",
    responses={204: {}, 202: {"model": PendingSemanticWriteResponse}},
)
async def delete_semantic_memory(
    project_id: str,
    entry_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    out = await OrchestrationService(db).delete_semantic_memory_entry_for_project(
        current_user, project_id, entry_id
    )
    if isinstance(out, ApprovalRequest):
        return JSONResponse(
            status_code=202,
            content=PendingSemanticWriteResponse(
                approval_id=out.id, approval_type=out.approval_type
            ).model_dump(),
        )
    return Response(status_code=204)


@router.get("/projects/{project_id}/episodic-memory/search", response_model=EpisodicSearchResponse)
async def search_episodic_memory(
    project_id: str,
    q: str | None = None,
    vec_q: str | None = None,
    limit: int = Query(45, ge=1, le=200),
    since: datetime | None = None,
    until: datetime | None = None,
    task_id: str | None = None,
    kinds: str | None = Query(
        None,
        description="Comma-separated: run_event,task_comment,brainstorm_message",
    ),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    kind_list = [k.strip() for k in kinds.split(",")] if kinds else None
    hits = await OrchestrationService(db).search_episodic_memory(
        current_user,
        project_id,
        q=q,
        vec_q=vec_q,
        limit=limit,
        since=since,
        until=until,
        task_id=task_id,
        kinds=kind_list,
    )
    return EpisodicSearchResponse(hits=hits)


@router.get(
    "/projects/{project_id}/episodic-memory/archives",
    response_model=list[EpisodicArchiveManifestResponse],
)
async def list_episodic_archives(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_episodic_archive_manifests_for_project(
        current_user, project_id
    )
    return [
        EpisodicArchiveManifestResponse(
            id=r.id,
            object_key=r.object_key,
            period_start=r.period_start,
            period_end=r.period_end,
            record_count=r.record_count,
            byte_size=r.byte_size,
            stats_json=r.stats_json or {},
            created_at=r.created_at,
        )
        for r in rows
    ]


@router.post("/projects/{project_id}/episodic-memory/reindex")
async def reindex_episodic_memory(
    project_id: str,
    limit: int = Query(200, ge=1, le=5000),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    n = await OrchestrationService(db).backfill_episodic_search_index(
        current_user, project_id, limit=limit
    )
    return {"indexed": n}


@router.get(
    "/projects/{project_id}/procedural-playbooks",
    response_model=list[ProceduralPlaybookResponse],
)
async def list_procedural_playbooks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_procedural_playbooks_for_project(current_user, project_id)
    return [_procedural_playbook(item) for item in rows]


@router.post(
    "/projects/{project_id}/procedural-playbooks",
    response_model=ProceduralPlaybookResponse,
    status_code=201,
)
async def create_procedural_playbook(
    project_id: str,
    payload: ProceduralPlaybookCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).create_procedural_playbook_for_project(
        current_user, project_id, payload.model_dump()
    )
    return _procedural_playbook(item)


@router.patch(
    "/projects/{project_id}/procedural-playbooks/{playbook_id}",
    response_model=ProceduralPlaybookResponse,
)
async def update_procedural_playbook(
    project_id: str,
    playbook_id: str,
    payload: ProceduralPlaybookUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).update_procedural_playbook_for_project(
        current_user, project_id, playbook_id, payload.model_dump(exclude_unset=True)
    )
    return _procedural_playbook(item)


@router.delete("/projects/{project_id}/procedural-playbooks/{playbook_id}", status_code=204)
async def delete_procedural_playbook(
    project_id: str,
    playbook_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_procedural_playbook_for_project(
        current_user, project_id, playbook_id
    )
    return Response(status_code=204)


@router.get("/projects/{project_id}/repositories", response_model=list[ProjectRepositoryLinkResponse])
async def list_project_repositories(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_project_repo(item) for item in await OrchestrationService(db).list_project_repositories(current_user, project_id)]


@router.patch("/projects/{project_id}/repositories/{repository_link_id}", response_model=ProjectRepositoryLinkResponse)
async def update_project_repository(
    project_id: str,
    repository_link_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project_repo(
        await OrchestrationService(db).update_project_repository(
            current_user, project_id, repository_link_id, payload
        )
    )


@router.get("/projects/{project_id}/memory-ingest-jobs", response_model=list[MemoryIngestJobResponse])
async def list_project_memory_ingest_jobs(
    project_id: str,
    limit: int = Query(60, ge=1, le=300),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_project_memory_ingest_jobs(
        current_user, project_id, limit=limit
    )
    return [MemoryIngestJobResponse(**item) for item in rows]


@router.get("/projects/{project_id}/repositories/index-status")
async def project_repository_index_status(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).project_repository_index_status(current_user, project_id)


@router.post("/projects/{project_id}/repositories", response_model=ProjectRepositoryLinkResponse, status_code=201)
async def add_project_repository(
    project_id: str,
    payload: ProjectRepositoryLinkCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project_repo(await OrchestrationService(db).add_project_repository(current_user, project_id, payload.model_dump()))


@router.get("/projects/{project_id}/tasks", response_model=list[TaskResponse])
async def list_tasks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    tasks = await service.list_tasks(current_user, project_id)
    link_ids = [t.github_issue_link_id for t in tasks if t.github_issue_link_id]
    summaries = await service.github_issue_summaries_for_link_ids(link_ids)
    dependencies = await service.repo.list_task_dependencies(project_id)
    deps_by_task: dict[str, list[str]] = {}
    for dep in dependencies:
        deps_by_task.setdefault(dep.task_id, []).append(dep.depends_on_task_id)
    return [
        _task(
            item,
            deps_by_task.get(item.id, []),
            summaries.get(item.github_issue_link_id) if item.github_issue_link_id else None,
        )
        for item in tasks
    ]


@router.post("/projects/{project_id}/tasks", response_model=TaskResponse, status_code=201)
async def create_task(
    project_id: str,
    payload: TaskCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    item = await service.create_task(current_user, project_id, payload.model_dump())
    gh = (
        await service.github_issue_summaries_for_link_ids([item.github_issue_link_id])
        if item.github_issue_link_id
        else {}
    )
    return _task(item, payload.dependency_ids, gh.get(item.github_issue_link_id) if item.github_issue_link_id else None)


@router.get("/projects/{project_id}/tasks/{task_id}", response_model=TaskResponse)
async def get_task(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    item = await service.get_task(current_user, project_id, task_id)
    gh = (
        await service.github_issue_summaries_for_link_ids([item.github_issue_link_id])
        if item.github_issue_link_id
        else {}
    )
    dependencies = await service.repo.list_task_dependencies(project_id)
    return _task(
        item,
        [dep.depends_on_task_id for dep in dependencies if dep.task_id == task_id],
        gh.get(item.github_issue_link_id) if item.github_issue_link_id else None,
    )


@router.get("/projects/{project_id}/dag/ready-tasks", response_model=list[DagReadyTaskItem])
async def list_dag_ready_tasks(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_dag_ready_tasks(current_user, project_id)
    return [DagReadyTaskItem(**row) for row in rows]


@router.post("/projects/{project_id}/dag/start-ready", response_model=DagParallelStartResult)
async def start_dag_parallel_ready_runs(
    project_id: str,
    payload: DagParallelStartPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    result = await OrchestrationService(db).start_parallel_dag_ready_runs(
        current_user, project_id, payload.model_dump()
    )
    return DagParallelStartResult(**result)


@router.get("/projects/{project_id}/tasks/{task_id}/merge-preview")
async def merge_resolution_preview(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).merge_resolution_preview(current_user, project_id, task_id)


@router.post("/projects/{project_id}/tasks/{task_id}/merge-resolve-run", response_model=TaskRunResponse)
async def start_merge_resolution_run(
    project_id: str,
    task_id: str,
    payload: MergeResolveRunPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    run = await OrchestrationService(db).start_merge_resolution_run(
        current_user, project_id, task_id, payload.model_dump()
    )
    return _run(run)


@router.patch("/projects/{project_id}/tasks/{task_id}", response_model=TaskResponse)
async def update_task(
    project_id: str,
    task_id: str,
    payload: TaskUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    item = await service.update_task(current_user, project_id, task_id, payload.model_dump(exclude_unset=True))
    gh = (
        await service.github_issue_summaries_for_link_ids([item.github_issue_link_id])
        if item.github_issue_link_id
        else {}
    )
    dependencies = await service.repo.list_task_dependencies(project_id)
    return _task(
        item,
        [dep.depends_on_task_id for dep in dependencies if dep.task_id == task_id],
        gh.get(item.github_issue_link_id) if item.github_issue_link_id else None,
    )


@router.delete("/projects/{project_id}/tasks/{task_id}", status_code=204)
async def delete_task(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_task(current_user, project_id, task_id)
    return Response(status_code=204)


@router.get("/projects/{project_id}/tasks/{task_id}/comments", response_model=list[TaskCommentResponse])
async def list_task_comments(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [TaskCommentResponse.model_validate(item) for item in await OrchestrationService(db).list_task_comments(current_user, project_id, task_id)]


@router.post("/projects/{project_id}/tasks/{task_id}/comments", response_model=TaskCommentResponse, status_code=201)
async def add_task_comment(
    project_id: str,
    task_id: str,
    payload: TaskCommentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return TaskCommentResponse.model_validate(await OrchestrationService(db).add_task_comment(current_user, project_id, task_id, payload.body))


@router.get("/projects/{project_id}/tasks/{task_id}/timeline", response_model=list[TaskTimelineEntry])
async def list_task_timeline(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).list_task_timeline(current_user, project_id, task_id)
    return [TaskTimelineEntry(**row) for row in rows]


@router.get(
    "/projects/{project_id}/tasks/{task_id}/execution-state",
    response_model=TaskExecutionSnapshotResponse,
)
async def get_task_execution_state(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await OrchestrationService(db).get_task_execution_snapshot(
        current_user, project_id, task_id
    )
    return _task_execution_snapshot(raw)


@router.get(
    "/projects/{project_id}/tasks/{task_id}/memory-coordination",
    response_model=TaskMemoryCoordinationResponse,
)
async def get_task_memory_coordination(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await OrchestrationService(db).get_task_memory_coordination(
        current_user, project_id, task_id
    )
    return TaskMemoryCoordinationResponse(
        shared=str(raw.get("shared") or ""),
        private={str(k): str(v) for k, v in (raw.get("private") or {}).items()},
    )


@router.patch(
    "/projects/{project_id}/tasks/{task_id}/memory-coordination",
    response_model=TaskMemoryCoordinationResponse,
)
async def patch_task_memory_coordination(
    project_id: str,
    task_id: str,
    payload: TaskMemoryCoordinationPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await OrchestrationService(db).patch_task_memory_coordination(
        current_user, project_id, task_id, payload.model_dump(exclude_unset=True)
    )
    return TaskMemoryCoordinationResponse(
        shared=str(raw.get("shared") or ""),
        private={str(k): str(v) for k, v in (raw.get("private") or {}).items()},
    )


@router.get("/projects/{project_id}/tasks/{task_id}/artifacts", response_model=list[TaskArtifactResponse])
async def list_task_artifacts(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [TaskArtifactResponse(id=item.id, task_id=item.task_id, run_id=item.run_id, kind=item.kind, title=item.title, content=item.content, metadata=item.metadata_json, created_at=item.created_at) for item in await OrchestrationService(db).list_task_artifacts(current_user, project_id, task_id)]


@router.post("/projects/{project_id}/tasks/{task_id}/artifacts", response_model=TaskArtifactResponse, status_code=201)
async def create_task_artifact(
    project_id: str,
    task_id: str,
    payload: TaskArtifactCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).create_task_artifact(current_user, project_id, task_id, payload.kind, payload.title, payload.content, payload.metadata)
    return TaskArtifactResponse(id=item.id, task_id=item.task_id, run_id=item.run_id, kind=item.kind, title=item.title, content=item.content, metadata=item.metadata_json, created_at=item.created_at)


@router.post("/projects/{project_id}/tasks/{task_id}/decompose", response_model=list[TaskResponse], status_code=201)
async def decompose_task(
    project_id: str,
    task_id: str,
    payload: TaskDecomposeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    tasks = await service.decompose_task(current_user, project_id, task_id, payload.max_subtasks, payload.context)
    return await _tasks_to_responses(service, tasks)


@router.get("/projects/{project_id}/tasks/{task_id}/subtasks", response_model=list[TaskResponse])
async def list_subtasks(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    tasks = await service.list_subtasks(current_user, project_id, task_id)
    return await _tasks_to_responses(service, tasks)


@router.post("/projects/{project_id}/tasks/{task_id}/check-acceptance", response_model=TaskAcceptanceCheckResponse)
async def check_task_acceptance(
    project_id: str,
    task_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).check_task_acceptance(current_user, project_id, task_id)


@router.get("/projects/{project_id}/milestones", response_model=list[ProjectMilestoneResponse])
async def list_milestones(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).list_milestones(current_user, project_id)


@router.post("/projects/{project_id}/milestones", response_model=ProjectMilestoneResponse, status_code=201)
async def create_milestone(
    project_id: str,
    payload: ProjectMilestoneCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).create_milestone(current_user, project_id, payload.title, payload.description, payload.due_date, payload.status, payload.position)


@router.patch("/projects/{project_id}/milestones/{milestone_id}", response_model=ProjectMilestoneResponse)
async def update_milestone(
    project_id: str,
    milestone_id: str,
    payload: ProjectMilestoneUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).update_milestone(current_user, project_id, milestone_id, payload.model_dump(exclude_none=True))


@router.get("/projects/{project_id}/decisions", response_model=list[ProjectDecisionResponse])
async def list_decisions(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_project_decision(d) for d in await OrchestrationService(db).list_decisions(current_user, project_id)]


@router.post("/projects/{project_id}/decisions", response_model=ProjectDecisionResponse, status_code=201)
async def create_decision(
    project_id: str,
    payload: ProjectDecisionCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project_decision(await OrchestrationService(db).create_decision(current_user, project_id, payload.title, payload.decision, payload.rationale, payload.author_label, payload.task_id, payload.brainstorm_id))


@router.post("/projects/{project_id}/tasks/{task_id}/runs", response_model=TaskRunResponse, status_code=201)
async def start_task_run(
    project_id: str,
    task_id: str,
    payload: TaskRunCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(
        await OrchestrationService(db).start_task_run(
            current_user,
            project_id,
            task_id,
            payload.model_dump(exclude_unset=True),
        )
    )


@router.get("/projects/{project_id}/evals", response_model=list[EvalRecordResponse])
async def list_eval_records(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_eval(item) for item in await OrchestrationService(db).list_eval_records(current_user, project_id)]


@router.post("/projects/{project_id}/evals", response_model=EvalRecordResponse, status_code=201)
async def create_eval_record(
    project_id: str,
    payload: EvalRecordCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _eval(await OrchestrationService(db).create_eval_record(current_user, project_id, payload.model_dump()))


@router.patch("/projects/{project_id}/evals/{eval_id}", response_model=EvalRecordResponse)
async def update_eval_record(
    project_id: str,
    eval_id: str,
    payload: EvalRecordUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _eval(
        await OrchestrationService(db).update_eval_record(
            current_user, project_id, eval_id, payload.model_dump(exclude_unset=True)
        )
    )


@router.post("/projects/{project_id}/evals/{eval_id}/start")
async def start_benchmark(
    project_id: str,
    eval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).start_benchmark(current_user, project_id, eval_id)


@router.post("/projects/{project_id}/evals/{eval_id}/score", response_model=EvalRecordResponse)
async def score_eval_record(
    project_id: str,
    eval_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _eval(await OrchestrationService(db).score_eval_record(current_user, project_id, eval_id))


@router.get("/projects/{project_id}/evals/leaderboard", response_model=list[EvalLeaderboardEntryResponse])
async def eval_leaderboard(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).eval_leaderboard(current_user, project_id)


@router.post("/projects/{project_id}/evals/benchmark-historical")
async def benchmark_historical(
    project_id: str,
    agent_a_id: str,
    agent_b_id: str,
    model_a: str | None = None,
    model_b: str | None = None,
    days: int = Query(60, ge=1, le=3650),
    limit: int = Query(8, ge=1, le=50),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).benchmark_historical_issues(
        current_user,
        project_id,
        agent_a_id=agent_a_id,
        agent_b_id=agent_b_id,
        model_a=model_a,
        model_b=model_b,
        days=days,
        limit=limit,
    )


@router.get("/runs", response_model=list[TaskRunResponse])
async def list_runs(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_run(item) for item in await OrchestrationService(db).list_task_runs(current_user, project_id)]


@router.get("/runs/{run_id}", response_model=TaskRunResponse)
async def get_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).get_run(current_user, run_id))


@router.get("/runs/{run_id}/cost", response_model=RunCostSummaryResponse)
async def get_run_cost_summary(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).get_run_cost_summary(current_user, run_id)
    return RunCostSummaryResponse(**payload)


@router.get("/runs/{run_id}/events", response_model=list[RunEventResponse])
async def list_run_events(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_event(item) for item in await OrchestrationService(db).list_run_events(current_user, run_id)]


@router.get("/runs/{run_id}/execution-state", response_model=RunExecutionSnapshotResponse)
async def get_run_execution_state(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    raw = await OrchestrationService(db).get_run_execution_snapshot(current_user, run_id)
    return _run_execution_snapshot(raw)


@router.get("/runs/{run_id}/working-memory", response_model=WorkingMemoryResponse)
async def get_run_working_memory(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    wm = await OrchestrationService(db).get_working_memory(current_user, run_id)
    return _working_memory_payload(wm)


@router.patch("/runs/{run_id}/working-memory", response_model=WorkingMemoryResponse)
async def patch_run_working_memory(
    run_id: str,
    payload: WorkingMemoryPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    merged = await OrchestrationService(db).patch_working_memory(
        current_user,
        run_id,
        payload.model_dump(exclude_unset=True),
    )
    return _working_memory_payload(merged)


@router.get("/runs/{run_id}/stream")
async def stream_run_events(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    await service.get_run(current_user, run_id)

    async def event_stream():
        last_seen_at = None
        terminal = {"completed", "failed", "cancelled", "blocked"}
        idle_loops = 0
        for _ in range(2400):  # up to 10 minutes at 250ms cadence
            events = await service.repo.list_run_events_since(run_id, created_after=last_seen_at)
            if events:
                idle_loops = 0
            for item in events:
                last_seen_at = item.created_at
                yield "event: run_event\n" f"data: {_event(item).model_dump_json()}\n\n"
            run_obj = await service.repo.get_run(current_user.id, run_id)
            if run_obj and run_obj.status in terminal:
                yield f"event: stream_end\ndata: {json.dumps({'event_type': 'stream_end', 'status': run_obj.status})}\n\n"
                return
            idle_loops += 1
            if idle_loops % 20 == 0:
                yield "event: heartbeat\ndata: {}\n\n"
            await asyncio.sleep(0.25)

    return StreamingResponse(event_stream(), media_type="text/event-stream")


@router.post("/runs/{run_id}/cancel", response_model=TaskRunResponse)
async def cancel_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).cancel_run(current_user, run_id))


@router.post("/runs/{run_id}/resume", response_model=TaskRunResponse)
async def resume_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).resume_run(current_user, run_id))


@router.get("/runs/{run_id}/durable-workflow")
async def get_run_durable_workflow(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).get_run_durable_workflow(current_user, run_id)


@router.post("/runs/{run_id}/signals")
async def send_run_workflow_signal(
    run_id: str,
    payload: WorkflowSignalRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).signal_run_workflow(
        current_user,
        run_id,
        payload.signal_name,
        payload.payload,
    )


@router.post("/runs/{run_id}/retry", response_model=TaskRunResponse)
async def retry_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).retry_run(current_user, run_id))


@router.post("/runs/{run_id}/replay", response_model=TaskRunResponse, status_code=201)
async def replay_run(
    run_id: str,
    payload: ReplayRunRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(
        await OrchestrationService(db).replay_run(
            current_user,
            run_id,
            payload.from_event_index,
            model_name=payload.model_name,
        )
    )


@router.get("/github/sync-events/stream")
async def github_sync_events_stream(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return await _live_snapshot_stream(lambda: service.github_live_snapshot(current_user, project_id))


@router.post("/github/sync-events/{sync_event_id}/replay")
async def replay_github_sync_event(
    sync_event_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).replay_github_sync_event(
        current_user,
        sync_event_id,
        force=bool(payload.get("force")),
    )
    return _github_sync_event(item)


@router.get("/analytics/cost", response_model=CostAggregationResponse)
async def cost_analytics(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).aggregate_cost_analytics(current_user, days)
    return CostAggregationResponse(**payload)


@router.get("/analytics/execution-insights", response_model=ExecutionInsightsResponse)
async def execution_insights(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).execution_insights(current_user, days)
    return ExecutionInsightsResponse(**payload)


@router.get("/analytics/agent-performance")
async def agent_performance(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).agent_performance_scorecard(current_user, days)


@router.get("/analytics/budget-projection")
async def budget_projection(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).project_budget_projection(current_user, days)


@router.post("/agents/{agent_id}/simulate")
async def simulate_agent(
    agent_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    scenarios = payload.get("scenarios") if isinstance(payload, dict) else None
    return await OrchestrationService(db).run_agent_simulation(current_user, agent_id, scenarios=scenarios)


@router.post("/projects/bootstrap-from-text")
async def bootstrap_project_from_text(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).bootstrap_project_from_text(current_user, str(payload.get("prompt") or ""))


@router.post("/projects/bootstrap-apply", response_model=ProjectResponse, status_code=201)
async def bootstrap_apply_project(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project(await OrchestrationService(db).apply_bootstrap_project(current_user, payload))


@router.get("/runs/{run_id}/explanation")
async def explain_run(
    run_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).explain_run(current_user, run_id)


@router.get("/projects/{project_id}/workflow-templates/custom")
async def list_custom_workflow_templates(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).list_custom_workflow_templates(current_user, project_id)


@router.post("/projects/{project_id}/workflow-templates/custom")
async def save_custom_workflow_template(
    project_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).save_custom_workflow_template(current_user, project_id, payload)


@router.get("/skills/marketplace")
async def list_skill_marketplace(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).list_skill_marketplace(current_user)


@router.post("/agents/{agent_id}/skills/pins", response_model=AgentResponse)
async def pin_agent_skills(
    agent_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _agent(await OrchestrationService(db).pin_agent_skills(current_user, agent_id, payload))


@router.get("/projects/{project_id}/schedules")
async def list_agent_schedules(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).list_agent_schedules(current_user, project_id)


@router.post("/projects/{project_id}/schedules")
async def save_agent_schedule(
    project_id: str,
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).save_agent_schedule(current_user, project_id, payload)


@router.post("/projects/{project_id}/evals/cross-project-dependencies")
async def cross_project_dependencies(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    tasks = await OrchestrationService(db).list_tasks(current_user, project_id)
    edges = []
    for task in tasks:
        for dep in (task.metadata_json or {}).get("external_dependencies", []):
            edges.append({"task_id": task.id, "blocked_by": dep})
    return {"project_id": project_id, "edges": edges}


@router.get("/workflow-templates", response_model=list[WorkflowTemplateResponse])
async def list_workflow_templates(current_user: User = Depends(get_current_user)):
    _ = current_user
    return [WorkflowTemplateResponse(**item) for item in BUILTIN_WORKFLOW_TEMPLATES]


@router.get("/providers", response_model=list[ProviderConfigResponse])
async def list_providers(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_provider(item) for item in await OrchestrationService(db).list_providers(current_user, project_id)]


@router.post("/providers", response_model=ProviderConfigResponse, status_code=201)
async def create_provider(
    payload: ProviderConfigCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _provider(await OrchestrationService(db).create_provider(current_user, payload.model_dump()))


@router.patch("/providers/{provider_id}", response_model=ProviderConfigResponse)
async def update_provider(
    provider_id: str,
    payload: ProviderConfigUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _provider(await OrchestrationService(db).update_provider(current_user, provider_id, payload.model_dump(exclude_unset=True)))


@router.post("/providers/{provider_id}/test")
async def test_provider_connection(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).test_provider(current_user, provider_id)


@router.get("/providers/{provider_id}/models", response_model=ProviderModelListResponse)
async def list_provider_models(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).list_provider_models_for_user(current_user, provider_id)


@router.get("/providers/model-capabilities", response_model=list[ModelCapabilityResponse])
async def list_model_capabilities(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    _ = current_user
    return [_model_capability(item) for item in await OrchestrationService(db).list_model_capabilities()]


@router.post("/providers/compare", response_model=ProviderCompareResponse)
async def compare_provider_outputs(
    payload: ProviderCompareRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).compare_providers(current_user, payload.model_dump())


@router.get("/brainstorms", response_model=list[BrainstormResponse])
async def list_brainstorms(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_brainstorm(item) for item in await OrchestrationService(db).list_brainstorms(current_user, project_id)]


@router.post("/brainstorms", response_model=BrainstormResponse, status_code=201)
async def create_brainstorm(
    payload: BrainstormCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _brainstorm(await OrchestrationService(db).create_brainstorm(current_user, payload.model_dump()))


@router.get("/brainstorms/{brainstorm_id}", response_model=BrainstormResponse)
async def get_brainstorm(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _brainstorm(await OrchestrationService(db).get_brainstorm(current_user, brainstorm_id))


@router.get("/brainstorms/{brainstorm_id}/participants", response_model=list[BrainstormParticipantResponse])
async def list_brainstorm_participants(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_brainstorm_participant(item) for item in await OrchestrationService(db).list_brainstorm_participants(current_user, brainstorm_id)]


@router.get("/brainstorms/{brainstorm_id}/messages", response_model=list[BrainstormMessageResponse])
async def list_brainstorm_messages(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_brainstorm_message(item) for item in await OrchestrationService(db).list_brainstorm_messages(current_user, brainstorm_id)]


@router.get("/brainstorms/{brainstorm_id}/discourse-insights", response_model=BrainstormDiscourseInsightsResponse)
async def brainstorm_discourse_insights(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await OrchestrationService(db).brainstorm_discourse_insights(current_user, brainstorm_id)
    return BrainstormDiscourseInsightsResponse(**data)


@router.post("/brainstorms/{brainstorm_id}/start", response_model=TaskRunResponse)
async def start_brainstorm(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).start_brainstorm(current_user, brainstorm_id))


@router.post("/brainstorms/{brainstorm_id}/next-round", response_model=TaskRunResponse)
async def start_brainstorm_next_round(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _run(await OrchestrationService(db).start_brainstorm(current_user, brainstorm_id))


@router.post("/brainstorms/{brainstorm_id}/force-summary", response_model=BrainstormResponse)
async def force_brainstorm_summary(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _brainstorm(await OrchestrationService(db).force_brainstorm_summary(current_user, brainstorm_id))


@router.post("/brainstorms/{brainstorm_id}/promote", response_model=list[TaskResponse])
async def promote_brainstorm(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    tasks = await service.promote_brainstorm_to_tasks(current_user, brainstorm_id)
    return await _tasks_to_responses(service, tasks)


@router.post("/brainstorms/{brainstorm_id}/promote-adr", response_model=ProjectDecisionResponse)
async def promote_brainstorm_adr(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _project_decision(await OrchestrationService(db).promote_brainstorm_to_adr(current_user, brainstorm_id))


@router.post("/brainstorms/{brainstorm_id}/promote-document", response_model=ProjectDocumentResponse)
async def promote_brainstorm_document(
    brainstorm_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _document(await OrchestrationService(db).promote_brainstorm_to_document(current_user, brainstorm_id))


@public_router.post("/webhooks/incidents")
async def incident_webhook(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
):
    user_id = payload.get("user_id")
    if not user_id:
        return JSONResponse(status_code=422, content={"detail": "user_id is required"})
    user = await db.get(User, str(user_id))
    if not user:
        return JSONResponse(status_code=404, content={"detail": "User not found"})
    task = await OrchestrationService(db).ingest_incident_alert(user, payload)
    return {"accepted": True, "task_id": task.id}


@router.post("/pr-assistant/review")
async def pr_assistant_review(
    payload: dict[str, Any],
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).pr_assistant_review(current_user, payload)


@router.get("/approvals", response_model=list[ApprovalResponse])
async def list_approvals(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_approval(item) for item in await OrchestrationService(db).list_approvals(current_user)]


@router.post("/approvals/{approval_id}", response_model=ApprovalResponse)
async def decide_approval(
    approval_id: str,
    payload: ApprovalDecision,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _approval(await OrchestrationService(db).decide_approval(current_user, approval_id, payload.status, payload.reason))


@router.get("/approvals/pending-count")
async def pending_approvals_count(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    count = await OrchestrationService(db).get_pending_approvals_count(current_user)
    return {"count": count}


@router.get("/projects/{project_id}/documents", response_model=list[ProjectDocumentResponse])
async def list_documents(
    project_id: str,
    task_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [_document(item) for item in await OrchestrationService(db).list_documents(current_user, project_id, task_id)]


@router.post("/projects/{project_id}/documents", response_model=ProjectDocumentResponse, status_code=201)
async def upload_document(
    project_id: str,
    file: UploadFile = File(...),
    task_id: str | None = Form(default=None),
    ttl_days: int | None = Form(default=None),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return _document(
        await OrchestrationService(db).upload_document(
            current_user,
            project_id,
            task_id,
            file,
            ttl_days=ttl_days,
        )
    )


@router.delete("/projects/{project_id}/documents/{document_id}", status_code=204)
async def delete_document(
    project_id: str,
    document_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_document(current_user, project_id, document_id)
    return Response(status_code=204)


@router.get("/projects/{project_id}/knowledge", response_model=list[KnowledgeSearchResultResponse])
async def search_knowledge(
    project_id: str,
    q: str,
    task_id: str | None = None,
    top_k: int = 5,
    include_decisions: bool = Query(False),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).search_project_knowledge(
        current_user,
        project_id,
        q,
        task_id=task_id,
        top_k=top_k,
        include_decisions=include_decisions,
    )


@router.get("/projects/{project_id}/memory", response_model=list[AgentMemoryEntryResponse])
async def list_project_memory(
    project_id: str,
    agent_id: str | None = None,
    status: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        _memory(item)
        for item in await OrchestrationService(db).list_project_memory(
            current_user,
            project_id,
            agent_id=agent_id,
            status=status,
        )
    ]


@router.delete("/projects/{project_id}/memory/{memory_id}", status_code=204)
async def delete_project_memory(
    project_id: str,
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_memory_entry(current_user, project_id, memory_id)
    return Response(status_code=204)


@router.post("/projects/{project_id}/repositories/{repository_link_id}/index")
async def index_repository(
    project_id: str,
    repository_link_id: str,
    payload: dict[str, Any] = Body(default_factory=dict),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).index_project_repository(
        current_user, project_id, repository_link_id, payload
    )


@router.get("/projects/{project_id}/stream")
async def project_stream(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return await _live_snapshot_stream(lambda: service.project_live_snapshot(current_user, project_id))
