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
RunMode = Literal["single_agent", "manager_worker", "brainstorm", "review", "debate"]
BrainstormMode = Literal[
    "exploration",
    "solution_design",
    "code_review",
    "incident_triage",
    "root_cause",
    "architecture_proposal",
]
BrainstormOutputType = Literal["adr", "implementation_plan", "test_plan", "risk_register"]


class AgentMarkdownValidationResponse(BaseModel):
    valid: bool
    normalized: dict[str, Any] | None = None
    errors: list[str] = Field(default_factory=list)


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
    version: int
    created_at: datetime
    updated_at: datetime


class ProviderConfigCreate(RequestModel):
    project_id: str | None = None
    name: str = Field(min_length=2, max_length=255)
    provider_type: str = Field(min_length=2, max_length=64)
    base_url: str | None = None
    api_key: str | None = None
    organization: str | None = None
    default_model: str = Field(min_length=1, max_length=255)
    fallback_model: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int = Field(default=4096, ge=128, le=200000)
    timeout_seconds: int = Field(default=120, ge=5, le=3600)
    is_default: bool = False
    is_enabled: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderConfigUpdate(RequestModel):
    name: str | None = None
    base_url: str | None = None
    api_key: str | None = None
    organization: str | None = None
    default_model: str | None = None
    fallback_model: str | None = None
    temperature: float | None = Field(default=None, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=128, le=200000)
    timeout_seconds: int | None = Field(default=None, ge=5, le=3600)
    is_default: bool | None = None
    is_enabled: bool | None = None
    metadata: dict[str, Any] | None = None


class ProviderConfigResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    name: str
    provider_type: str
    base_url: str | None
    api_key_hint: str | None
    organization: str | None
    default_model: str
    fallback_model: str | None
    temperature: float
    max_tokens: int
    timeout_seconds: int
    is_default: bool
    is_enabled: bool
    metadata: dict[str, Any]
    last_healthcheck_status: str | None
    last_healthcheck_latency_ms: int | None
    is_healthy: bool
    last_healthcheck_at: datetime | None
    created_at: datetime
    updated_at: datetime


class ModelCapabilityResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_type: str
    model_slug: str
    display_name: str | None
    supports_tools: bool
    supports_vision: bool
    max_context_tokens: int
    cost_per_1k_input: float
    cost_per_1k_output: float
    metadata: dict[str, Any]
    is_active: bool
    created_at: datetime
    updated_at: datetime


class ProviderModelListResponse(BaseModel):
    provider_id: str
    provider_type: str
    models: list[dict[str, Any]] = Field(default_factory=list)


class ProviderCompareRequest(RequestModel):
    provider_a_id: str
    provider_b_id: str
    model_a: str | None = None
    model_b: str | None = None
    task_title: str = Field(min_length=2, max_length=255)
    task_description: str | None = None
    acceptance_criteria: str | None = None
    task_metadata: dict[str, Any] = Field(default_factory=dict)


class ProviderCompareResult(BaseModel):
    provider_id: str
    provider_name: str
    provider_type: str
    model_name: str
    latency_ms: int
    input_tokens: int
    output_tokens: int
    token_total: int
    estimated_cost_usd: float
    output_text: str
    is_healthy: bool


class ProviderCompareResponse(BaseModel):
    prompt_preview: str
    result_a: ProviderCompareResult
    result_b: ProviderCompareResult


class ProjectCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
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


class TaskCreate(RequestModel):
    title: str = Field(min_length=2, max_length=255)
    description: str | None = None
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
    acceptance_criteria: str | None = None
    assigned_agent_id: str | None = None
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
    result_summary: str | None = None
    result_payload: dict[str, Any] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class TaskUpdate(RequestModel):
    title: str | None = None
    description: str | None = None
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
    result_summary: str | None
    result_payload: dict[str, Any]
    position: int
    metadata: dict[str, Any]
    dependency_ids: list[str] = Field(default_factory=list)
    created_at: datetime
    updated_at: datetime


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


class RunEventTailItem(BaseModel):
    event_type: str
    level: str
    message: str
    created_at: datetime


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
    last_run_id: str | None
    focal_run_id: str | None
    checkpoint_excerpt: dict[str, Any]
    recent_events_tail: list[RunEventTailItem]


class RunExecutionSnapshotResponse(BaseModel):
    meta: ExecutionSnapshotMeta
    project_id: str
    run: TaskRunResponse
    task_id: str | None
    pending_approvals: list[PendingApprovalSummary]
    pending_github_sync: list[PendingGithubSyncSummary]
    checkpoint_excerpt: dict[str, Any]
    recent_events_tail: list[RunEventTailItem]


class WorkingMemoryResponse(BaseModel):
    """Run-scoped structured working set (Layer 2); persisted in ``checkpoint_json``."""

    schema_version: str = "1.0"
    objective: str = ""
    accepted_plan: str = ""
    latest_findings: str = ""
    temp_notes: str = ""
    open_questions: str = ""
    discussion_summary: str = ""
    artifact_refs: list[str] = Field(default_factory=list)
    updated_at: str


class WorkingMemoryPatch(RequestModel):
    objective: str | None = None
    accepted_plan: str | None = None
    latest_findings: str | None = None
    temp_notes: str | None = None
    open_questions: str | None = None
    discussion_summary: str | None = None
    artifact_refs: list[str] | None = None


class SemanticMemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    scope: str
    project_id: str | None
    agent_id: str | None
    entry_type: str
    namespace: str
    title: str
    body: str
    metadata: dict[str, Any]
    source_chunk_id: str | None
    source_task_id: str | None
    source_run_id: str | None
    provenance: dict[str, Any]
    created_by_user_id: str | None
    created_at: datetime
    updated_at: datetime


class SemanticMemoryEntryCreate(RequestModel):
    entry_type: str
    title: str = Field(min_length=1, max_length=255)
    body: str = Field(min_length=1)
    scope: str = "project"
    namespace: str | None = None
    agent_id: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    source_chunk_id: str | None = None
    source_task_id: str | None = None
    source_run_id: str | None = None
    provenance: dict[str, Any] = Field(default_factory=dict)


class SemanticMemoryEntryUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body: str | None = None
    entry_type: str | None = None
    namespace: str | None = None
    metadata: dict[str, Any] | None = None


class PromoteWorkingMemoryRequest(RequestModel):
    run_id: str
    entry_type: str = "note"
    title: str | None = Field(default=None, max_length=255)


class EpisodicSearchResponse(BaseModel):
    hits: list[dict[str, Any]]


class MemorySettingsResponse(BaseModel):
    auto_promote_decisions: bool
    auto_promote_approved_agent_memory: bool
    auto_ingest_bypasses_semantic_approval: bool
    second_stage_rag: bool
    semantic_write_requires_approval: bool
    episodic_retrieval_depth: int
    episodic_retention_days: int
    episodic_archive_enabled: bool
    episodic_delete_index_after_archive: bool
    task_close_auto_promote_working_memory: bool
    enable_semantic_vector_search: bool
    enable_episodic_vector_search: bool
    deep_recall_mode: bool
    deep_recall_episodic_candidates: int
    classifier_worker_enabled: bool


class MemorySettingsPatch(RequestModel):
    auto_promote_decisions: bool | None = None
    auto_promote_approved_agent_memory: bool | None = None
    auto_ingest_bypasses_semantic_approval: bool | None = None
    second_stage_rag: bool | None = None
    semantic_write_requires_approval: bool | None = None
    episodic_retrieval_depth: int | None = Field(default=None, ge=1, le=200)
    episodic_retention_days: int | None = Field(default=None, ge=1, le=3650)
    episodic_archive_enabled: bool | None = None
    episodic_delete_index_after_archive: bool | None = None
    task_close_auto_promote_working_memory: bool | None = None
    enable_semantic_vector_search: bool | None = None
    enable_episodic_vector_search: bool | None = None
    deep_recall_mode: bool | None = None
    deep_recall_episodic_candidates: int | None = Field(default=None, ge=4, le=200)
    classifier_worker_enabled: bool | None = None


class PendingSemanticWriteResponse(BaseModel):
    pending: bool = True
    approval_id: str
    approval_type: str = "semantic_memory_write"


class SemanticMergeRequest(RequestModel):
    canonical_entry_id: str
    merge_entry_ids: list[str] = Field(min_length=1)
    link_relation: str = "supersedes"


class SemanticMemoryLinkCreate(RequestModel):
    from_entry_id: str
    to_entry_id: str
    relation_type: str = Field(min_length=1, max_length=64)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SemanticMemoryLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    project_id: str
    from_entry_id: str
    to_entry_id: str
    relation_type: str
    metadata: dict[str, Any]
    created_at: datetime


class EpisodicArchiveManifestResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    object_key: str
    period_start: datetime
    period_end: datetime
    record_count: int
    byte_size: int
    stats_json: dict[str, Any]
    created_at: datetime


class ProceduralPlaybookResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    project_id: str
    slug: str
    title: str
    body_md: str
    version: int
    tags: list[Any]
    namespace: str
    created_at: datetime
    updated_at: datetime


class ProceduralPlaybookCreate(RequestModel):
    slug: str = Field(min_length=1, max_length=128)
    title: str = Field(min_length=1, max_length=255)
    body_md: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    namespace: str | None = None


class ProceduralPlaybookUpdate(RequestModel):
    title: str | None = Field(default=None, min_length=1, max_length=255)
    body_md: str | None = None
    tags: list[str] | None = None
    namespace: str | None = None
    version: int | None = None


class TaskMemoryCoordinationResponse(BaseModel):
    shared: str
    private: dict[str, str]


class TaskMemoryCoordinationPatch(RequestModel):
    shared: str | None = None
    private: dict[str, str] | None = None


class SemanticConflictGroupResponse(BaseModel):
    group_key: str
    entries: list[dict[str, Any]]


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


class BrainstormCreate(RequestModel):
    project_id: str
    task_id: str | None = None
    moderator_agent_id: str | None = None
    topic: str = Field(min_length=3, max_length=255)
    participant_agent_ids: list[str] = Field(default_factory=list)
    mode: BrainstormMode = "exploration"
    output_type: BrainstormOutputType = "implementation_plan"
    max_rounds: int = Field(default=3, ge=1, le=10)
    max_cost_usd: float = Field(default=10, ge=0.1, le=1000)
    max_repetition_score: float = Field(default=0.92, ge=0.1, le=1.0)
    stop_conditions: dict[str, Any] = Field(default_factory=dict)


class BrainstormResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    initiator_user_id: str
    moderator_agent_id: str | None
    topic: str
    status: str
    mode: str
    output_type: str
    max_rounds: int
    stop_conditions: dict[str, Any]
    participant_count: int = 0
    current_round: int = 0
    consensus_status: str = "open"
    latest_round_summary: str | None = None
    summary: str | None
    final_recommendation: str | None
    decision_log: list[dict[str, Any]]
    created_at: datetime
    updated_at: datetime


class BrainstormParticipantResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brainstorm_id: str
    agent_id: str
    order_index: int
    stance: str | None
    created_at: datetime


class BrainstormMessageResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    brainstorm_id: str
    agent_id: str | None
    round_number: int
    message_type: str
    content: str
    metadata: dict[str, Any]
    created_at: datetime


class GithubConnectionCreate(RequestModel):
    name: str = Field(min_length=2, max_length=255)
    api_url: str = "https://api.github.com"
    token: str | None = None


class GithubConnectionResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    name: str
    api_url: str
    connection_mode: str = "token"
    installation_id: int | None = None
    organization_login: str | None = None
    token_hint: str | None
    account_login: str | None
    is_active: bool
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GithubRepositoryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    connection_id: str
    project_id: str | None
    owner_name: str
    repo_name: str
    full_name: str
    default_branch: str | None
    repo_url: str | None
    is_active: bool
    metadata: dict[str, Any]
    last_synced_at: datetime | None
    created_at: datetime


class GithubIssueImportRequest(RequestModel):
    project_id: str
    repository_id: str
    issue_numbers: list[int] = Field(default_factory=list)
    auto_assign_agent_id: str | None = None


class GithubIssueLinkResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str
    task_id: str | None
    issue_number: int
    title: str
    body: str | None
    state: str
    labels: list[str]
    assignee_login: str | None
    issue_url: str | None
    sync_status: str
    last_comment_posted_at: datetime | None
    last_synced_at: datetime | None
    last_error: str | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class GithubSyncEventResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    repository_id: str | None
    issue_link_id: str | None
    action: str
    status: str
    detail: str | None
    payload: dict[str, Any]
    created_at: datetime


class GithubCommentRequest(RequestModel):
    body: str = Field(min_length=1)
    close_issue: bool = False


class GithubAppInstallResponse(BaseModel):
    install_url: str


class GithubWebhookResponse(BaseModel):
    accepted: bool = True
    sync_event_id: str | None = None


class ApprovalDecision(RequestModel):
    status: Literal["approved", "rejected"]
    reason: str | None = None


class ApprovalResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str | None
    task_id: str | None
    run_id: str | None
    issue_link_id: str | None
    requested_by_user_id: str | None
    approved_by_user_id: str | None
    approval_type: str
    status: str
    reason: str | None
    payload: dict[str, Any]
    created_at: datetime
    resolved_at: datetime | None


class ProjectDocumentResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    uploaded_by_user_id: str
    filename: str
    content_type: str
    source_text: str
    object_key: str | None
    size_bytes: int
    summary_text: str | None
    ingestion_status: str
    chunk_count: int
    ttl_days: int | None
    expires_at: datetime | None
    deleted_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class KnowledgeSearchResultResponse(BaseModel):
    hit_kind: Literal["chunk", "decision"] = "chunk"
    document_id: str
    chunk_id: str
    filename: str
    chunk_index: int
    score: float
    content: str
    metadata: dict[str, Any] = Field(default_factory=dict)
    decision_id: str | None = None


class PortfolioProjectSummary(BaseModel):
    project_id: str
    name: str
    slug: str
    active_runs: int
    open_tasks: int
    repository_links: int


class ExecutionEventTypeCount(BaseModel):
    event_type: str
    count: int


class ToolFailureCount(BaseModel):
    tool: str
    count: int


class ExecutionInsightsResponse(BaseModel):
    since: datetime
    days: int
    by_event_type: list[ExecutionEventTypeCount]
    tool_failures_by_tool: list[ToolFailureCount] = Field(default_factory=list)
    reopen_events: int = 0
    brainstorm_round_summary_events: int = 0
    blocked_events: int = 0
    tool_call_failed_events: int = 0


class RuntimeInfoResponse(BaseModel):
    orchestration_offline_mode: bool
    orchestration_provider_failover: bool
    orchestration_use_langgraph: bool = False
    orchestration_durable_queue_backend: str = "celery"
    celery_queues: dict[str, str] = Field(
        default_factory=dict,
        description="Logical plane → Redis queue name (split workers; see ADR 0006).",
    )


class BrainstormDiscourseInsightsResponse(BaseModel):
    message_count: int
    same_agent_streak_ratio: float
    top_repeated_terms: list[str]
    rounds_with_messages: int
    last_round_repetition_score: float | None = None
    last_round_pairwise_min_similarity: float | None = None
    consensus_kind: str | None = None
    conflict_signal: bool | None = None


class TaskTimelineEntry(BaseModel):
    kind: Literal["comment", "github_sync"]
    id: str
    created_at: datetime
    title: str
    body: str | None = None
    detail: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class WorkflowTemplateResponse(BaseModel):
    id: str
    name: str
    description: str
    suggested_execution: dict[str, Any] = Field(default_factory=dict)


class AgentMemoryEntryResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    agent_id: str
    project_id: str | None
    source_run_id: str | None
    key: str
    value_text: str
    scope: str
    status: str
    approved_by_user_id: str | None
    ttl_days: int | None
    expires_at: datetime | None
    deleted_at: datetime | None
    metadata: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class OverviewResponse(BaseModel):
    projects: list[ProjectResponse]
    agents: list[AgentResponse]
    active_runs: list[TaskRunResponse]
    pending_approvals: list[ApprovalResponse]
    github_events: list[GithubSyncEventResponse]


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


class TaskDecomposeRequest(RequestModel):
    max_subtasks: int = Field(default=5, ge=1, le=10)
    context: str | None = None


class TaskDecomposeResponse(BaseModel):
    parent_task_id: str
    subtasks: list[dict[str, Any]]


class TaskAcceptanceCheckResponse(BaseModel):
    task_id: str
    passed: bool
    checks: list[dict[str, Any]]  # [{name, passed, detail}]


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


VALID_GATE_ACTIONS = frozenset([
    "post_to_github", "open_pr", "mark_complete",
    "write_memory", "use_expensive_model", "run_tool",
])

VALID_AUTONOMY_LEVELS = frozenset(["autonomous", "semi_autonomous", "assisted", "supervised"])


class GateConfigResponse(BaseModel):
    autonomy_level: str
    approval_gates: list[str]


class GateConfigUpdate(RequestModel):
    autonomy_level: str | None = None
    approval_gates: list[str] | None = None

    @field_validator("autonomy_level")
    @classmethod
    def _validate_autonomy(cls, v: str | None) -> str | None:
        if v is not None and v not in VALID_AUTONOMY_LEVELS:
            raise ValueError(f"autonomy_level must be one of {sorted(VALID_AUTONOMY_LEVELS)}")
        return v

    @field_validator("approval_gates")
    @classmethod
    def _validate_gates(cls, v: list[str] | None) -> list[str] | None:
        if v is not None:
            invalid = [g for g in v if g not in VALID_GATE_ACTIONS]
            if invalid:
                raise ValueError(f"Invalid gate actions: {invalid}. Valid: {sorted(VALID_GATE_ACTIONS)}")
        return v


class EvalRecordCreate(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    task_id: str | None = None
    agent_a_id: str | None = None
    agent_b_id: str | None = None
    model_a: str | None = None
    model_b: str | None = None


class EvalRecordUpdate(RequestModel):
    winner: str | None = None
    score_a: float | None = None
    score_b: float | None = None
    criteria_met_a: bool | None = None
    criteria_met_b: bool | None = None
    notes: str | None = None


class EvalRecordResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    project_id: str
    task_id: str | None
    name: str
    run_a_id: str | None
    run_b_id: str | None
    agent_a_id: str | None
    agent_b_id: str | None
    model_a: str | None
    model_b: str | None
    winner: str | None
    score_a: float | None
    score_b: float | None
    criteria_met_a: bool | None
    criteria_met_b: bool | None
    notes: str | None
    metadata_json: dict
    created_at: datetime
    updated_at: datetime


class CostAggregationResponse(BaseModel):
    period: str
    by_project: list[dict[str, Any]]
    by_agent: list[dict[str, Any]]
    by_provider: list[dict[str, Any]]
    most_expensive_runs: list[dict[str, Any]]
    total_cost_usd: float
    total_tokens: int
