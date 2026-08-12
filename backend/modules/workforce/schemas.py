"""Pydantic schemas for workforce domain APIs."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel

SkillScope = Literal["task", "project", "organization", "template", "global"]
SkillStatus = Literal["draft", "testing", "active", "deprecated", "archived"]
RiskLevel = Literal["low", "medium", "high", "critical"]


class DepartmentCreate(RequestModel):
    company_id: str
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    description: str | None = None
    parent_department_id: str | None = None
    default_knowledge_policy: dict[str, Any] = Field(default_factory=dict)
    default_tool_policy: dict[str, Any] = Field(default_factory=dict)
    default_model_policy: dict[str, Any] = Field(default_factory=dict)
    default_approval_policy: dict[str, Any] = Field(default_factory=dict)
    budget_policy: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class DepartmentUpdate(RequestModel):
    name: str | None = None
    description: str | None = None
    parent_department_id: str | None = None
    default_knowledge_policy: dict[str, Any] | None = None
    default_tool_policy: dict[str, Any] | None = None
    default_model_policy: dict[str, Any] | None = None
    default_approval_policy: dict[str, Any] | None = None
    budget_policy: dict[str, Any] | None = None
    metadata: dict[str, Any] | None = None
    is_archived: bool | None = None


class DepartmentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    company_id: str
    name: str
    slug: str
    description: str | None
    parent_department_id: str | None
    default_knowledge_policy_json: dict[str, Any] = Field(default_factory=dict)
    default_tool_policy_json: dict[str, Any] = Field(default_factory=dict)
    default_model_policy_json: dict[str, Any] = Field(default_factory=dict)
    default_approval_policy_json: dict[str, Any] = Field(default_factory=dict)
    budget_policy_json: dict[str, Any] = Field(default_factory=dict)
    metadata_json: dict[str, Any] = Field(default_factory=dict)
    is_archived: bool = False
    created_at: datetime
    updated_at: datetime


class SkillVersionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    skill_id: str
    version_number: int
    purpose: str = ""
    when_to_use: str = ""
    instructions_markdown: str = ""
    input_schema_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_json: dict[str, Any] = Field(default_factory=dict)
    capabilities_json: list[Any] = Field(default_factory=list)
    required_tools_json: list[Any] = Field(default_factory=list)
    knowledge_requirements_json: list[Any] = Field(default_factory=list)
    constraints_markdown: str = ""
    risk_level: str = "low"
    approval_policy_json: dict[str, Any] = Field(default_factory=dict)
    examples_json: list[Any] = Field(default_factory=list)
    evaluation_criteria_json: list[Any] = Field(default_factory=list)
    source_type: str = "manual"
    is_published: bool = False
    generated_by_model: str | None = None
    created_at: datetime


class SkillResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    company_id: str | None = None
    slug: str
    name: str
    description: str | None = None
    scope: str
    status: str
    current_version_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    legacy_skill_pack_id: str | None = None
    created_at: datetime
    updated_at: datetime
    current_version: SkillVersionResponse | None = None
    # Flattened current_version fields for UI consumers
    purpose: str = ""
    when_to_use: str = ""
    instructions: str = ""
    instructions_markdown: str = ""
    capabilities: list[Any] = Field(default_factory=list)
    tools: list[Any] = Field(default_factory=list)
    knowledge: list[Any] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    constraints: list[Any] = Field(default_factory=list)
    risk_level: str = "low"
    examples: list[Any] = Field(default_factory=list)
    evaluation_criteria: list[Any] = Field(default_factory=list)
    version: int = 0
    parent_skill_id: str | None = None


class SkillDraftCreate(RequestModel):
    name: str = ""
    slug: str = ""
    description: str = ""
    purpose: str = ""
    when_to_use: str = ""
    instructions_markdown: str = ""
    scope: SkillScope = "project"
    risk_level: RiskLevel = "low"
    source_type: str = "manual"
    source_task_id: str | None = None
    source_project_id: str | None = None
    company_id: str | None = None
    skill_id: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    knowledge_requirements: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    constraints_markdown: str = ""
    approval_policy: dict[str, Any] = Field(default_factory=dict)
    examples: list[Any] = Field(default_factory=list)
    evaluation_criteria: list[Any] = Field(default_factory=list)
    confidence: float | None = None
    generation_metadata: dict[str, Any] = Field(default_factory=dict)
    unmatched_sections: list[Any] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class SkillDraftUpdate(RequestModel):
    name: str | None = None
    slug: str | None = None
    description: str | None = None
    purpose: str | None = None
    when_to_use: str | None = None
    instructions_markdown: str | None = None
    scope: SkillScope | None = None
    risk_level: RiskLevel | None = None
    status: str | None = None
    capabilities: list[str] | None = None
    required_tools: list[str] | None = None
    knowledge_requirements: list[str] | None = None
    input_schema: dict[str, Any] | None = None
    output_schema: dict[str, Any] | None = None
    constraints_markdown: str | None = None
    approval_policy: dict[str, Any] | None = None
    examples: list[Any] | None = None
    evaluation_criteria: list[Any] | None = None


class SkillDraftResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    company_id: str | None = None
    skill_id: str | None = None
    source_type: str
    source_task_id: str | None = None
    source_project_id: str | None = None
    project_id: str | None = None
    status: str
    name: str
    slug: str
    description: str = ""
    purpose: str = ""
    when_to_use: str = ""
    instructions_markdown: str = ""
    instructions: str = ""
    scope: str
    risk_level: str
    capabilities_json: list[Any] = Field(default_factory=list)
    required_tools_json: list[Any] = Field(default_factory=list)
    knowledge_requirements_json: list[Any] = Field(default_factory=list)
    input_schema_json: dict[str, Any] = Field(default_factory=dict)
    output_schema_json: dict[str, Any] = Field(default_factory=dict)
    constraints_markdown: str = ""
    approval_policy_json: dict[str, Any] = Field(default_factory=dict)
    examples_json: list[Any] = Field(default_factory=list)
    evaluation_criteria_json: list[Any] = Field(default_factory=list)
    validation_errors_json: list[Any] = Field(default_factory=list)
    warnings_json: list[Any] = Field(default_factory=list)
    unmatched_sections_json: list[Any] = Field(default_factory=list)
    duplicate_matches_json: list[Any] = Field(default_factory=list)
    confidence: float | None = None
    generation_metadata_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    updated_at: datetime
    # FE-friendly aliases
    capabilities: list[Any] = Field(default_factory=list)
    tools: list[Any] = Field(default_factory=list)
    knowledge: list[Any] = Field(default_factory=list)
    inputs: dict[str, Any] = Field(default_factory=dict)
    outputs: dict[str, Any] = Field(default_factory=dict)
    constraints: list[Any] = Field(default_factory=list)
    examples: list[Any] = Field(default_factory=list)
    evaluation_criteria: list[Any] = Field(default_factory=list)
    validation_errors: list[Any] = Field(default_factory=list)
    validation_warnings: list[Any] = Field(default_factory=list)
    duplicate_matches: list[Any] = Field(default_factory=list)
    is_valid: bool = False


class SkillPromoteRequest(RequestModel):
    target_scope: SkillScope


class TaskAnalysisOutput(BaseModel):
    """Strict structured analyzer output — never free-form."""

    objective: str
    task_category: str
    required_capabilities: list[str] = Field(default_factory=list)
    required_skills: list[str] = Field(default_factory=list)
    required_tools: list[str] = Field(default_factory=list)
    knowledge_requirements: list[str] = Field(default_factory=list)
    expected_artifacts: list[str] = Field(default_factory=list)
    acceptance_criteria: list[str] = Field(default_factory=list)
    risk_level: RiskLevel = "medium"
    autonomy_recommendation: str = "semi-autonomous"
    review_requirements: list[str] = Field(default_factory=list)
    approval_requirements: list[str] = Field(default_factory=list)


class TaskRequirementResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    analysis_id: str
    task_id: str
    kind: str
    key: str
    label: str
    description: str = ""
    priority: str = "required"
    coverage_status: str = "missing"
    matched_skill_id: str | None = None
    match_score: float | None = None
    match_explanation: str | None = None


class TaskAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    task_id: str
    project_id: str
    analyzer_version: str
    model_name: str | None = None
    content_fingerprint: str
    objective: str
    task_category: str
    risk_level: str
    autonomy_recommendation: str
    required_capabilities_json: list[Any] = Field(default_factory=list)
    required_tools_json: list[Any] = Field(default_factory=list)
    knowledge_requirements_json: list[Any] = Field(default_factory=list)
    expected_artifacts_json: list[Any] = Field(default_factory=list)
    acceptance_criteria_json: list[Any] = Field(default_factory=list)
    review_requirements_json: list[Any] = Field(default_factory=list)
    approval_requirements_json: list[Any] = Field(default_factory=list)
    raw_output_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime
    requirements: list[TaskRequirementResponse] = Field(default_factory=list)


class SkillMatchResult(BaseModel):
    skill_id: str
    skill_slug: str
    skill_name: str
    score: float
    explanation: str
    matched_capabilities: list[str] = Field(default_factory=list)
    matched_tools: list[str] = Field(default_factory=list)
    capability_overlap: float = 0.0
    tool_overlap: float = 0.0
    scope_relevance: float = 0.0
    status_bonus: float = 0.0
    scope: str = "task"
    status: str = "active"


class GapDetectionResult(BaseModel):
    covered: list[dict[str, Any]] = Field(default_factory=list)
    partial: list[dict[str, Any]] = Field(default_factory=list)
    missing: list[dict[str, Any]] = Field(default_factory=list)
    matches: list[SkillMatchResult] = Field(default_factory=list)


class DuplicateMatch(BaseModel):
    skill_id: str
    skill_slug: str
    skill_name: str
    similarity: float
    reasons: list[str] = Field(default_factory=list)


class SkillGenerationOutput(BaseModel):
    name: str = ""
    slug: str = ""
    purpose: str = ""
    description: str = ""
    instructions: str = ""
    when_to_use: str = ""
    capabilities: list[str] = Field(default_factory=list)
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    required_tools: list[str] = Field(default_factory=list)
    knowledge_requirements: list[str] = Field(default_factory=list)
    constraints: str = ""
    risk: RiskLevel = "medium"
    approval_requirements: list[str] = Field(default_factory=list)
    examples: list[Any] = Field(default_factory=list)
    evaluation_criteria: list[Any] = Field(default_factory=list)
    recommended_scope: SkillScope = "project"
    confidence: float | None = None


class SkillGenerationBatchResult(BaseModel):
    """Batch result from generating multiple skill drafts for gaps."""

    drafts: list[dict[str, Any]] = Field(default_factory=list)
    duplicate_warnings: list[DuplicateMatch] = Field(default_factory=list)


class AgentMatchResult(BaseModel):
    agent_id: str
    agent_name: str
    score: float = Field(default=0.0, alias="coverage_score")
    coverage_score: float = 0.0
    explanation: str
    covered_capabilities: list[str] = Field(default_factory=list)
    matched_skills: list[str] = Field(default_factory=list)
    missing_capabilities: list[str] = Field(default_factory=list)
    effective_tools: list[str] = Field(default_factory=list)
    requested_but_unavailable_tools: list[str] = Field(default_factory=list)

    model_config = ConfigDict(populate_by_name=True)


class AgentAssemblyProposal(BaseModel):
    recommended_agents: list[str] = Field(default_factory=list)
    assembly_type: str = "single_agent"
    rationale: str = ""
    proposed_name: str = ""
    proposed_slug: str = ""
    skill_ids: list[str] = Field(default_factory=list)
    skill_slugs: list[str] = Field(default_factory=list)
    capabilities: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)


class ProjectAnalysisOutput(BaseModel):
    recommended_tasks: list[dict[str, Any]] = Field(default_factory=list)
    recommended_skills: list[dict[str, Any]] = Field(default_factory=list)
    recommended_agents: list[dict[str, Any]] = Field(default_factory=list)
    recommended_reviewers: list[dict[str, Any]] = Field(default_factory=list)
    recommended_workflow: dict[str, Any] = Field(default_factory=dict)


class ProjectAnalysisResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    analyzer_version: str
    model_name: str | None = None
    recommended_tasks_json: list[Any] = Field(default_factory=list)
    recommended_skills_json: list[Any] = Field(default_factory=list)
    recommended_agents_json: list[Any] = Field(default_factory=list)
    recommended_workflow_json: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class ToolDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    slug: str
    name: str
    description: str = ""
    provider_type: str = "native"
    tool_schema: dict[str, Any] = Field(default_factory=dict, validation_alias="schema_json")
    risk_level: str = "low"
    requires_approval: bool = False
    is_active: bool = True


class WorkflowDefinitionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    slug: str
    name: str
    description: str = ""
    category: str = "general"
    status: str = "draft"
    current_version_id: str | None = None
    is_template: bool = False
    created_at: datetime


class SkillUsageResponse(BaseModel):
    skill_id: str
    skill_version_id: str | None = None
    run_count: int = 0
    success_count: int = 0
    human_accept_count: int = 0
    success_rate: float = 0.0
    avg_latency_ms: float | None = None
    avg_cost_usd: float | None = None
    retry_rate: float = 0.0
    last_used_at: datetime | None = None
    promotion_recommendation: str | None = None


class SkillImproveRequest(RequestModel):
    feedback: str = ""
    evaluation_id: str | None = None


class AssembleAgentRequest(RequestModel):
    name: str | None = None
    slug: str | None = None
    assign_to_task: bool = True
    activate: bool = False
