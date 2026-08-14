"""SQLAlchemy load-only options for thin list queries (DATA-001B)."""

from __future__ import annotations

from sqlalchemy.orm import Load, load_only

from backend.modules.notifications.models import Notification
from backend.modules.orchestration.models import ApprovalRequest, RunEvent, TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


def task_run_list_load() -> Load:
    return load_only(
        TaskRun.id,
        TaskRun.parent_run_id,
        TaskRun.project_id,
        TaskRun.task_id,
        TaskRun.run_mode,
        TaskRun.status,
        TaskRun.model_name,
        TaskRun.attempt_number,
        TaskRun.token_input,
        TaskRun.token_output,
        TaskRun.token_total,
        TaskRun.estimated_cost_micros,
        TaskRun.latency_ms,
        TaskRun.error_message,
        TaskRun.retry_count,
        TaskRun.created_at,
        TaskRun.started_at,
        TaskRun.completed_at,
        TaskRun.cancelled_at,
    )


def run_event_list_load() -> Load:
    return load_only(
        RunEvent.id,
        RunEvent.run_id,
        RunEvent.task_id,
        RunEvent.level,
        RunEvent.event_type,
        RunEvent.message,
        RunEvent.input_tokens,
        RunEvent.output_tokens,
        RunEvent.cost_usd_micros,
        RunEvent.created_at,
    )


def task_list_load() -> Load:
    return load_only(
        OrchestratorTask.id,
        OrchestratorTask.project_id,
        OrchestratorTask.title,
        OrchestratorTask.status,
        OrchestratorTask.priority,
        OrchestratorTask.task_type,
        OrchestratorTask.position,
        OrchestratorTask.assigned_agent_id,
        OrchestratorTask.human_assignee_id,
        OrchestratorTask.parent_task_id,
        OrchestratorTask.github_issue_link_id,
        OrchestratorTask.due_date,
        OrchestratorTask.labels_json,
        OrchestratorTask.result_summary,
        OrchestratorTask.created_at,
        OrchestratorTask.updated_at,
    )


def approval_list_load() -> Load:
    return load_only(
        ApprovalRequest.id,
        ApprovalRequest.project_id,
        ApprovalRequest.task_id,
        ApprovalRequest.run_id,
        ApprovalRequest.issue_link_id,
        ApprovalRequest.approval_type,
        ApprovalRequest.status,
        ApprovalRequest.reason,
        ApprovalRequest.effect_hash,
        ApprovalRequest.effect_version,
        ApprovalRequest.expires_at,
        ApprovalRequest.created_at,
        ApprovalRequest.resolved_at,
    )


def notification_list_load() -> Load:
    return load_only(
        Notification.id,
        Notification.type,
        Notification.title,
        Notification.body,
        Notification.is_read,
        Notification.created_at,
    )


def project_list_load() -> Load:
    return load_only(
        OrchestratorProject.id,
        OrchestratorProject.name,
        OrchestratorProject.slug,
        OrchestratorProject.description,
        OrchestratorProject.status,
        OrchestratorProject.memory_scope,
        OrchestratorProject.company_id,
        OrchestratorProject.department_id,
        OrchestratorProject.created_at,
        OrchestratorProject.updated_at,
    )
