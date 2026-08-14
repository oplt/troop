from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import (
    HierarchyExecutionMode,
    HierarchyRelationship,
    HierarchyRoutingMode,
)


def _coerce_null_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


class ProjectCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None
    status: str = "active"
    goals_markdown: str = ""
    settings: dict[str, Any] = Field(default_factory=dict)
    memory_scope: str = "project"
    knowledge_summary: str | None = None
    company_id: str | None = None
    department_id: str | None = None
    knowledge_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProjectUpdate(RequestModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    status: str | None = None
    goals_markdown: str | None = None
    settings: dict[str, Any] | None = None
    memory_scope: str | None = None
    knowledge_summary: str | None = None
    department_id: str | None = None
    knowledge_policy: dict[str, Any] | None = None
    budget: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None


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
    company_id: str | None = None
    department_id: str | None = None
    knowledge_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime

    @field_validator("settings", "knowledge_policy", "budget", "metadata", mode="before")
    @classmethod
    def coerce_null_json_dicts(cls, value: Any) -> dict[str, Any]:
        return _coerce_null_dict(value)


class HierarchyEdge(BaseModel):
    source_agent_id: str
    target_agent_id: str
    relationship: HierarchyRelationship = "delegates_to"


class HierarchyPolicyUpdate(RequestModel):
    manager_agent_id: str | None = None
    edges: list[HierarchyEdge] = Field(default_factory=list)
    delegation_rules: dict[str, list[str]] = Field(default_factory=dict)
    brainstorm_rules: dict[str, list[str]] = Field(default_factory=dict)
    reviewer_agent_ids: list[str] = Field(default_factory=list)
    reviewer_chain_mode: str = "sequential"
    routing_mode: HierarchyRoutingMode = "capability_based"
    sibling_load_balance: str = "queue_depth"
    default_execution_mode: HierarchyExecutionMode = "single_agent"
    blocked_handoff: dict[str, Any] = Field(default_factory=dict)


class HierarchyPolicyResponse(HierarchyPolicyUpdate):
    final_authority: str = "human_user"
    validation_errors: list[str] = Field(default_factory=list)


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

    @field_validator("metadata", mode="before")
    @classmethod
    def coerce_null_metadata(cls, value: Any) -> dict[str, Any]:
        return _coerce_null_dict(value)


class LocalRepoWorkspacePayload(RequestModel):
    enabled: bool = True
    repo_path: str = Field(default="", max_length=2000)
    allowed_branches: list[str] = Field(default_factory=list)
    dirty_worktree_policy: Literal["block", "warn", "allow"] = "block"
    file_allowlist: list[str] = Field(default_factory=list)
    file_denylist: list[str] = Field(default_factory=list)
    max_diff_bytes: int = Field(default=200_000, ge=1_000, le=5_000_000)
    command_allowlist: list[str] = Field(default_factory=list)
    worktree_root: str | None = None


class LocalRepoWorkspaceResponse(BaseModel):
    valid: bool
    blocked_reasons: list[str] = Field(default_factory=list)
    workspace: dict[str, Any]
    branch: str | None = None
    dirty: bool | None = None
    status: str | None = None
    remotes: str | None = None
    last_commit: str | None = None
    diff_bytes: int | None = None
    inspected_at: str | None = None


class LocalRepoCommandRequest(RequestModel):
    command: str = Field(min_length=1, max_length=1000)
    cwd: str | None = None
    timeout_seconds: int = Field(default=60, ge=1, le=600)


class LocalRepoCommandResponse(BaseModel):
    command: str
    cwd: str
    exit_code: int
    stdout: str
    stderr: str
    duration_ms: int
    timed_out: bool = False


class LocalRepoReadFileResponse(BaseModel):
    path: str
    content: str
    truncated: bool = False


class LocalRepoWorktreeResponse(BaseModel):
    branch: str
    path: str
    base_repo_path: str
    created_at: str


class LocalRepoContextPackResponse(BaseModel):
    repo: dict[str, Any]
    issue_text: str
    acceptance_criteria: str | None = None
    tree: list[str]
    files: list[dict[str, Any]]
    constraints: dict[str, Any]
    created_at: str
