from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, Float, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.modules.github.models import (
    GithubConnection,
    GithubIssueLink,
    GithubRepository,
    GithubSyncEvent,
)
from backend.modules.memory.models import (
    AgentMemoryEntry,
    EpisodicArchiveManifest,
    EpisodicSearchIndex,
    MemoryIngestJob,
    ProceduralPlaybook,
    ProjectDocument,
    ProjectDocumentChunk,
    SemanticMemoryEntry,
    SemanticMemoryLink,
)
from backend.modules.orchestration.model_utils import (
    EMBEDDING_VECTOR_DIMENSIONS,
    normalize_embedding_for_vector,
    utcnow as _utcnow,
)
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
    ProjectDecision,
    ProjectMilestone,
    ProjectRepositoryLink,
    TaskArtifact,
    TaskComment,
    TaskDependency,
)
from backend.modules.team.models import (
    AgentProfile,
    AgentProfileVersion,
    AgentTemplateCatalog,
    ProjectAgentMembership,
    SkillPack,
    TeamTemplateCatalog,
)


class ProviderConfig(Base):
    __tablename__ = "provider_configs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    name: Mapped[str] = mapped_column(String(255))
    provider_type: Mapped[str] = mapped_column(String(64), default="openai_compatible")
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    encrypted_api_key: Mapped[str | None] = mapped_column(Text, nullable=True)
    api_key_hint: Mapped[str | None] = mapped_column(String(32), nullable=True)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    default_model: Mapped[str] = mapped_column(String(255), default="")
    fallback_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    temperature: Mapped[float] = mapped_column(Float, default=0.2)
    max_tokens: Mapped[int] = mapped_column(Integer, default=4096)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=120)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    last_healthcheck_status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    last_healthcheck_latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_healthy: Mapped[bool] = mapped_column(Boolean, default=False)
    last_healthcheck_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class ModelCapability(Base):
    __tablename__ = "model_capabilities"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    provider_type: Mapped[str] = mapped_column(String(64), default="openai_compatible", index=True)
    model_slug: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    supports_tools: Mapped[bool] = mapped_column(Boolean, default=False)
    supports_vision: Mapped[bool] = mapped_column(Boolean, default=False)
    max_context_tokens: Mapped[int] = mapped_column(Integer, default=8192)
    cost_per_1k_input: Mapped[float] = mapped_column(Float, default=0.0)
    cost_per_1k_output: Mapped[float] = mapped_column(Float, default=0.0)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    triggered_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    orchestrator_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    worker_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    reviewer_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    provider_config_id: Mapped[str | None] = mapped_column(
        ForeignKey("provider_configs.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    brainstorm_id: Mapped[str | None] = mapped_column(
        ForeignKey("brainstorms.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    run_mode: Mapped[str] = mapped_column(String(32), default="single_agent")
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    attempt_number: Mapped[int] = mapped_column(Integer, default=1)
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    token_total: Mapped[int] = mapped_column(Integer, default=0)
    estimated_cost_micros: Mapped[int] = mapped_column(Integer, default=0)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    checkpoint_json: Mapped[dict] = mapped_column(JSON, default=dict)
    input_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cancelled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class RunEvent(Base):
    __tablename__ = "run_events"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    run_id: Mapped[str] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    level: Mapped[str] = mapped_column(String(16), default="info")
    event_type: Mapped[str] = mapped_column(String(64), default="log")
    message: Mapped[str] = mapped_column(Text)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    input_tokens: Mapped[int] = mapped_column(Integer, default=0)
    output_tokens: Mapped[int] = mapped_column(Integer, default=0)
    cost_usd_micros: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow, index=True)


class Brainstorm(Base):
    __tablename__ = "brainstorms"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    initiator_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        index=True,
    )
    moderator_agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    topic: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="draft")
    max_rounds: Mapped[int] = mapped_column(Integer, default=3)
    stop_conditions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_recommendation: Mapped[str | None] = mapped_column(Text, nullable=True)
    decision_log_json: Mapped[list[dict]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )


class BrainstormParticipant(Base):
    __tablename__ = "brainstorm_participants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    brainstorm_id: Mapped[str] = mapped_column(
        ForeignKey("brainstorms.id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    order_index: Mapped[int] = mapped_column(Integer, default=0)
    stance: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BrainstormMessage(Base):
    __tablename__ = "brainstorm_messages"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    brainstorm_id: Mapped[str] = mapped_column(
        ForeignKey("brainstorms.id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    round_number: Mapped[int] = mapped_column(Integer, default=1)
    message_type: Mapped[str] = mapped_column(String(32), default="argument")
    content: Mapped[str] = mapped_column(Text)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class ApprovalRequest(Base):
    __tablename__ = "approval_requests"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    issue_link_id: Mapped[str | None] = mapped_column(
        ForeignKey("github_issue_links.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    requested_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approved_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    approval_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class EvalRecord(Base):
    __tablename__ = "eval_records"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    run_a_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"), nullable=True
    )
    run_b_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"), nullable=True
    )
    agent_a_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True
    )
    agent_b_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True
    )
    model_a: Mapped[str | None] = mapped_column(String(255), nullable=True)
    model_b: Mapped[str | None] = mapped_column(String(255), nullable=True)
    winner: Mapped[str | None] = mapped_column(String(8), nullable=True)
    score_a: Mapped[float | None] = mapped_column(Float, nullable=True)
    score_b: Mapped[float | None] = mapped_column(Float, nullable=True)
    criteria_met_a: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    criteria_met_b: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=_utcnow, onupdate=_utcnow
    )
