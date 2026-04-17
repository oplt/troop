from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel

TaskStatus = Literal[
    "backlog",
    "queued",
    "planned",
    "in_progress",
    "blocked",
    "needs_review",
    "approved",
    "completed",
    "failed",
    "synced_to_github",
    "archived",
]
TaskPriority = Literal["low", "normal", "high", "urgent"]


class ProjectCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\\-]*$")
    description: str | None = None
    status: str = "active"
    goals_markdown: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    memory_scope: str = "project"
    knowledge_summary: str | None = None


class ProjectUpdate(RequestModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    status: str | None = None
    goals_markdown: str | None = None
    settings: dict[str, Any] | None = None
    memory_scope: str | None = None
    knowledge_summary: str | None = None


class ProjectResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    slug: str
    description: str | None
    status: str
    goals_markdown: str
    settings: dict[str, Any]
    memory_scope: str
    knowledge_summary: str | None
    created_at: datetime
    updated_at: datetime


class ProjectRepositoryLinkCreate(RequestModel):
    github_repository_id: str | None = None
    provider: str = "github"
    owner_name: str = Field(min_length=1, max_length=255)
    repo_name: str = Field(min_length=1, max_length=255)
    full_name: str = Field(min_length=3, max_length=255)
    default_branch: str | None = None
    repository_url: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectRepositoryLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    github_repository_id: str | None
    provider: str
    owner_name: str
    repo_name: str
    full_name: str
    default_branch: str | None
    repository_url: str | None
    metadata: dict[str, Any]


class TaskCreate(RequestModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
    source: str = "manual"
    task_type: str = "general"
    priority: TaskPriority = "normal"
    status: TaskStatus = "backlog"
    acceptance_criteria: str | None = None
    assigned_agent_id: str | None = None
    reviewer_agent_id: str | None = None
    dependency_ids: list[str] = Field(default_factory=list)
    due_date: datetime | None = None
    response_sla_hours: int | None = Field(default=None, ge=1, le=8760)
    labels: list[str] = Field(default_factory=list)
    result_summary: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority_create(cls, value: object) -> object:
        if value == "medium":
            return "normal"
        return value


class TaskUpdate(RequestModel):
    title: str | None = None
    description: str | None = None
    source: str | None = None
    task_type: str | None = None
    priority: TaskPriority | None = None
    status: TaskStatus | None = None
    acceptance_criteria: str | None = None
    assigned_agent_id: str | None = None
    reviewer_agent_id: str | None = None
    dependency_ids: list[str] | None = None
    due_date: datetime | None = None
    response_sla_hours: int | None = Field(default=None, ge=1, le=8760)
    labels: list[str] | None = None
    result_summary: str | None = None
    result_payload: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None

    @field_validator("priority", mode="before")
    @classmethod
    def _normalize_priority_update(cls, value: object) -> object:
        if value == "medium":
            return "normal"
        return value


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


class TaskResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    created_by_user_id: str
    assigned_agent_id: str | None
    reviewer_agent_id: str | None
    github_issue_link_id: str | None
    github_issue_number: int | None = None
    github_issue_url: str | None = None
    github_repository_full_name: str | None = None
    parent_task_id: str | None = None
    title: str
    description: str | None
    source: str
    task_type: str
    priority: str
    status: str
    acceptance_criteria: str | None
    due_date: datetime | None
    response_sla_hours: int | None = None
    labels: list[str]
    result_summary: str | None = None
    result_payload: dict[str, Any]
    position: int
    metadata: dict[str, Any]
    dependency_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


class TaskDecomposeRequest(RequestModel):
    max_subtasks: int = Field(default=5, ge=1, le=10)
    context: str | None = None


class TaskDecomposeResponse(BaseModel):
    parent_task_id: str
    subtasks: list[dict[str, Any]]


class TaskAcceptanceCheckResponse(BaseModel):
    task_id: str
    passed: bool
    checks: list[dict[str, Any]]


class TaskArtifactCreate(RequestModel):
    kind: str = "summary"
    title: str = Field(min_length=1, max_length=255)
    content: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectMilestoneCreate(RequestModel):
    title: str = Field(min_length=1, max_length=255)
    description: str | None = None
    due_date: datetime | None = None
    status: str = "open"
    position: int = 0


class ProjectMilestoneUpdate(RequestModel):
    title: str | None = None
    description: str | None = None
    due_date: datetime | None = None
    status: str | None = None
    position: int | None = None


class ProjectMilestoneResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    title: str
    description: str | None
    due_date: datetime | None
    status: str
    position: int
    created_at: datetime
    updated_at: datetime


class ProjectDecisionCreate(RequestModel):
    title: str = Field(min_length=1, max_length=255)
    decision: str = Field(min_length=1)
    rationale: str | None = None
    author_label: str | None = None
    task_id: str | None = None
    brainstorm_id: str | None = None


class ProjectDecisionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    brainstorm_id: str | None
    title: str
    decision: str
    rationale: str | None
    author_label: str | None
    created_at: datetime


class PortfolioProjectSummary(BaseModel):
    project_id: str
    name: str
    slug: str
    active_runs: int
    open_tasks: int
    repository_links: int


class TaskTimelineEntry(BaseModel):
    kind: Literal["comment", "github_sync"]
    id: str
    created_at: datetime
    title: str
    body: str | None = None
    detail: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)
