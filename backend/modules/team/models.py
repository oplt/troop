from datetime import datetime
from uuid import uuid4

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from backend.db.base import Base
from backend.modules.orchestration.model_utils import utcnow


class AgentProfile(Base):
    __tablename__ = "agent_profiles"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    owner_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        nullable=True,
        index=True,
    )
    parent_agent_id: Mapped[str | None] = mapped_column(
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
    parent_template_slug: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    name: Mapped[str] = mapped_column(String(255))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    role: Mapped[str] = mapped_column(String(64), default="specialist")
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    mission_markdown: Mapped[str] = mapped_column(Text, default="")
    rules_markdown: Mapped[str] = mapped_column(Text, default="")
    output_contract_markdown: Mapped[str] = mapped_column(Text, default="")
    source_markdown: Mapped[str] = mapped_column(Text, default="")
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    visibility: Mapped[str] = mapped_column(String(32), default="private")
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    budget_json: Mapped[dict] = mapped_column(JSON, default=dict)
    timeout_seconds: Mapped[int] = mapped_column(Integer, default=900)
    retry_limit: Mapped[int] = mapped_column(Integer, default=1)
    memory_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    version: Mapped[int] = mapped_column(Integer, default=1)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AgentProfileVersion(Base):
    __tablename__ = "agent_profile_versions"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    agent_profile_id: Mapped[str] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    version_number: Mapped[int] = mapped_column(Integer)
    source_markdown: Mapped[str] = mapped_column(Text, default="")
    snapshot_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_by_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
        index=True,
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class SkillPack(Base):
    __tablename__ = "skill_packs"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    rules_markdown: Mapped[str] = mapped_column(Text, default="")
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class TeamTemplateCatalog(Base):
    __tablename__ = "team_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    outcome: Mapped[str] = mapped_column(String(255), default="")
    roles_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    tools_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    autonomy: Mapped[str] = mapped_column(String(64), default="medium")
    visibility: Mapped[str] = mapped_column(String(64), default="private")
    agent_template_slugs_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class AgentTemplateCatalog(Base):
    __tablename__ = "agent_templates"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    slug: Mapped[str] = mapped_column(String(255), index=True)
    name: Mapped[str] = mapped_column(String(255))
    role: Mapped[str] = mapped_column(String(64), default="specialist")
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    parent_template_slug: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    system_prompt: Mapped[str] = mapped_column(Text, default="")
    mission_markdown: Mapped[str] = mapped_column(Text, default="")
    rules_markdown: Mapped[str] = mapped_column(Text, default="")
    output_contract_markdown: Mapped[str] = mapped_column(Text, default="")
    capabilities_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    allowed_tools_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    skills_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    tags_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    model_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    budget_json: Mapped[dict] = mapped_column(JSON, default=dict)
    memory_policy_json: Mapped[dict] = mapped_column(JSON, default=dict)
    output_schema_json: Mapped[dict] = mapped_column(JSON, default=dict)
    metadata_json: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )


class ProjectAgentMembership(Base):
    __tablename__ = "project_agent_memberships"

    id: Mapped[str] = mapped_column(String, primary_key=True, default=lambda: str(uuid4()))
    project_id: Mapped[str] = mapped_column(
        ForeignKey("orchestrator_projects.id", ondelete="CASCADE"),
        index=True,
    )
    agent_id: Mapped[str] = mapped_column(
        ForeignKey("agent_profiles.id", ondelete="CASCADE"),
        index=True,
    )
    role: Mapped[str] = mapped_column(String(64), default="member")
    is_default_manager: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
