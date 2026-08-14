from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.agents import AgentInheritancePreview
from backend.modules.orchestration.schemas.common import *  # noqa: F403


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
    permissions: str | dict[str, Any] | None = None
    escalation_path: str | None = None
    budget: dict[str, Any]
    memory_policy: dict[str, Any]
    output_schema: dict[str, Any]
    task_filters: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTemplateCreate(RequestModel):
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=2, max_length=255)
    role: str = "specialist"
    description: str = ""
    parent_template_slug: str | None = None
    system_prompt: str = ""
    mission_markdown: str = ""
    rules_markdown: str = ""
    output_contract_markdown: str = ""
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    skills: list[str] = Field(default_factory=list)
    model_policy: dict[str, Any] = Field(default_factory=dict)
    permissions: str | dict[str, Any] | None = None
    escalation_path: str | None = None
    budget: dict[str, Any] = Field(default_factory=dict)
    memory_policy: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    task_filters: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class AgentTemplateUpdate(RequestModel):
    slug: str | None = Field(
        default=None, min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$"
    )
    name: str | None = Field(default=None, min_length=2, max_length=255)
    role: str | None = None
    description: str | None = None
    parent_template_slug: str | None = None
    system_prompt: str | None = None
    mission_markdown: str | None = None
    rules_markdown: str | None = None
    output_contract_markdown: str | None = None
    capabilities: list[str] | None = None
    allowed_tools: list[str] | None = None
    tags: list[str] | None = None
    skills: list[str] | None = None
    model_policy: dict[str, Any] | None = None
    permissions: str | dict[str, Any] | None = None
    escalation_path: str | None = None
    budget: dict[str, Any] | None = None
    memory_policy: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    task_filters: list[str] | None = None
    metadata: dict[str, Any] | None = None


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
    permissions: str | dict[str, Any] | None = None
    escalation_path: str | None = None
    task_filters: list[str] = Field(default_factory=list)


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
