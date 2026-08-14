from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.common import *  # noqa: F403

class PortfolioProjectSummary(BaseModel):
    project_id: str
    name: str
    slug: str
    active_runs: int
    open_tasks: int
    repository_links: int


class PortfolioProjectControlPlane(BaseModel):
    project_id: str
    name: str
    slug: str
    manager: dict[str, Any] = Field(default_factory=dict)
    health: dict[str, Any] = Field(default_factory=dict)
    queue_depth: dict[str, int] = Field(default_factory=dict)
    cost_rollup: dict[str, Any] = Field(default_factory=dict)
    blocked_work: list[dict[str, Any]] = Field(default_factory=list)
    escalation_inbox: list[dict[str, Any]] = Field(default_factory=list)
    latest_run: dict[str, Any] | None = None
    execution_policy: dict[str, Any] = Field(default_factory=dict)


class PortfolioExecutionPolicyUpdate(RequestModel):
    routing_mode: str | None = None
    approval_policy: str | None = None
    repo_indexing_cadence: str | None = None
    cost_cap_usd: float | None = Field(default=None, ge=0)


class PortfolioExecutionPolicyResponse(BaseModel):
    routing_mode: str
    approval_policy: str
    repo_indexing_cadence: str
    cost_cap_usd: float


class OperatorHealthCard(BaseModel):
    key: str
    label: str
    status: str
    summary: str
    metrics: dict[str, Any] = Field(default_factory=dict)


class OperatorDashboardResponse(BaseModel):
    generated_at: datetime
    queue_health: dict[str, Any] = Field(default_factory=dict)
    webhook_lag: dict[str, Any] = Field(default_factory=dict)
    replay_backlog: dict[str, Any] = Field(default_factory=dict)
    stuck_runs: dict[str, Any] = Field(default_factory=dict)
    services: list[OperatorHealthCard] = Field(default_factory=list)


class PortfolioControlPlaneResponse(BaseModel):
    generated_at: datetime
    totals: dict[str, Any] = Field(default_factory=dict)
    execution_policy: PortfolioExecutionPolicyResponse
    operator_dashboard: OperatorDashboardResponse
    projects: list[PortfolioProjectControlPlane] = Field(default_factory=list)


class WorkflowSignalRequest(RequestModel):
    signal_name: str = Field(min_length=2, max_length=64)
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionEventTypeCount(BaseModel):
    event_type: str
    count: int


class ToolFailureCount(BaseModel):
    tool: str
    count: int


class ExecutionRollup(BaseModel):
    """A stable, privacy-safe aggregate used by observability screens."""

    id: str | None = None
    name: str
    runs: int = 0
    tokens: int = 0
    cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    retries: int = 0
    tool_failures: int = 0
    validation_failures: int = 0
    acceptance_rate: float | None = None


class ProviderHealthSummaryResponse(BaseModel):
    provider_id: str
    project_id: str | None = None
    name: str
    provider_type: str
    default_model: str
    enabled: bool
    status: str
    healthy: bool | None = None
    latency_ms: int | None = None
    last_checked_at: datetime | None = None
    error: str | None = None


class ExecutionInsightsResponse(BaseModel):
    since: datetime
    days: int
    by_event_type: list[ExecutionEventTypeCount]
    tool_failures_by_tool: list[ToolFailureCount] = Field(default_factory=list)
    reopen_events: int = 0
    brainstorm_round_summary_events: int = 0
    blocked_events: int = 0
    tool_call_failed_events: int = 0
    total_runs: int = 0
    completed_runs: int = 0
    failed_runs: int = 0
    total_tokens: int = 0
    total_cost_usd: float = 0.0
    avg_latency_ms: float = 0.0
    p95_latency_ms: float = 0.0
    retry_count: int = 0
    retry_rate: float = 0.0
    validation_failures: int = 0
    hallucination_failures: int = 0
    github_sync_events: int = 0
    github_sync_failures: int = 0
    discussion_rounds: int = 0
    discussion_loop_score: float | None = None
    discussion_loop_detected: int = 0
    acceptance_checks: int = 0
    accepted_after_review: int = 0
    acceptance_rate_after_review: float | None = None
    evaluation_records: int = 0
    by_project: list[ExecutionRollup] = Field(default_factory=list)
    by_agent: list[ExecutionRollup] = Field(default_factory=list)
    by_task: list[ExecutionRollup] = Field(default_factory=list)
    by_provider: list[ExecutionRollup] = Field(default_factory=list)


class RuntimeInfoResponse(BaseModel):
    orchestration_provider_failover: bool
    orchestration_durable_queue_backend: str = "celery"
    durable_signal_model: str = "checkpoint_signal_queue"
    durable_query_model: str = "checkpoint_query_snapshot"
    durable_backend: dict[str, Any] = Field(default_factory=dict)
    execution_topology: dict[str, Any] = Field(default_factory=dict)
    realtime_transport: dict[str, Any] = Field(default_factory=dict)
    celery_queues: dict[str, str] = Field(
        default_factory=dict,
        description="Logical plane → Redis queue name (split workers; see ADR 0006).",
    )
