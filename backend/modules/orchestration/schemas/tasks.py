from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.github.schemas import GithubSyncEventResponse

from backend.modules.orchestration.schemas.common import *  # noqa: F403

class TaskCreate(RequestModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    objective: str | None = None
    source: str = "manual"
    task_type: str = "general"
    priority: TaskPriority = "normal"

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority_create(cls, value: object) -> object:
        if value == "medium":
            return "normal"
        return value

    status: TaskStatus = "backlog"
    risk_level: str = "medium"
    autonomy_level: str = "semi-autonomous"
    assignment_mode: str = "manual"
    acceptance_criteria: str | None = None
    assigned_agent_id: str | None = None
    human_assignee_id: str | None = None
    reviewer_agent_id: str | None = None
    dependency_ids: list[str] = Field(default_factory=list)
    due_date: datetime | None = None
    response_sla_hours: int | None = Field(
        default=None,
        ge=1,
        le=8760,
        description="Optional hours from task creation for SLA deadline when no due_date (combined with due_date as earliest of the two).",
    )
    labels: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    external_links: list[dict[str, Any]] = Field(default_factory=list)
    result_summary: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentWorkSessionCreate(RequestModel):
    agent_id: str | None = None
    repository_link_id: str | None = None
    acceptance_criteria: str | None = None
    risk_level: Literal["low", "medium", "high"] = "medium"
    required_tests: list[str] = Field(default_factory=list)


class AgentWorkSessionUpdate(RequestModel):
    status: Literal[
        "queued",
        "preparing_workspace",
        "analyzing",
        "planning",
        "editing",
        "testing",
        "review-ready",
        "blocked",
        "failed",
        "done",
    ]
    plan: str | None = None
    plan_status: str | None = None
    blocker: str | None = None
    summary: str | None = None
    artifacts: list[dict[str, Any]] | None = None


class AgentWorkSessionResponse(BaseModel):
    status: str
    agent_id: str | None = None
    repository_link_id: str | None = None
    local_repo: dict[str, Any] = Field(default_factory=dict)
    acceptance_criteria: str | None = None
    risk_level: str
    required_tests: list[str] = Field(default_factory=list)
    planning_gate_required: bool = False
    plan_status: str | None = None
    plan: str | None = None
    blocker: str | None = None
    summary: str | None = None
    quality_score: dict[str, Any] | None = None
    artifacts: list[dict[str, Any]] = Field(default_factory=list)
    created_by_user_id: str | None = None
    updated_by_user_id: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class AgentQualityScoreResponse(BaseModel):
    correctness: int
    test_coverage: int
    diff_size: int
    blast_radius: int
    confidence: int
    security_risk: int
    ux_impact: int


class TaskUpdate(RequestModel):
    title: str | None = None
    description: str | None = None
    objective: str | None = None
    source: str | None = None
    task_type: str | None = None
    priority: TaskPriority | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority_update(cls, value: object) -> object:
        if value == "medium":
            return "normal"
        return value

    status: TaskStatus | None = None
    risk_level: str | None = None
    autonomy_level: str | None = None
    assignment_mode: str | None = None
    acceptance_criteria: str | None = None
    assigned_agent_id: str | None = None
    human_assignee_id: str | None = None
    reviewer_agent_id: str | None = None
    dependency_ids: list[str] | None = None
    due_date: datetime | None = None
    response_sla_hours: int | None = Field(default=None, ge=1, le=8760)
    labels: list[str] | None = None
    required_tools: list[str] | None = None
    external_links: list[dict[str, Any]] | None = None
    result_summary: str | None = None
    result_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


class TaskCommentCreate(RequestModel):
    body: str = Field(min_length=1)


class TaskCommentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    author_user_id: str | None
    author_agent_id: str | None
    body: str
    created_at: datetime


class TaskArtifactResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    run_id: str | None
    kind: str
    title: str
    content: str | None
    metadata: dict[str, Any]
    created_at: datetime


class DagReadyTaskItem(BaseModel):
    id: str
    title: str
    status: str
    dependency_count: int


class TaskBlockerResponse(BaseModel):
    task_id: str
    can_start: bool
    blockers: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[dict[str, Any]] = Field(default_factory=list)


class DagParallelStartPayload(RequestModel):
    run_mode: RunMode = "single_agent"
    limit: int = Field(default=8, ge=1, le=24)
    task_ids: list[str] | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)


class DagParallelStartResult(BaseModel):
    started_run_ids: list[str]
    skipped_task_ids: list[str]
    messages: list[str]


class MergeResolveRunPayload(RequestModel):
    run_mode: RunMode = "single_agent"
    model_name: str | None = None
    input_payload: dict[str, Any] = Field(default_factory=dict)
    notes: str | None = None


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    created_by_user_id: str
    assigned_agent_id: str | None
    human_assignee_id: str | None = None
    reviewer_agent_id: str | None
    github_issue_link_id: str | None
    github_issue_number: int | None = None
    github_issue_url: str | None = None
    github_repository_full_name: str | None = None
    parent_task_id: str | None = None
    title: str
    description: str | None
    objective: str | None = None
    source: str
    task_type: str
    priority: str
    status: str
    risk_level: str = "medium"
    autonomy_level: str = "semi-autonomous"
    assignment_mode: str = "manual"
    acceptance_criteria: str | None
    due_date: datetime | None
    response_sla_hours: int | None = None
    labels: list[str]
    required_tools: list[str] = Field(default_factory=list)
    external_links: list[dict[str, Any]] = Field(default_factory=list)
    result_summary: str | None = None
    result_payload: dict[str, Any]
    position: int
    metadata: dict[str, Any]
    dependency_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


