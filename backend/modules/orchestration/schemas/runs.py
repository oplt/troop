from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.common import *  # noqa: F403

class TaskAssignmentRequest(RequestModel):
    """Explicit assignment contract used by board drag-and-drop actions."""

    assigned_agent_id: str | None = None
    source: Literal["drag_drop", "manual"] = "drag_drop"


class TaskRunCreate(RequestModel):
    run_mode: RunMode = "single_agent"
    orchestrator_agent_id: str | None = None
    worker_agent_id: str | None = None
    reviewer_agent_id: str | None = None
    provider_config_id: str | None = None
    model_name: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)


class TaskRunResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    parent_run_id: str | None
    project_id: str
    task_id: str | None
    triggered_by_user_id: str | None
    orchestrator_agent_id: str | None
    worker_agent_id: str | None
    reviewer_agent_id: str | None
    provider_config_id: str | None
    brainstorm_id: str | None
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
    checkpoint_json: dict[str, Any]
    input_payload: dict[str, Any]
    output_payload: dict[str, Any]
    created_at: datetime
    started_at: datetime | None
    completed_at: datetime | None
    cancelled_at: datetime | None
    # Populated when a run is created (e.g. POST .../runs); empty on later GETs unless re-serialized with context.
    startup_warnings: list[str] = Field(default_factory=list)


class RunCostSummaryResponse(BaseModel):
    run_id: str
    project_id: str
    status: str
    estimated_cost_usd: float
    event_cost_sum_usd: float
    token_input: int
    token_output: int
    token_total: int
    model_name: str | None


class ExecutionSnapshotMeta(BaseModel):
    schema_version: str
    execution_truth: str
    sources_read: list[str]


class ActiveRunSummary(BaseModel):
    id: str
    status: str
    run_mode: str
    attempt_number: int
    retry_count: int
    started_at: datetime | None
    created_at: datetime
    error_message: str | None


class PendingApprovalSummary(BaseModel):
    id: str
    approval_type: str
    run_id: str | None
    task_id: str | None
    reason: str | None
    created_at: datetime


class PendingGithubSyncSummary(BaseModel):
    id: str
    action: str
    status: str
    detail: str | None
    created_at: datetime


class ProjectLiveSnapshotResponse(BaseModel):
    project_id: str
    agent_counts: dict[str, int] = Field(default_factory=dict)
    resource_counts: dict[str, int] = Field(default_factory=dict)
    task_counts: dict[str, int] = Field(default_factory=dict)
    run_counts: dict[str, int] = Field(default_factory=dict)
    approval_counts: dict[str, int] = Field(default_factory=dict)
    sync_counts: dict[str, int] = Field(default_factory=dict)
    ingest_counts: dict[str, int] = Field(default_factory=dict)
    latest: dict[str, datetime | None] = Field(default_factory=dict)


class RunEventTailItem(BaseModel):
    event_type: str
    level: str
    message: str
    created_at: datetime


class RunTraceStep(BaseModel):
    step_id: str
    title: str
    actor: str
    status: str
    sequence: int
    started_at: str | None
    completed_at: str | None
    last_error: str | None
    is_current: bool
    resumable: bool
    attempts: int
    metadata: dict[str, Any]


class TaskExecutionSnapshotResponse(BaseModel):
    meta: ExecutionSnapshotMeta
    project_id: str
    task_id: str
    task_status: str
    task_title: str
    has_active_run: bool
    active_runs: list[ActiveRunSummary]
    pending_approvals: list[PendingApprovalSummary]
    pending_github_sync: list[PendingGithubSyncSummary]
    metadata_views: dict[str, Any]
    routing_explainability: dict[str, Any] = Field(default_factory=dict)
    acceptance_summary: dict[str, Any] = Field(default_factory=dict)
    execution_memory: dict[str, Any] = Field(default_factory=dict)
    changed_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    last_run_id: str | None
    focal_run_id: str | None
    checkpoint_excerpt: dict[str, Any]
    recent_events_tail: list[RunEventTailItem]
    trace: list[RunTraceStep] = Field(default_factory=list)
    durable_workflow: dict[str, Any] = Field(default_factory=dict)
    child_runs: list[TaskRunResponse] = Field(default_factory=list)
    blocker_queue: list[dict[str, Any]] = Field(default_factory=list)
    review_state: dict[str, Any] = Field(default_factory=dict)
    github_action_state: dict[str, Any] = Field(default_factory=dict)


class RunExecutionSnapshotResponse(BaseModel):
    meta: ExecutionSnapshotMeta
    project_id: str
    run: TaskRunResponse
    task_id: str | None
    pending_approvals: list[PendingApprovalSummary]
    pending_github_sync: list[PendingGithubSyncSummary]
    routing_explainability: dict[str, Any] = Field(default_factory=dict)
    execution_memory: dict[str, Any] = Field(default_factory=dict)
    changed_artifacts: list[dict[str, Any]] = Field(default_factory=list)
    checkpoint_excerpt: dict[str, Any]
    recent_events_tail: list[RunEventTailItem]
    trace: list[RunTraceStep] = Field(default_factory=list)
    durable_workflow: dict[str, Any] = Field(default_factory=dict)
    child_runs: list[TaskRunResponse] = Field(default_factory=list)
    blocker_queue: list[dict[str, Any]] = Field(default_factory=list)
    review_state: dict[str, Any] = Field(default_factory=dict)
    github_action_state: dict[str, Any] = Field(default_factory=dict)
    resumable: bool = False


class RunEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    run_id: str
    task_id: str | None
    level: str
    event_type: str
    message: str
    payload: dict[str, Any]
    input_tokens: int = 0
    output_tokens: int = 0
    cost_usd_micros: int = 0
    created_at: datetime

