from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel


class AgentMarkdownValidationResponse(BaseModel):
    valid: bool
    normalized: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    activation_ready: bool = False


class AgentLintSummary(BaseModel):
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    activation_ready: bool = False


class AgentResolvedProfile(BaseModel):
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    rules_markdown: str = ""
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    model_policy: dict[str, Any] = Field(default_factory=dict)


class AgentInheritancePreview(BaseModel):
    parent_template_slug: str | None = None
    inherited_fields: dict[str, Any] = Field(default_factory=dict)
    overridden_fields: dict[str, Any] = Field(default_factory=dict)
    effective: AgentResolvedProfile = Field(default_factory=AgentResolvedProfile)


class AgentCreate(RequestModel):
    project_id: str | None = None
    parent_agent_id: str | None = None
    reviewer_agent_id: str | None = None
    provider_config_id: str | None = None
    parent_template_slug: str | None = None
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None
    role: str = "specialist"
    system_prompt: str = ""
    mission_markdown: str = ""
    rules_markdown: str = ""
    output_contract_markdown: str = ""
    source_markdown: str = ""
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    visibility: str = "private"
    tags: list[str] = Field(default_factory=list)
    budget: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: int = Field(default=900, ge=10, le=14400)
    retry_limit: int = Field(default=1, ge=0, le=10)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    task_filters: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentUpdate(RequestModel):
    project_id: str | None = None
    parent_agent_id: str | None = None
    reviewer_agent_id: str | None = None
    provider_config_id: str | None = None
    parent_template_slug: str | None = None
    name: str | None = Field(default=None, min_length=2, max_length=255)
    slug: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    role: str | None = None
    system_prompt: str | None = None
    mission_markdown: str | None = None
    rules_markdown: str | None = None
    output_contract_markdown: str | None = None
    source_markdown: str | None = None
    capabilities: list[str] | None = None
    allowed_tools: list[str] | None = None
    skills: list[str] | None = None
    model_policy: dict[str, Any] | None = None
    visibility: str | None = None
    is_active: bool | None = None
    tags: list[str] | None = None
    budget: dict[str, Any] | None = None
    timeout_seconds: int | None = Field(default=None, ge=10, le=14400)
    retry_limit: int | None = Field(default=None, ge=0, le=10)
    memory_policy: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    task_filters: list[str] | None = None
    metadata: dict[str, Any] | None = None


class AgentVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    agent_profile_id: str
    version_number: int
    source_markdown: str
    snapshot_json: dict[str, Any]
    created_by_user_id: str | None
    created_at: datetime


class AgentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    parent_agent_id: str | None
    reviewer_agent_id: str | None
    provider_config_id: str | None
    parent_template_slug: str | None
    name: str
    slug: str
    description: str | None
    role: str
    system_prompt: str
    mission_markdown: str
    rules_markdown: str
    output_contract_markdown: str
    source_markdown: str
    capabilities: list[str]
    allowed_tools: list[str]
    skills: list[str]
    model_policy: dict[str, Any]
    visibility: str
    is_active: bool
    tags: list[str]
    budget: dict[str, Any]
    timeout_seconds: int
    retry_limit: int
    memory_policy: dict[str, Any]
    output_schema: dict[str, Any]
    inheritance: AgentInheritancePreview | None = None
    lint: AgentLintSummary | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    version: int
    created_at: datetime
    updated_at: datetime


class ProjectAgentMembershipCreate(RequestModel):
    agent_id: str
    role: str = "member"
    is_default_manager: bool = False


class ProjectAgentMembershipUpdate(RequestModel):
    role: str | None = None
    is_default_manager: bool | None = None


class ProjectAgentMembershipResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    agent_id: str
    role: str
    is_default_manager: bool
    created_at: datetime


class AgentTemplateResponse(BaseModel):
    id: str | None = None
    slug: str
    name: str
    role: str
    description: str
    parent_template_slug: str | None = None
    system_prompt: str | None = None
    mission_markdown: str | None = None
    rules_markdown: str | None = None
    output_contract_markdown: str | None = None
    capabilities: list[str]
    allowed_tools: list[str]
    tags: list[str]
    skills: list[str]
    model_policy: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any]
    memory_policy: dict[str, Any]
    output_schema: dict[str, Any]
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentFromTemplateRequest(RequestModel):
    project_id: str | None = None
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    provider_config_id: str | None = None
    parent_template_slug: str | None = None
    skills: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    budget: dict[str, Any] = Field(default_factory=dict)
    model_policy: dict[str, Any] = Field(default_factory=dict)


class AgentTestRunRequest(RequestModel):
    task_title: str = "Test task"
    task_description: str | None = None
    acceptance_criteria: str | None = None
    task_labels: list[str] = Field(default_factory=list)
    task_metadata: dict[str, Any] = Field(default_factory=dict)
    model_name: str | None = None
    provider_config_id: str | None = None


class AgentTestRunTraceEvent(BaseModel):
    step: str
    level: str = "info"
    message: str
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentTestRunResponse(BaseModel):
    agent_id: str
    agent_name: str
    model_used: str | None
    input_tokens: int
    output_tokens: int
    token_total: int
    latency_ms: int
    estimated_cost_usd: float
    output_text: str
    trace: list[AgentTestRunTraceEvent] = Field(default_factory=list)
    simulated_tool_results: list[dict[str, Any]] = Field(default_factory=list)
    inheritance: AgentInheritancePreview | None = None


class SkillPackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    slug: str
    name: str
    description: str | None
    capabilities: list[str]
    allowed_tools: list[str]
    rules_markdown: str
    tags: list[str]
