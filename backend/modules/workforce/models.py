"""First-class workforce domain: departments, skills, analysis, tools, workflows."""

from __future__ import annotations

from datetime import datetime
from uuid import uuid4

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Integer,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.modules.orchestration.model_utils import utcnow


class Department(Base):
    __tablename__ = "departments"
    __table_args__ = (UniqueConstraint("company_id", "slug", name="uq_departments_company_slug"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    company_id: Mapped[str] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_department_id: Mapped[str | None] = mapped_column(
        ForeignKey("departments.id", ondelete="SET NULL"), nullable=True, index=True
    )
    default_knowledge_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    default_tool_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    default_model_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    default_approval_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    budget_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_archived: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class Skill(Base):
    """Versioned skill identity. Replaces SkillPack as the canonical skill entity."""

    __tablename__ = "skills"
    __table_args__ = (UniqueConstraint("owner_id", "slug", name="uq_skills_owner_slug"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    legacy_skill_pack_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_packs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    scope: Mapped[str] = mapped_column(String(32), default="organization", index=True)
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    current_version_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SkillVersion(Base):
    """Immutable published skill content."""

    __tablename__ = "skill_versions"
    __table_args__ = (
        UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    version_number: Mapped[int] = mapped_column(Integer)
    purpose: Mapped[str] = mapped_column(Text, default="")
    when_to_use: Mapped[str] = mapped_column(Text, default="")
    instructions_markdown: Mapped[str] = mapped_column(Text, default="")
    input_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    capabilities_json: Mapped[list] = mapped_column(JSON, default=list)
    required_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    knowledge_requirements_json: Mapped[list] = mapped_column(JSON, default=list)
    constraints_markdown: Mapped[str] = mapped_column(Text, default="")
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    approval_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    examples_json: Mapped[list] = mapped_column(JSON, default=list)
    evaluation_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    source_type: Mapped[str] = mapped_column(String(64), default="manual")
    source_task_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    source_project_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    generated_by_model: Mapped[str | None] = mapped_column(String(255), nullable=True)
    generation_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillDraft(Base):
    """Mutable draft shared by markdown import, manual builder, and AI generation."""

    __tablename__ = "skill_drafts"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    skill_id: Mapped[str | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_type: Mapped[str] = mapped_column(String(64), default="manual", index=True)
    source_task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    source_project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="draft", index=True)
    name: Mapped[str] = mapped_column(String(255), default="")
    slug: Mapped[str] = mapped_column(String(255), default="")
    description: Mapped[str] = mapped_column(Text, default="")
    purpose: Mapped[str] = mapped_column(Text, default="")
    when_to_use: Mapped[str] = mapped_column(Text, default="")
    instructions_markdown: Mapped[str] = mapped_column(Text, default="")
    scope: Mapped[str] = mapped_column(String(32), default="project")
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    capabilities_json: Mapped[list] = mapped_column(JSON, default=list)
    required_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    knowledge_requirements_json: Mapped[list] = mapped_column(JSON, default=list)
    input_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    constraints_markdown: Mapped[str] = mapped_column(Text, default="")
    approval_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    examples_json: Mapped[list] = mapped_column(JSON, default=list)
    evaluation_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    validation_errors_json: Mapped[list] = mapped_column(JSON, default=list)
    warnings_json: Mapped[list] = mapped_column(JSON, default=list)
    unmatched_sections_json: Mapped[list] = mapped_column(JSON, default=list)
    duplicate_matches_json: Mapped[list] = mapped_column(JSON, default=list)
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    generation_metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AgentSkillAssignment(Base):
    __tablename__ = "agent_skill_assignments"
    __table_args__ = (
        UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill_assignments_agent_skill"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"), index=True
    )
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    skill_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    version_policy: Mapped[str] = mapped_column(String(32), default="latest_active")
    priority: Mapped[int] = mapped_column(Integer, default=100)
    enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskAnalysis(Base):
    __tablename__ = "task_analyses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    task_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    analyzer_version: Mapped[str] = mapped_column(String(64), default="1.0.0")
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    content_fingerprint: Mapped[str] = mapped_column(String(64), index=True)
    objective: Mapped[str] = mapped_column(Text, default="")
    task_category: Mapped[str] = mapped_column(String(128), default="general")
    risk_level: Mapped[str] = mapped_column(String(32), default="medium")
    autonomy_recommendation: Mapped[str] = mapped_column(String(64), default="semi-autonomous")
    required_capabilities_json: Mapped[list] = mapped_column(JSON, default=list)
    required_tools_json: Mapped[list] = mapped_column(JSON, default=list)
    knowledge_requirements_json: Mapped[list] = mapped_column(JSON, default=list)
    expected_artifacts_json: Mapped[list] = mapped_column(JSON, default=list)
    acceptance_criteria_json: Mapped[list] = mapped_column(JSON, default=list)
    review_requirements_json: Mapped[list] = mapped_column(JSON, default=list)
    approval_requirements_json: Mapped[list] = mapped_column(JSON, default=list)
    raw_output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskRequirement(Base):
    __tablename__ = "task_requirements"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    analysis_id: Mapped[str] = mapped_column(
        ForeignKey("task_analyses.id", ondelete="CASCADE"), index=True
    )
    task_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="CASCADE"), index=True
    )
    kind: Mapped[str] = mapped_column(String(64), default="capability")
    key: Mapped[str] = mapped_column(String(255), index=True)
    label: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    priority: Mapped[str] = mapped_column(String(32), default="required")
    coverage_status: Mapped[str] = mapped_column(String(32), default="missing")
    matched_skill_id: Mapped[str | None] = mapped_column(
        ForeignKey("skills.id", ondelete="SET NULL"), nullable=True, index=True
    )
    match_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    match_explanation: Mapped[str | None] = mapped_column(Text, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillEvaluation(Base):
    __tablename__ = "skill_evaluations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    skill_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_id: Mapped[str | None] = mapped_column(
        ForeignKey("task_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    agent_id: Mapped[str | None] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="SET NULL"), nullable=True, index=True
    )
    success: Mapped[bool] = mapped_column(Boolean, default=False)
    human_accepted: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    score: Mapped[float | None] = mapped_column(Float, nullable=True)
    latency_ms: Mapped[int | None] = mapped_column(Integer, nullable=True)
    token_usage: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cost_usd: Mapped[float | None] = mapped_column(Float, nullable=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    criteria_scores_json: Mapped[dict] = mapped_column(JSON, default=dict)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillUsageStat(Base):
    __tablename__ = "skill_usage_stats"
    __table_args__ = (
        UniqueConstraint("skill_id", "skill_version_id", name="uq_skill_usage_stats_skill_version"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    skill_id: Mapped[str] = mapped_column(ForeignKey("skills.id", ondelete="CASCADE"), index=True)
    skill_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("skill_versions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    run_count: Mapped[int] = mapped_column(Integer, default=0)
    success_count: Mapped[int] = mapped_column(Integer, default=0)
    human_accept_count: Mapped[int] = mapped_column(Integer, default=0)
    total_latency_ms: Mapped[int] = mapped_column(Integer, default=0)
    total_cost_usd: Mapped[float] = mapped_column(Float, default=0.0)
    total_retries: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ToolDefinition(Base):
    __tablename__ = "tool_definitions"
    __table_args__ = (UniqueConstraint("slug", name="uq_tool_definitions_slug"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    provider_type: Mapped[str] = mapped_column(String(64), default="native")
    schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    side_effect: Mapped[str] = mapped_column(String(32), default="read")
    reversibility: Mapped[str] = mapped_column(String(32), default="none")
    data_sensitivity: Mapped[str] = mapped_column(String(32), default="internal")
    parallel_safe: Mapped[bool] = mapped_column(Boolean, default=False)
    idempotency_strategy: Mapped[str] = mapped_column(String(64), default="none")
    commit_check_strategy: Mapped[str] = mapped_column(String(64), default="none")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectorDefinition(Base):
    __tablename__ = "connector_definitions"
    __table_args__ = (UniqueConstraint("slug", name="uq_connector_definitions_slug"),)

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    provider_type: Mapped[str] = mapped_column(String(64), default="native")
    config_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectorInstallation(Base):
    __tablename__ = "connector_installations"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    connector_definition_id: Mapped[str] = mapped_column(
        ForeignKey("connector_definitions.id", ondelete="CASCADE"), index=True
    )
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255))
    status: Mapped[str] = mapped_column(String(32), default="active")
    environment: Mapped[str] = mapped_column(String(32), default="dev", index=True)
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Secrets never returned to frontend; encrypted at rest by settings layer when present.
    secrets_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ConnectorOperation(Base):
    """Provider-neutral trigger/search/read/action operation metadata."""

    __tablename__ = "connector_operations"
    __table_args__ = (
        UniqueConstraint(
            "connector_definition_id", "slug", name="uq_connector_operations_definition_slug"
        ),
        Index("ix_connector_operations_type_active", "operation_type", "is_active"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    connector_definition_id: Mapped[str] = mapped_column(
        ForeignKey("connector_definitions.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)
    operation_type: Mapped[str] = mapped_column(String(32), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    input_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    risk_level: Mapped[str] = mapped_column(String(32), default="low")
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=False)
    required_scopes_json: Mapped[list] = mapped_column(JSON, default=list)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ConnectorOAuthState(Base):
    """Short-lived single-use OAuth state and PKCE verifier."""

    __tablename__ = "connector_oauth_states"
    __table_args__ = (
        UniqueConstraint("state_hash", name="uq_connector_oauth_states_state_hash"),
        Index("ix_connector_oauth_states_owner_provider", "owner_id", "provider"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    state_hash: Mapped[str] = mapped_column(String(64))
    encrypted_code_verifier: Mapped[str] = mapped_column(Text)
    requested_scopes_json: Mapped[list] = mapped_column(JSON, default=list)
    redirect_after: Mapped[str | None] = mapped_column(String(1000), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TriggerSubscription(Base):
    __tablename__ = "trigger_subscriptions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_version_id",
            "node_id",
            "connector_installation_id",
            name="uq_trigger_subscriptions_version_node_installation",
        ),
        Index("ix_trigger_subscriptions_status_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(255))
    provider: Mapped[str] = mapped_column(String(64), index=True)
    external_subscription_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    external_cursor: Mapped[str | None] = mapped_column(String(512), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_event_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ExternalEvent(Base):
    """Durable inbox row. Payload is normalized and intentionally minimal."""

    __tablename__ = "external_events"
    __table_args__ = (
        UniqueConstraint("provider", "dedupe_key", name="uq_external_events_provider_dedupe"),
        Index("ix_external_events_status_received", "status", "received_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    external_event_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    event_type: Mapped[str] = mapped_column(String(128), index=True)
    dedupe_key: Mapped[str] = mapped_column(String(64))
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    workflow_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class ExternalKnowledgeSource(Base):
    __tablename__ = "external_knowledge_sources"
    __table_args__ = (
        UniqueConstraint(
            "project_id",
            "connector_installation_id",
            "provider",
            name="uq_external_knowledge_sources_project_installation",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    provider: Mapped[str] = mapped_column(String(64), index=True)
    root_config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sync_cursor: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    last_synced_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ExternalDocumentSyncState(Base):
    __tablename__ = "external_document_sync_states"
    __table_args__ = (
        UniqueConstraint(
            "source_id", "external_file_id", name="uq_external_document_sync_source_file"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    source_id: Mapped[str] = mapped_column(
        ForeignKey("external_knowledge_sources.id", ondelete="CASCADE"), index=True
    )
    external_file_id: Mapped[str] = mapped_column(String(512))
    external_path: Mapped[str] = mapped_column(String(1024), default="")
    etag: Mapped[str | None] = mapped_column(String(255), nullable=True)
    project_document_id: Mapped[str | None] = mapped_column(
        ForeignKey("project_documents.id", ondelete="SET NULL"), nullable=True, index=True
    )
    acl_snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    sync_status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ApprovalDelivery(Base):
    __tablename__ = "approval_deliveries"
    __table_args__ = (
        UniqueConstraint(
            "approval_request_id",
            "channel",
            "connector_installation_id",
            "destination_id",
            name="uq_approval_deliveries_target",
        ),
        Index("ix_approval_deliveries_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    approval_request_id: Mapped[str] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True
    )
    channel: Mapped[str] = mapped_column(String(64), index=True)
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    destination_id: Mapped[str] = mapped_column(String(255))
    external_message_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    delivered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    responded_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TelegramIdentityBinding(Base):
    __tablename__ = "telegram_identity_bindings"
    __table_args__ = (
        UniqueConstraint(
            "connector_installation_id",
            "telegram_user_id",
            name="uq_telegram_bindings_installation_user",
        ),
        UniqueConstraint("link_token_hash", name="uq_telegram_bindings_link_token_hash"),
        Index("ix_telegram_bindings_owner_status", "owner_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    telegram_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    telegram_chat_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    telegram_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class SlackIdentityBinding(Base):
    __tablename__ = "slack_identity_bindings"
    __table_args__ = (
        UniqueConstraint(
            "connector_installation_id",
            "slack_user_id",
            name="uq_slack_bindings_installation_user",
        ),
        UniqueConstraint("link_token_hash", name="uq_slack_bindings_link_token_hash"),
        Index("ix_slack_bindings_owner_status", "owner_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    slack_team_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slack_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    slack_channel_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    slack_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TeamsIdentityBinding(Base):
    __tablename__ = "teams_identity_bindings"
    __table_args__ = (
        UniqueConstraint(
            "connector_installation_id",
            "teams_user_id",
            name="uq_teams_bindings_installation_user",
        ),
        UniqueConstraint("link_token_hash", name="uq_teams_bindings_link_token_hash"),
        Index("ix_teams_bindings_owner_status", "owner_id", "status"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    teams_tenant_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    teams_user_id: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    conversation_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    teams_username: Mapped[str | None] = mapped_column(String(255), nullable=True)
    link_token_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    token_expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    linked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ApprovalInteraction(Base):
    __tablename__ = "approval_interactions"
    __table_args__ = (
        UniqueConstraint(
            "approval_request_id",
            "telegram_user_id",
            "mode",
            name="uq_approval_interactions_approval_user_mode",
        ),
        Index("ix_approval_interactions_status_expiry", "status", "expires_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    approval_request_id: Mapped[str] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="CASCADE"), index=True
    )
    approval_delivery_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_deliveries.id", ondelete="CASCADE"), nullable=True, index=True
    )
    telegram_user_id: Mapped[str] = mapped_column(String(64), index=True)
    mode: Mapped[str] = mapped_column(String(32))
    expected_input: Mapped[str] = mapped_column(String(64), default="text")
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DraftExecutionMetadata(Base):
    __tablename__ = "draft_execution_metadata"
    __table_args__ = (
        UniqueConstraint(
            "connector_installation_id",
            "provider_draft_id",
            name="uq_draft_execution_installation_provider_draft",
        ),
        Index("ix_draft_execution_status_updated", "status", "updated_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="CASCADE"), nullable=True, index=True
    )
    connector_installation_id: Mapped[str] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), index=True
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    workflow_node_id: Mapped[str | None] = mapped_column(String(255), nullable=True)
    provider_draft_id: Mapped[str] = mapped_column(String(512))
    message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    thread_fingerprint: Mapped[str] = mapped_column(String(64))
    content_hash: Mapped[str] = mapped_column(String(64), index=True)
    draft_version: Mapped[int] = mapped_column(Integer, default=1)
    status: Mapped[str] = mapped_column(String(32), default="current", index=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ExternalActionExecution(Base):
    """Exactly-once local action claim and provider reconciliation record."""

    __tablename__ = "external_action_executions"
    __table_args__ = (
        UniqueConstraint("idempotency_key", name="uq_external_action_executions_key"),
        Index("ix_external_action_executions_status_created", "status", "created_at"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    connector_installation_id: Mapped[str | None] = mapped_column(
        ForeignKey("connector_installations.id", ondelete="CASCADE"), nullable=True, index=True
    )
    workflow_run_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="SET NULL"), nullable=True, index=True
    )
    approval_request_id: Mapped[str | None] = mapped_column(
        ForeignKey("approval_requests.id", ondelete="SET NULL"), nullable=True, index=True
    )
    action_key: Mapped[str] = mapped_column(String(255), index=True)
    idempotency_key: Mapped[str] = mapped_column(String(64))
    arguments_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="claimed", index=True)
    external_result_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ToolGrant(Base):
    __tablename__ = "tool_grants"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    tool_definition_id: Mapped[str] = mapped_column(
        ForeignKey("tool_definitions.id", ondelete="CASCADE"), index=True
    )
    subject_type: Mapped[str] = mapped_column(String(64), index=True)  # agent|skill|project|dept
    subject_id: Mapped[str] = mapped_column(String, index=True)
    effect: Mapped[str] = mapped_column(String(16), default="allow")  # allow|deny
    conditions_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ActionPolicy(Base):
    __tablename__ = "action_policies"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    scope_type: Mapped[str] = mapped_column(String(64), default="organization")
    scope_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    action_key: Mapped[str] = mapped_column(String(255), index=True)
    decision: Mapped[str] = mapped_column(String(64), default="approval_required")
    risk_level: Mapped[str] = mapped_column(String(32), default="medium")
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkflowDefinition(Base):
    __tablename__ = "workflow_definitions"
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_workflow_definitions_owner_slug"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    company_id: Mapped[str | None] = mapped_column(
        ForeignKey("companies.id", ondelete="SET NULL"), nullable=True, index=True
    )
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    category: Mapped[str] = mapped_column(String(64), default="general")
    status: Mapped[str] = mapped_column(String(32), default="draft")
    current_version_id: Mapped[str | None] = mapped_column(String, nullable=True)
    draft_version_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    published_version_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    is_template: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkflowVersion(Base):
    __tablename__ = "workflow_versions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id", "version_number", name="uq_workflow_versions_workflow_version"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    version_number: Mapped[int] = mapped_column(Integer)
    nodes_json: Mapped[list] = mapped_column(JSON, default=list)
    edges_json: Mapped[list] = mapped_column(JSON, default=list)
    entry_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    graph_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowEnvironmentDeployment(Base):
    """Active immutable version + connection bindings for one workflow environment."""

    __tablename__ = "workflow_environment_deployments"
    __table_args__ = (
        UniqueConstraint(
            "workflow_id",
            "environment",
            name="uq_workflow_environment_deployments_workflow_env",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    environment: Mapped[str] = mapped_column(String(32), index=True)
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE")
    )
    connection_bindings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    deployed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    deployed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkflowEnvironmentDeploymentEvent(Base):
    """Audit trail for environment promotions and rollbacks."""

    __tablename__ = "workflow_environment_deployment_events"
    __table_args__ = (
        Index(
            "ix_workflow_environment_deployment_events_workflow_env", "workflow_id", "environment"
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    environment: Mapped[str] = mapped_column(String(32))
    action: Mapped[str] = mapped_column(String(32))
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE")
    )
    connection_bindings_json: Mapped[dict] = mapped_column(JSON, default=dict)
    previous_version_id: Mapped[str | None] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="SET NULL"), nullable=True
    )
    previous_bindings_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    actor_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)


class WorkflowRun(Base):
    __tablename__ = "workflow_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_definitions.id", ondelete="CASCADE"), index=True
    )
    workflow_version_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_versions.id", ondelete="CASCADE"), index=True
    )
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    task_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_tasks.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(32), default="queued", index=True)
    current_node_id: Mapped[str | None] = mapped_column(String, nullable=True)
    context_json: Mapped[dict] = mapped_column(JSON, default=dict)
    result_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkflowStepRun(Base):
    __tablename__ = "workflow_step_runs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    node_id: Mapped[str] = mapped_column(String(255))
    node_type: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(32), default="pending")
    input_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkflowChildExecution(Base):
    """Indexed parent↔child link for agent/subworkflow/parallel branch wakes."""

    __tablename__ = "workflow_child_executions"
    __table_args__ = (
        UniqueConstraint(
            "workflow_run_id",
            "workflow_node_id",
            "child_run_id",
            name="uq_workflow_child_exec_run_node_child",
        ),
        UniqueConstraint(
            "workflow_run_id",
            "workflow_node_id",
            "branch_key",
            name="uq_workflow_child_exec_run_node_branch",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workflow_run_id: Mapped[str] = mapped_column(
        ForeignKey("workflow_runs.id", ondelete="CASCADE"), index=True
    )
    workflow_node_id: Mapped[str] = mapped_column(String(255))
    child_type: Mapped[str] = mapped_column(String(32))  # task_run | workflow_run | branch
    child_run_id: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    branch_key: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="pending", index=True)
    output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectAnalysis(Base):
    __tablename__ = "project_analyses"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"), index=True
    )
    analyzer_version: Mapped[str] = mapped_column(String(64), default="1.0.0")
    model_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    recommended_tasks_json: Mapped[list] = mapped_column(JSON, default=list)
    recommended_skills_json: Mapped[list] = mapped_column(JSON, default=list)
    recommended_agents_json: Mapped[list] = mapped_column(JSON, default=list)
    recommended_workflow_json: Mapped[dict] = mapped_column(JSON, default=dict)
    raw_output_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspacePackage(Base):
    """Private workspace-scoped package catalog entry (MKT-001)."""

    __tablename__ = "workspace_packages"
    __table_args__ = (
        UniqueConstraint("workspace_id", "slug", name="uq_workspace_packages_workspace_slug"),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    owner_user_id: Mapped[str] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), index=True
    )
    slug: Mapped[str] = mapped_column(String(128), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str] = mapped_column(Text, default="")
    kind: Mapped[str] = mapped_column(String(32))
    visibility: Mapped[str] = mapped_column(String(32), default="private")
    source_marketplace_slug: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class WorkspacePackageVersion(Base):
    __tablename__ = "workspace_package_versions"
    __table_args__ = (
        UniqueConstraint(
            "package_id",
            "version_number",
            name="uq_workspace_package_versions_package_version",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    package_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_packages.id", ondelete="CASCADE"), index=True
    )
    version_label: Mapped[str] = mapped_column(String(64))
    version_number: Mapped[int] = mapped_column(Integer)
    payload_json: Mapped[dict] = mapped_column(JSON, default=dict)
    permission_manifest_json: Mapped[dict] = mapped_column(JSON, default=dict)
    trust_json: Mapped[dict] = mapped_column(JSON, default=dict)
    changelog: Mapped[str] = mapped_column(Text, default="")
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class WorkspacePackageInstallation(Base):
    __tablename__ = "workspace_package_installations"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "package_id",
            name="uq_workspace_package_installations_workspace_package",
        ),
    )

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    workspace_id: Mapped[str] = mapped_column(
        ForeignKey("workspaces.id", ondelete="CASCADE"), index=True
    )
    package_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_packages.id", ondelete="CASCADE"), index=True
    )
    installed_version_id: Mapped[str] = mapped_column(
        ForeignKey("workspace_package_versions.id", ondelete="CASCADE")
    )
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    installed_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    installed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


__all__ = [
    "Department",
    "Skill",
    "SkillVersion",
    "SkillDraft",
    "AgentSkillAssignment",
    "TaskAnalysis",
    "TaskRequirement",
    "SkillEvaluation",
    "SkillUsageStat",
    "ToolDefinition",
    "ConnectorDefinition",
    "ConnectorInstallation",
    "ConnectorOperation",
    "ConnectorOAuthState",
    "TriggerSubscription",
    "ExternalEvent",
    "ExternalKnowledgeSource",
    "ExternalDocumentSyncState",
    "ApprovalDelivery",
    "TelegramIdentityBinding",
    "SlackIdentityBinding",
    "TeamsIdentityBinding",
    "ApprovalInteraction",
    "DraftExecutionMetadata",
    "ExternalActionExecution",
    "ToolGrant",
    "ActionPolicy",
    "WorkflowDefinition",
    "WorkflowVersion",
    "WorkflowRun",
    "WorkflowStepRun",
    "WorkflowChildExecution",
    "WorkspacePackage",
    "WorkspacePackageVersion",
    "WorkspacePackageInstallation",
    "ProjectAnalysis",
]
