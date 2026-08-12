"""Workforce domain foundation: departments, skills, analysis, tools, workflows.

Revision ID: e8a1c2d3f4b5
Revises: d5e6f7a8b9c0
Create Date: 2026-08-12 18:49:00.000000
"""

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy import text

from alembic import op

revision: str = "e8a1c2d3f4b5"
down_revision: str | Sequence[str] | None = "d5e6f7a8b9c0"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Create departments table first (FK dependency from orchestrator_projects)
    op.create_table(
        "departments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("parent_department_id", sa.String(), nullable=True),
        sa.Column("default_knowledge_policy_json", sa.JSON(), nullable=False),
        sa.Column("default_tool_policy_json", sa.JSON(), nullable=False),
        sa.Column("default_model_policy_json", sa.JSON(), nullable=False),
        sa.Column("default_approval_policy_json", sa.JSON(), nullable=False),
        sa.Column("budget_policy_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_archived", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_department_id"], ["departments.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("company_id", "slug", name="uq_departments_company_slug"),
    )
    op.create_index("ix_departments_company_id", "departments", ["company_id"])
    op.create_index("ix_departments_slug", "departments", ["slug"])
    op.create_index("ix_departments_parent_department_id", "departments", ["parent_department_id"])

    # Extend orchestrator_projects table
    op.add_column("orchestrator_projects", sa.Column("department_id", sa.String(), nullable=True))
    op.add_column(
        "orchestrator_projects",
        sa.Column("knowledge_policy_json", sa.JSON(), nullable=True, server_default="{}"),
    )
    op.add_column("orchestrator_projects", sa.Column("budget_json", sa.JSON(), nullable=True))
    op.add_column("orchestrator_projects", sa.Column("metadata_json", sa.JSON(), nullable=True))
    op.create_foreign_key(
        "fk_orchestrator_projects_department_id_departments",
        "orchestrator_projects",
        "departments",
        ["department_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_orchestrator_projects_department_id",
        "orchestrator_projects",
        ["department_id"],
    )

    # Extend orchestrator_tasks table
    op.add_column("orchestrator_tasks", sa.Column("human_assignee_id", sa.String(), nullable=True))
    op.add_column("orchestrator_tasks", sa.Column("reviewer_user_id", sa.String(), nullable=True))
    op.add_column("orchestrator_tasks", sa.Column("objective", sa.Text(), nullable=True))
    op.add_column("orchestrator_tasks", sa.Column("expected_output", sa.Text(), nullable=True))
    op.add_column(
        "orchestrator_tasks",
        sa.Column("risk_level", sa.String(length=32), nullable=False, server_default="medium"),
    )
    op.add_column(
        "orchestrator_tasks",
        sa.Column(
            "autonomy_level",
            sa.String(length=64),
            nullable=False,
            server_default="semi-autonomous",
        ),
    )
    op.add_column(
        "orchestrator_tasks",
        sa.Column("assignment_mode", sa.String(length=32), nullable=False, server_default="manual"),
    )
    op.create_foreign_key(
        "fk_orchestrator_tasks_human_assignee_id_users",
        "orchestrator_tasks",
        "users",
        ["human_assignee_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "fk_orchestrator_tasks_reviewer_user_id_users",
        "orchestrator_tasks",
        "users",
        ["reviewer_user_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_index(
        "ix_orchestrator_tasks_human_assignee_id",
        "orchestrator_tasks",
        ["human_assignee_id"],
    )
    op.create_index(
        "ix_orchestrator_tasks_reviewer_user_id",
        "orchestrator_tasks",
        ["reviewer_user_id"],
    )

    # Create skills table (referenced by skill_versions and others)
    op.create_table(
        "skills",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("legacy_skill_pack_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version_id", sa.String(), nullable=True),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["legacy_skill_pack_id"], ["skill_packs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_skills_owner_slug"),
    )
    op.create_index("ix_skills_owner_id", "skills", ["owner_id"])
    op.create_index("ix_skills_company_id", "skills", ["company_id"])
    op.create_index("ix_skills_legacy_skill_pack_id", "skills", ["legacy_skill_pack_id"])
    op.create_index("ix_skills_slug", "skills", ["slug"])
    op.create_index("ix_skills_scope", "skills", ["scope"])
    op.create_index("ix_skills_status", "skills", ["status"])
    op.create_index("ix_skills_current_version_id", "skills", ["current_version_id"])
    op.create_index("ix_skills_project_id", "skills", ["project_id"])
    op.create_index("ix_skills_task_id", "skills", ["task_id"])
    op.create_index("ix_skills_created_by", "skills", ["created_by"])

    # Create skill_versions table
    op.create_table(
        "skill_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("when_to_use", sa.Text(), nullable=False),
        sa.Column("instructions_markdown", sa.Text(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("required_tools_json", sa.JSON(), nullable=False),
        sa.Column("knowledge_requirements_json", sa.JSON(), nullable=False),
        sa.Column("constraints_markdown", sa.Text(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("approval_policy_json", sa.JSON(), nullable=False),
        sa.Column("examples_json", sa.JSON(), nullable=False),
        sa.Column("evaluation_criteria_json", sa.JSON(), nullable=False),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_task_id", sa.String(), nullable=True),
        sa.Column("source_project_id", sa.String(), nullable=True),
        sa.Column("generated_by_model", sa.String(length=255), nullable=True),
        sa.Column("generation_metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "version_number", name="uq_skill_versions_skill_version"),
    )
    op.create_index("ix_skill_versions_skill_id", "skill_versions", ["skill_id"])
    op.create_index("ix_skill_versions_source_task_id", "skill_versions", ["source_task_id"])
    op.create_index("ix_skill_versions_source_project_id", "skill_versions", ["source_project_id"])

    # Create skill_drafts table
    op.create_table(
        "skill_drafts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("skill_id", sa.String(), nullable=True),
        sa.Column("source_type", sa.String(length=64), nullable=False),
        sa.Column("source_task_id", sa.String(), nullable=True),
        sa.Column("source_project_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("purpose", sa.Text(), nullable=False),
        sa.Column("when_to_use", sa.Text(), nullable=False),
        sa.Column("instructions_markdown", sa.Text(), nullable=False),
        sa.Column("scope", sa.String(length=32), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("required_tools_json", sa.JSON(), nullable=False),
        sa.Column("knowledge_requirements_json", sa.JSON(), nullable=False),
        sa.Column("input_schema_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("constraints_markdown", sa.Text(), nullable=False),
        sa.Column("approval_policy_json", sa.JSON(), nullable=False),
        sa.Column("examples_json", sa.JSON(), nullable=False),
        sa.Column("evaluation_criteria_json", sa.JSON(), nullable=False),
        sa.Column("validation_errors_json", sa.JSON(), nullable=False),
        sa.Column("warnings_json", sa.JSON(), nullable=False),
        sa.Column("unmatched_sections_json", sa.JSON(), nullable=False),
        sa.Column("duplicate_matches_json", sa.JSON(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=True),
        sa.Column("generation_metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["source_task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["source_project_id"], ["orchestrator_projects.id"], ondelete="SET NULL"
        ),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skill_drafts_owner_id", "skill_drafts", ["owner_id"])
    op.create_index("ix_skill_drafts_company_id", "skill_drafts", ["company_id"])
    op.create_index("ix_skill_drafts_skill_id", "skill_drafts", ["skill_id"])
    op.create_index("ix_skill_drafts_source_type", "skill_drafts", ["source_type"])
    op.create_index("ix_skill_drafts_source_task_id", "skill_drafts", ["source_task_id"])
    op.create_index("ix_skill_drafts_source_project_id", "skill_drafts", ["source_project_id"])
    op.create_index("ix_skill_drafts_status", "skill_drafts", ["status"])

    # Create agent_skill_assignments table
    op.create_table(
        "agent_skill_assignments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("skill_version_id", sa.String(), nullable=True),
        sa.Column("version_policy", sa.String(length=32), nullable=False),
        sa.Column("priority", sa.Integer(), nullable=False),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("agent_id", "skill_id", name="uq_agent_skill_assignments_agent_skill"),
    )
    op.create_index("ix_agent_skill_assignments_agent_id", "agent_skill_assignments", ["agent_id"])
    op.create_index("ix_agent_skill_assignments_skill_id", "agent_skill_assignments", ["skill_id"])
    op.create_index(
        "ix_agent_skill_assignments_skill_version_id",
        "agent_skill_assignments",
        ["skill_version_id"],
    )

    # Create task_analyses table
    op.create_table(
        "task_analyses",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("analyzer_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("content_fingerprint", sa.String(length=64), nullable=False),
        sa.Column("objective", sa.Text(), nullable=False),
        sa.Column("task_category", sa.String(length=128), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("autonomy_recommendation", sa.String(length=64), nullable=False),
        sa.Column("required_capabilities_json", sa.JSON(), nullable=False),
        sa.Column("required_tools_json", sa.JSON(), nullable=False),
        sa.Column("knowledge_requirements_json", sa.JSON(), nullable=False),
        sa.Column("expected_artifacts_json", sa.JSON(), nullable=False),
        sa.Column("acceptance_criteria_json", sa.JSON(), nullable=False),
        sa.Column("review_requirements_json", sa.JSON(), nullable=False),
        sa.Column("approval_requirements_json", sa.JSON(), nullable=False),
        sa.Column("raw_output_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_analyses_task_id", "task_analyses", ["task_id"])
    op.create_index("ix_task_analyses_project_id", "task_analyses", ["project_id"])
    op.create_index("ix_task_analyses_content_fingerprint", "task_analyses", ["content_fingerprint"])

    # Create task_requirements table
    op.create_table(
        "task_requirements",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("analysis_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("key", sa.String(length=255), nullable=False),
        sa.Column("label", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("coverage_status", sa.String(length=32), nullable=False),
        sa.Column("matched_skill_id", sa.String(), nullable=True),
        sa.Column("match_score", sa.Float(), nullable=True),
        sa.Column("match_explanation", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["analysis_id"], ["task_analyses.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["matched_skill_id"], ["skills.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_task_requirements_analysis_id", "task_requirements", ["analysis_id"])
    op.create_index("ix_task_requirements_task_id", "task_requirements", ["task_id"])
    op.create_index("ix_task_requirements_key", "task_requirements", ["key"])
    op.create_index("ix_task_requirements_matched_skill_id", "task_requirements", ["matched_skill_id"])

    # Create skill_evaluations table
    op.create_table(
        "skill_evaluations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("skill_version_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("success", sa.Boolean(), nullable=False),
        sa.Column("human_accepted", sa.Boolean(), nullable=True),
        sa.Column("score", sa.Float(), nullable=True),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("token_usage", sa.Integer(), nullable=True),
        sa.Column("cost_usd", sa.Float(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("criteria_scores_json", sa.JSON(), nullable=False),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_skill_evaluations_skill_id", "skill_evaluations", ["skill_id"])
    op.create_index("ix_skill_evaluations_skill_version_id", "skill_evaluations", ["skill_version_id"])
    op.create_index("ix_skill_evaluations_task_id", "skill_evaluations", ["task_id"])
    op.create_index("ix_skill_evaluations_run_id", "skill_evaluations", ["run_id"])
    op.create_index("ix_skill_evaluations_agent_id", "skill_evaluations", ["agent_id"])

    # Create skill_usage_stats table
    op.create_table(
        "skill_usage_stats",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("skill_id", sa.String(), nullable=False),
        sa.Column("skill_version_id", sa.String(), nullable=True),
        sa.Column("run_count", sa.Integer(), nullable=False),
        sa.Column("success_count", sa.Integer(), nullable=False),
        sa.Column("human_accept_count", sa.Integer(), nullable=False),
        sa.Column("total_latency_ms", sa.Integer(), nullable=False),
        sa.Column("total_cost_usd", sa.Float(), nullable=False),
        sa.Column("total_retries", sa.Integer(), nullable=False),
        sa.Column("last_used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["skill_id"], ["skills.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["skill_version_id"], ["skill_versions.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("skill_id", "skill_version_id", name="uq_skill_usage_stats_skill_version"),
    )
    op.create_index("ix_skill_usage_stats_skill_id", "skill_usage_stats", ["skill_id"])
    op.create_index("ix_skill_usage_stats_skill_version_id", "skill_usage_stats", ["skill_version_id"])

    # Create tool_definitions table
    op.create_table(
        "tool_definitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("schema_json", sa.JSON(), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("requires_approval", sa.Boolean(), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_tool_definitions_slug"),
    )
    op.create_index("ix_tool_definitions_slug", "tool_definitions", ["slug"])

    # Create connector_definitions table
    op.create_table(
        "connector_definitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("config_schema_json", sa.JSON(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug", name="uq_connector_definitions_slug"),
    )
    op.create_index("ix_connector_definitions_slug", "connector_definitions", ["slug"])

    # Create connector_installations table
    op.create_table(
        "connector_installations",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("connector_definition_id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("config_json", sa.JSON(), nullable=False),
        sa.Column("secrets_ref", sa.String(length=255), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(
            ["connector_definition_id"], ["connector_definitions.id"], ondelete="CASCADE"
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        "ix_connector_installations_connector_definition_id",
        "connector_installations",
        ["connector_definition_id"],
    )
    op.create_index("ix_connector_installations_owner_id", "connector_installations", ["owner_id"])
    op.create_index("ix_connector_installations_company_id", "connector_installations", ["company_id"])

    # Create tool_grants table
    op.create_table(
        "tool_grants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("tool_definition_id", sa.String(), nullable=False),
        sa.Column("subject_type", sa.String(length=64), nullable=False),
        sa.Column("subject_id", sa.String(), nullable=False),
        sa.Column("effect", sa.String(length=16), nullable=False),
        sa.Column("conditions_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["tool_definition_id"], ["tool_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_tool_grants_tool_definition_id", "tool_grants", ["tool_definition_id"])
    op.create_index("ix_tool_grants_subject_type", "tool_grants", ["subject_type"])
    op.create_index("ix_tool_grants_subject_id", "tool_grants", ["subject_id"])

    # Create action_policies table
    op.create_table(
        "action_policies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("scope_type", sa.String(length=64), nullable=False),
        sa.Column("scope_id", sa.String(), nullable=True),
        sa.Column("action_key", sa.String(length=255), nullable=False),
        sa.Column("decision", sa.String(length=64), nullable=False),
        sa.Column("risk_level", sa.String(length=32), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_action_policies_owner_id", "action_policies", ["owner_id"])
    op.create_index("ix_action_policies_company_id", "action_policies", ["company_id"])
    op.create_index("ix_action_policies_scope_id", "action_policies", ["scope_id"])
    op.create_index("ix_action_policies_action_key", "action_policies", ["action_key"])

    # Create workflow_definitions table
    op.create_table(
        "workflow_definitions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("company_id", sa.String(), nullable=True),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("category", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_version_id", sa.String(), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["company_id"], ["companies.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("owner_id", "slug", name="uq_workflow_definitions_owner_slug"),
    )
    op.create_index("ix_workflow_definitions_owner_id", "workflow_definitions", ["owner_id"])
    op.create_index("ix_workflow_definitions_company_id", "workflow_definitions", ["company_id"])
    op.create_index("ix_workflow_definitions_slug", "workflow_definitions", ["slug"])

    # Create workflow_versions table
    op.create_table(
        "workflow_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("nodes_json", sa.JSON(), nullable=False),
        sa.Column("edges_json", sa.JSON(), nullable=False),
        sa.Column("entry_node_id", sa.String(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("is_published", sa.Boolean(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "workflow_id", "version_number", name="uq_workflow_versions_workflow_version"
        ),
    )
    op.create_index("ix_workflow_versions_workflow_id", "workflow_versions", ["workflow_id"])

    # Create workflow_runs table
    op.create_table(
        "workflow_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_id", sa.String(), nullable=False),
        sa.Column("workflow_version_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("current_node_id", sa.String(), nullable=True),
        sa.Column("context_json", sa.JSON(), nullable=False),
        sa.Column("result_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_id"], ["workflow_definitions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["workflow_version_id"], ["workflow_versions.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_runs_workflow_id", "workflow_runs", ["workflow_id"])
    op.create_index("ix_workflow_runs_workflow_version_id", "workflow_runs", ["workflow_version_id"])
    op.create_index("ix_workflow_runs_project_id", "workflow_runs", ["project_id"])
    op.create_index("ix_workflow_runs_task_id", "workflow_runs", ["task_id"])
    op.create_index("ix_workflow_runs_status", "workflow_runs", ["status"])

    # Create workflow_step_runs table
    op.create_table(
        "workflow_step_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("workflow_run_id", sa.String(), nullable=False),
        sa.Column("node_id", sa.String(length=255), nullable=False),
        sa.Column("node_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("input_json", sa.JSON(), nullable=False),
        sa.Column("output_json", sa.JSON(), nullable=False),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["workflow_run_id"], ["workflow_runs.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_workflow_step_runs_workflow_run_id", "workflow_step_runs", ["workflow_run_id"])

    # Create project_analyses table
    op.create_table(
        "project_analyses",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("analyzer_version", sa.String(length=64), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("recommended_tasks_json", sa.JSON(), nullable=False),
        sa.Column("recommended_skills_json", sa.JSON(), nullable=False),
        sa.Column("recommended_agents_json", sa.JSON(), nullable=False),
        sa.Column("recommended_workflow_json", sa.JSON(), nullable=False),
        sa.Column("raw_output_json", sa.JSON(), nullable=False),
        sa.Column("created_by", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_project_analyses_project_id", "project_analyses", ["project_id"])

    # Data migrations
    connection = op.get_bind()

    # 1. Backfill skills from skill_packs
    result = connection.execute(text("SELECT COUNT(*) FROM users")).scalar()
    if result and result > 0:
        # Get the first user ID for skill ownership
        first_user = connection.execute(
            text("SELECT id FROM users ORDER BY created_at LIMIT 1")
        ).scalar()

        if first_user:
            # Fetch all skill_packs
            skill_packs = connection.execute(
                text(
                    """
                    SELECT id, slug, name, description, purpose, rules_markdown,
                           capabilities_json, allowed_tools_json, created_at
                    FROM skill_packs
                    """
                )
            ).fetchall()

            for sp in skill_packs:
                # Create Skill record
                skill_id = connection.execute(
                    text(
                        """
                        INSERT INTO skills (id, owner_id, slug, name, description, scope, status,
                                          legacy_skill_pack_id, created_at, updated_at)
                        VALUES (
                            lower(hex(randomblob(16))),
                            :owner_id, :slug, :name, :description, 'organization', 'active',
                            :skill_pack_id, :created_at, :created_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "owner_id": first_user,
                        "slug": sp[1],
                        "name": sp[2],
                        "description": sp[3] or "",
                        "skill_pack_id": sp[0],
                        "created_at": sp[8],
                    },
                ).scalar()

                # Create SkillVersion record
                version_id = connection.execute(
                    text(
                        """
                        INSERT INTO skill_versions (
                            id, skill_id, version_number, purpose, when_to_use,
                            instructions_markdown, input_schema_json, output_schema_json,
                            capabilities_json, required_tools_json, knowledge_requirements_json,
                            constraints_markdown, risk_level, approval_policy_json, examples_json,
                            evaluation_criteria_json, source_type, source_task_id, source_project_id,
                            generated_by_model, generation_metadata_json, is_published, created_by,
                            created_at
                        )
                        VALUES (
                            lower(hex(randomblob(16))), :skill_id, 1, :purpose, '', :instructions,
                            '{}', '{}', :capabilities, :tools, '[]', '', 'low', '{}', '[]', '[]',
                            'migrated_skill_pack', NULL, NULL, NULL, '{}', 1, NULL, :created_at
                        )
                        RETURNING id
                        """
                    ),
                    {
                        "skill_id": skill_id,
                        "purpose": sp[4] or sp[3] or "",
                        "instructions": sp[5] or "",
                        "capabilities": sp[6] or "[]",
                        "tools": sp[7] or "[]",
                        "created_at": sp[8],
                    },
                ).scalar()

                # Update skills.current_version_id
                connection.execute(
                    text("UPDATE skills SET current_version_id = :version_id WHERE id = :skill_id"),
                    {"version_id": version_id, "skill_id": skill_id},
                )

    # 2. Seed native tool definitions
    native_tools = [
        {
            "slug": "web_search",
            "name": "Web Search",
            "description": "Search the public web",
            "provider_type": "native",
            "risk_level": "low",
            "requires_approval": False,
        },
        {
            "slug": "web_fetch",
            "name": "Web Fetch",
            "description": "Fetch a URL",
            "provider_type": "native",
            "risk_level": "low",
            "requires_approval": False,
        },
        {
            "slug": "knowledge_search",
            "name": "Knowledge Search",
            "description": "Search project/org knowledge",
            "provider_type": "native",
            "risk_level": "low",
            "requires_approval": False,
        },
        {
            "slug": "repo_search",
            "name": "Repository Search",
            "description": "Search linked repositories",
            "provider_type": "native",
            "risk_level": "low",
            "requires_approval": False,
        },
        {
            "slug": "fs_read",
            "name": "Filesystem Read",
            "description": "Read files in workspace",
            "provider_type": "native",
            "risk_level": "low",
            "requires_approval": False,
        },
        {
            "slug": "fs_write",
            "name": "Filesystem Write",
            "description": "Write files in workspace",
            "provider_type": "native",
            "risk_level": "high",
            "requires_approval": True,
        },
        {
            "slug": "code_execute",
            "name": "Code Execute",
            "description": "Execute code in sandbox",
            "provider_type": "native",
            "risk_level": "high",
            "requires_approval": True,
        },
        {
            "slug": "db_query",
            "name": "Database Query",
            "description": "Run read/write DB queries",
            "provider_type": "native",
            "risk_level": "critical",
            "requires_approval": True,
        },
        {
            "slug": "github_comment",
            "name": "GitHub Comment",
            "description": "Comment on GitHub issues/PRs",
            "provider_type": "github",
            "risk_level": "medium",
            "requires_approval": True,
        },
        {
            "slug": "github_label_issue",
            "name": "GitHub Label Issue",
            "description": "Add/remove GitHub issue labels",
            "provider_type": "github",
            "risk_level": "medium",
            "requires_approval": True,
        },
        {
            "slug": "github_create_pr",
            "name": "GitHub Create PR",
            "description": "Open a pull request",
            "provider_type": "github",
            "risk_level": "high",
            "requires_approval": True,
        },
    ]

    for tool in native_tools:
        # Check if tool already exists
        existing = connection.execute(
            text("SELECT id FROM tool_definitions WHERE slug = :slug"), {"slug": tool["slug"]}
        ).scalar()

        if not existing:
            connection.execute(
                text(
                    """
                    INSERT INTO tool_definitions (
                        id, slug, name, description, provider_type, schema_json,
                        risk_level, requires_approval, is_active, metadata_json, created_at
                    )
                    VALUES (
                        lower(hex(randomblob(16))), :slug, :name, :description, :provider_type,
                        '{}', :risk_level, :requires_approval, 1, '{}', datetime('now')
                    )
                    """
                ),
                tool,
            )

    # 3. Backfill agent_skill_assignments from agent_profiles.skills_json
    agents = connection.execute(
        text("SELECT id, skills_json FROM agent_profiles WHERE skills_json IS NOT NULL")
    ).fetchall()

    import json

    for agent_row in agents:
        agent_id, skills_json_str = agent_row[0], agent_row[1]
        if not skills_json_str:
            continue

        try:
            skill_slugs = json.loads(skills_json_str)
            if not isinstance(skill_slugs, list):
                continue
        except (json.JSONDecodeError, TypeError):
            continue

        for slug in skill_slugs:
            # Find skill by slug (prefer first match)
            skill_id = connection.execute(
                text("SELECT id FROM skills WHERE slug = :slug LIMIT 1"), {"slug": slug}
            ).scalar()

            if skill_id:
                # Check if assignment already exists
                existing_assignment = connection.execute(
                    text(
                        """
                        SELECT id FROM agent_skill_assignments
                        WHERE agent_id = :agent_id AND skill_id = :skill_id
                        """
                    ),
                    {"agent_id": agent_id, "skill_id": skill_id},
                ).scalar()

                if not existing_assignment:
                    connection.execute(
                        text(
                            """
                            INSERT INTO agent_skill_assignments (
                                id, agent_id, skill_id, skill_version_id, version_policy,
                                priority, enabled, created_at
                            )
                            VALUES (
                                lower(hex(randomblob(16))), :agent_id, :skill_id, NULL,
                                'latest_active', 100, 1, datetime('now')
                            )
                            """
                        ),
                        {"agent_id": agent_id, "skill_id": skill_id},
                    )


def downgrade() -> None:
    # Drop all new tables in reverse dependency order
    op.drop_table("project_analyses")
    op.drop_table("workflow_step_runs")
    op.drop_table("workflow_runs")
    op.drop_table("workflow_versions")
    op.drop_table("workflow_definitions")
    op.drop_table("action_policies")
    op.drop_table("tool_grants")
    op.drop_table("connector_installations")
    op.drop_table("connector_definitions")
    op.drop_table("tool_definitions")
    op.drop_table("skill_usage_stats")
    op.drop_table("skill_evaluations")
    op.drop_table("task_requirements")
    op.drop_table("task_analyses")
    op.drop_table("agent_skill_assignments")
    op.drop_table("skill_drafts")
    op.drop_table("skill_versions")
    op.drop_table("skills")

    # Drop columns from orchestrator_tasks
    op.drop_index("ix_orchestrator_tasks_reviewer_user_id", table_name="orchestrator_tasks")
    op.drop_index("ix_orchestrator_tasks_human_assignee_id", table_name="orchestrator_tasks")
    op.drop_constraint(
        "fk_orchestrator_tasks_reviewer_user_id_users",
        "orchestrator_tasks",
        type_="foreignkey",
    )
    op.drop_constraint(
        "fk_orchestrator_tasks_human_assignee_id_users",
        "orchestrator_tasks",
        type_="foreignkey",
    )
    for column in (
        "assignment_mode",
        "autonomy_level",
        "risk_level",
        "expected_output",
        "objective",
        "reviewer_user_id",
        "human_assignee_id",
    ):
        op.drop_column("orchestrator_tasks", column)

    # Drop columns from orchestrator_projects
    op.drop_index("ix_orchestrator_projects_department_id", table_name="orchestrator_projects")
    op.drop_constraint(
        "fk_orchestrator_projects_department_id_departments",
        "orchestrator_projects",
        type_="foreignkey",
    )
    for column in ("metadata_json", "budget_json", "knowledge_policy_json", "department_id"):
        op.drop_column("orchestrator_projects", column)

    # Drop departments table
    op.drop_table("departments")
