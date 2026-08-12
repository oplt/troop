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
    __table_args__ = (
        UniqueConstraint("owner_id", "slug", name="uq_skills_owner_slug"),
    )

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
    skill_id: Mapped[str] = mapped_column(
        ForeignKey("skills.id", ondelete="CASCADE"), index=True
    )
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
        UniqueConstraint(
            "agent_id", "skill_id", name="uq_agent_skill_assignments_agent_skill"
        ),
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
    config_json: Mapped[dict] = mapped_column(JSON, default=dict)
    # Secrets never returned to frontend; encrypted at rest by settings layer when present.
    secrets_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
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
    is_published: Mapped[bool] = mapped_column(Boolean, default=False)
    created_by: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
    "ToolGrant",
    "ActionPolicy",
    "WorkflowDefinition",
    "WorkflowVersion",
    "WorkflowRun",
    "WorkflowStepRun",
    "ProjectAnalysis",
]
