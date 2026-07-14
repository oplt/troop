"""Transport presenters shared by REST, agent, and GraphQL adapters.

Presenters intentionally depend on response schemas, not routers.  This keeps
framework delivery code replaceable while preserving the existing response
contracts during the Phase 6 extraction.
"""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.hitl_policy import redact_approval_payload
from backend.modules.orchestration.schemas import (
    ActiveRunSummary,
    AgentInheritancePreview,
    AgentLintSummary,
    AgentResolvedProfile,
    AgentResponse,
    ExecutionSnapshotMeta,
    PendingApprovalSummary,
    PendingGithubSyncSummary,
    RunEventResponse,
    RunEventTailItem,
    RunExecutionSnapshotResponse,
    RunTraceStep,
    TaskExecutionSnapshotResponse,
    TaskResponse,
    TaskRunResponse,
)


def to_agent_response(item: Any) -> AgentResponse:
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
        permissions=(item.model_policy_json or {}).get("permissions"),
        escalation_path=(item.model_policy_json or {}).get("escalation_path"),
        visibility=item.visibility,
        is_active=item.is_active,
        tags=item.tags_json,
        budget=item.budget_json,
        timeout_seconds=item.timeout_seconds,
        retry_limit=item.retry_limit,
        memory_policy=item.memory_policy_json,
        output_schema=item.output_schema_json,
        task_filters=list((item.metadata_json or {}).get("task_filters") or []),
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


def to_task_response(
    item: Any,
    dependency_ids: list[str] | None = None,
    github_summary: dict[str, Any] | None = None,
) -> TaskResponse:
    gh_num = gh_url = gh_repo = None
    if github_summary:
        raw_number = github_summary.get("issue_number")
        gh_num = int(raw_number) if raw_number is not None else None
        issue_url = github_summary.get("issue_url")
        gh_url = str(issue_url) if issue_url else None
        repository_name = github_summary.get("repository_full_name")
        gh_repo = str(repository_name) if repository_name else None
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
        required_tools=list((item.metadata_json or {}).get("required_tools") or []),
        external_links=list((item.metadata_json or {}).get("external_links") or []),
        result_summary=item.result_summary,
        result_payload=item.result_payload_json,
        position=item.position,
        metadata=item.metadata_json,
        dependency_ids=list(dependency_ids or []),
        created_at=item.created_at,
        updated_at=item.updated_at,
    )


def to_run_response(item: Any, *, startup_warnings: list[str] | None = None) -> TaskRunResponse:
    return TaskRunResponse(
        id=item.id,
        parent_run_id=getattr(item, "parent_run_id", None),
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
        startup_warnings=list(startup_warnings or []),
    )


def to_event_response(item: Any) -> RunEventResponse:
    return RunEventResponse(
        id=item.id,
        run_id=item.run_id,
        task_id=item.task_id,
        level=item.level,
        event_type=item.event_type,
        message=item.message,
        payload=redact_approval_payload(item.payload_json),
        input_tokens=item.input_tokens,
        output_tokens=item.output_tokens,
        cost_usd_micros=item.cost_usd_micros,
        created_at=item.created_at,
    )


def to_task_execution_snapshot(raw: dict[str, Any]) -> TaskExecutionSnapshotResponse:
    return TaskExecutionSnapshotResponse(
        meta=ExecutionSnapshotMeta(**raw["meta"]),
        project_id=raw["project_id"],
        task_id=raw["task_id"],
        task_status=raw["task_status"],
        task_title=raw["task_title"],
        has_active_run=raw["has_active_run"],
        active_runs=[ActiveRunSummary(**item) for item in raw["active_runs"]],
        pending_approvals=[PendingApprovalSummary(**item) for item in raw["pending_approvals"]],
        pending_github_sync=[
            PendingGithubSyncSummary(**item) for item in raw["pending_github_sync"]
        ],
        metadata_views=raw["metadata_views"],
        routing_explainability=raw.get("routing_explainability") or {},
        acceptance_summary=raw.get("acceptance_summary") or {},
        execution_memory=raw.get("execution_memory") or {},
        changed_artifacts=raw.get("changed_artifacts") or [],
        last_run_id=raw["last_run_id"],
        focal_run_id=raw["focal_run_id"],
        checkpoint_excerpt=raw["checkpoint_excerpt"],
        recent_events_tail=[RunEventTailItem(**item) for item in raw["recent_events_tail"]],
        trace=[RunTraceStep(**item) for item in raw.get("trace", [])],
        durable_workflow=raw.get("durable_workflow") or {},
        child_runs=[to_run_response(item) for item in raw.get("child_runs") or []],
        blocker_queue=list(raw.get("blocker_queue") or []),
        review_state=dict(raw.get("review_state") or {}),
        github_action_state=dict(raw.get("github_action_state") or {}),
    )


def to_run_execution_snapshot(raw: dict[str, Any]) -> RunExecutionSnapshotResponse:
    return RunExecutionSnapshotResponse(
        meta=ExecutionSnapshotMeta(**raw["meta"]),
        project_id=raw["project_id"],
        run=to_run_response(raw["run"]),
        task_id=raw["task_id"],
        pending_approvals=[PendingApprovalSummary(**item) for item in raw["pending_approvals"]],
        pending_github_sync=[
            PendingGithubSyncSummary(**item) for item in raw["pending_github_sync"]
        ],
        routing_explainability=raw.get("routing_explainability") or {},
        execution_memory=raw.get("execution_memory") or {},
        changed_artifacts=raw.get("changed_artifacts") or [],
        checkpoint_excerpt=raw["checkpoint_excerpt"],
        recent_events_tail=[RunEventTailItem(**item) for item in raw["recent_events_tail"]],
        trace=[RunTraceStep(**item) for item in raw.get("trace", [])],
        durable_workflow=raw.get("durable_workflow") or {},
        child_runs=[to_run_response(item) for item in raw.get("child_runs") or []],
        blocker_queue=list(raw.get("blocker_queue") or []),
        review_state=dict(raw.get("review_state") or {}),
        github_action_state=dict(raw.get("github_action_state") or {}),
        resumable=bool(raw.get("resumable", False)),
    )


__all__ = [
    "to_agent_response",
    "to_event_response",
    "to_run_execution_snapshot",
    "to_run_response",
    "to_task_execution_snapshot",
    "to_task_response",
]
