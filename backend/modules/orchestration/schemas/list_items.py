"""Thin list-row DTOs for paginated collection endpoints (DATA-001B)."""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field

LIST_MESSAGE_MAX_CHARS = 400


def truncate_list_text(value: str | None, *, max_chars: int = LIST_MESSAGE_MAX_CHARS) -> str | None:
    if value is None:
        return None
    text = value.strip()
    if len(text) <= max_chars:
        return text
    return text[:max_chars] + "…"


class TaskRunListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_run_id: str | None
    project_id: str
    task_id: str | None
    run_mode: str
    status: str
    model_name: str | None
    attempt_number: int
    token_input: int
    token_output: int
    token_total: int
    estimated_cost_micros: int
    latency_ms: int | None
    error_message: str | None
    retry_count: int
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None


class RunEventListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    task_id: str | None
    level: str
    event_type: str
    message: str
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_micros: int = 0
    created_at: datetime


class TaskListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    status: str
    priority: str
    task_type: str
    position: int
    assigned_agent_id: str | None
    human_assignee_id: str | None = None
    parent_task_id: str | None = None
    github_issue_number: int | None = None
    github_issue_url: str | None = None
    github_repository_full_name: str | None = None
    due_date: datetime | None
    labels: list[str] = Field(default_factory=list)
    dependency_ids: list[str] = Field(default_factory=list)
    has_result: bool = False
    created_at: datetime
    updated_at: datetime


class ApprovalListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    task_id: str | None
    run_id: str | None
    issue_link_id: str | None
    approval_type: str
    status: str
    reason: str | None
    effect_hash: str | None = None
    effect_version: int = 1
    expires_at: datetime | None = None
    created_at: datetime
    resolved_at: datetime | None


class ProjectListItem(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None
    status: str
    memory_scope: str
    company_id: str | None = None
    department_id: str | None = None
    created_at: datetime
    updated_at: datetime
