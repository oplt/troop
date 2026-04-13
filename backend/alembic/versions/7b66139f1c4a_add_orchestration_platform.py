"""add orchestration platform

Revision ID: 7b66139f1c4a
Revises: 3f1bfc747f3e
Create Date: 2026-04-12 20:30:00.000000

"""
from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

# revision identifiers, used by Alembic.
revision: str = "7b66139f1c4a"
down_revision: str | Sequence[str] | None = "3f1bfc747f3e"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "orchestrator_projects",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("goals_markdown", sa.Text(), nullable=False),
        sa.Column("settings_json", sa.JSON(), nullable=False),
        sa.Column("memory_scope", sa.String(length=64), nullable=False),
        sa.Column("knowledge_summary", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orchestrator_projects_owner_id"), "orchestrator_projects", ["owner_id"], unique=False)
    op.create_index(op.f("ix_orchestrator_projects_slug"), "orchestrator_projects", ["slug"], unique=False)

    op.create_table(
        "provider_configs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("provider_type", sa.String(length=64), nullable=False),
        sa.Column("base_url", sa.String(length=500), nullable=True),
        sa.Column("encrypted_api_key", sa.Text(), nullable=True),
        sa.Column("api_key_hint", sa.String(length=32), nullable=True),
        sa.Column("organization", sa.String(length=255), nullable=True),
        sa.Column("default_model", sa.String(length=255), nullable=False),
        sa.Column("fallback_model", sa.String(length=255), nullable=True),
        sa.Column("temperature", sa.Float(), nullable=False),
        sa.Column("max_tokens", sa.Integer(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("is_default", sa.Boolean(), nullable=False),
        sa.Column("is_enabled", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_healthcheck_status", sa.String(length=32), nullable=True),
        sa.Column("last_healthcheck_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_provider_configs_owner_id"), "provider_configs", ["owner_id"], unique=False)
    op.create_index(op.f("ix_provider_configs_project_id"), "provider_configs", ["project_id"], unique=False)

    op.create_table(
        "agent_profiles",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("parent_agent_id", sa.String(), nullable=True),
        sa.Column("reviewer_agent_id", sa.String(), nullable=True),
        sa.Column("provider_config_id", sa.String(), nullable=True),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("slug", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("system_prompt", sa.Text(), nullable=False),
        sa.Column("mission_markdown", sa.Text(), nullable=False),
        sa.Column("rules_markdown", sa.Text(), nullable=False),
        sa.Column("output_contract_markdown", sa.Text(), nullable=False),
        sa.Column("source_markdown", sa.Text(), nullable=False),
        sa.Column("capabilities_json", sa.JSON(), nullable=False),
        sa.Column("allowed_tools_json", sa.JSON(), nullable=False),
        sa.Column("model_policy_json", sa.JSON(), nullable=False),
        sa.Column("visibility", sa.String(length=32), nullable=False),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("tags_json", sa.JSON(), nullable=False),
        sa.Column("budget_json", sa.JSON(), nullable=False),
        sa.Column("timeout_seconds", sa.Integer(), nullable=False),
        sa.Column("retry_limit", sa.Integer(), nullable=False),
        sa.Column("memory_policy_json", sa.JSON(), nullable=False),
        sa.Column("output_schema_json", sa.JSON(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_config_id"], ["provider_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_profiles_owner_id"), "agent_profiles", ["owner_id"], unique=False)
    op.create_index(op.f("ix_agent_profiles_project_id"), "agent_profiles", ["project_id"], unique=False)
    op.create_index(op.f("ix_agent_profiles_slug"), "agent_profiles", ["slug"], unique=False)
    op.create_index(op.f("ix_agent_profiles_parent_agent_id"), "agent_profiles", ["parent_agent_id"], unique=False)
    op.create_index(op.f("ix_agent_profiles_reviewer_agent_id"), "agent_profiles", ["reviewer_agent_id"], unique=False)
    op.create_index(op.f("ix_agent_profiles_provider_config_id"), "agent_profiles", ["provider_config_id"], unique=False)

    op.create_table(
        "agent_profile_versions",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("agent_profile_id", sa.String(), nullable=False),
        sa.Column("version_number", sa.Integer(), nullable=False),
        sa.Column("source_markdown", sa.Text(), nullable=False),
        sa.Column("snapshot_json", sa.JSON(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_profile_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_agent_profile_versions_agent_profile_id"), "agent_profile_versions", ["agent_profile_id"], unique=False)
    op.create_index(op.f("ix_agent_profile_versions_created_by_user_id"), "agent_profile_versions", ["created_by_user_id"], unique=False)

    op.create_table(
        "project_agent_memberships",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("role", sa.String(length=64), nullable=False),
        sa.Column("is_default_manager", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_agent_memberships_project_id"), "project_agent_memberships", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_agent_memberships_agent_id"), "project_agent_memberships", ["agent_id"], unique=False)

    op.create_table(
        "github_connections",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("owner_id", sa.String(), nullable=False),
        sa.Column("name", sa.String(length=255), nullable=False),
        sa.Column("api_url", sa.String(length=500), nullable=False),
        sa.Column("encrypted_token", sa.Text(), nullable=False),
        sa.Column("token_hint", sa.String(length=32), nullable=True),
        sa.Column("account_login", sa.String(length=255), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_github_connections_owner_id"), "github_connections", ["owner_id"], unique=False)

    op.create_table(
        "github_repositories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("connection_id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("owner_name", sa.String(length=255), nullable=False),
        sa.Column("repo_name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("repo_url", sa.String(length=1000), nullable=True),
        sa.Column("is_active", sa.Boolean(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["connection_id"], ["github_connections.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_github_repositories_connection_id"), "github_repositories", ["connection_id"], unique=False)
    op.create_index(op.f("ix_github_repositories_project_id"), "github_repositories", ["project_id"], unique=False)
    op.create_index(op.f("ix_github_repositories_full_name"), "github_repositories", ["full_name"], unique=False)

    op.create_table(
        "project_repositories",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("github_repository_id", sa.String(), nullable=True),
        sa.Column("provider", sa.String(length=32), nullable=False),
        sa.Column("owner_name", sa.String(length=255), nullable=False),
        sa.Column("repo_name", sa.String(length=255), nullable=False),
        sa.Column("full_name", sa.String(length=255), nullable=False),
        sa.Column("default_branch", sa.String(length=255), nullable=True),
        sa.Column("repository_url", sa.String(length=1000), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["github_repository_id"], ["github_repositories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_repositories_project_id"), "project_repositories", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_repositories_github_repository_id"), "project_repositories", ["github_repository_id"], unique=False)

    op.create_table(
        "orchestrator_tasks",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("created_by_user_id", sa.String(), nullable=False),
        sa.Column("assigned_agent_id", sa.String(), nullable=True),
        sa.Column("reviewer_agent_id", sa.String(), nullable=True),
        sa.Column("github_issue_link_id", sa.String(), nullable=True),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("description", sa.Text(), nullable=True),
        sa.Column("source", sa.String(length=32), nullable=False),
        sa.Column("task_type", sa.String(length=64), nullable=False),
        sa.Column("priority", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("acceptance_criteria", sa.Text(), nullable=True),
        sa.Column("due_date", sa.DateTime(timezone=True), nullable=True),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("result_summary", sa.Text(), nullable=True),
        sa.Column("result_payload_json", sa.JSON(), nullable=False),
        sa.Column("position", sa.Integer(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["assigned_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["created_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["reviewer_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_orchestrator_tasks_project_id"), "orchestrator_tasks", ["project_id"], unique=False)
    op.create_index(op.f("ix_orchestrator_tasks_created_by_user_id"), "orchestrator_tasks", ["created_by_user_id"], unique=False)
    op.create_index(op.f("ix_orchestrator_tasks_assigned_agent_id"), "orchestrator_tasks", ["assigned_agent_id"], unique=False)
    op.create_index(op.f("ix_orchestrator_tasks_reviewer_agent_id"), "orchestrator_tasks", ["reviewer_agent_id"], unique=False)
    op.create_index(op.f("ix_orchestrator_tasks_github_issue_link_id"), "orchestrator_tasks", ["github_issue_link_id"], unique=False)
    op.create_index(op.f("ix_orchestrator_tasks_status"), "orchestrator_tasks", ["status"], unique=False)

    op.create_table(
        "brainstorms",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("initiator_user_id", sa.String(), nullable=False),
        sa.Column("moderator_agent_id", sa.String(), nullable=True),
        sa.Column("topic", sa.String(length=255), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("max_rounds", sa.Integer(), nullable=False),
        sa.Column("stop_conditions_json", sa.JSON(), nullable=False),
        sa.Column("summary", sa.Text(), nullable=True),
        sa.Column("final_recommendation", sa.Text(), nullable=True),
        sa.Column("decision_log_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["initiator_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["moderator_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brainstorms_project_id"), "brainstorms", ["project_id"], unique=False)
    op.create_index(op.f("ix_brainstorms_task_id"), "brainstorms", ["task_id"], unique=False)
    op.create_index(op.f("ix_brainstorms_initiator_user_id"), "brainstorms", ["initiator_user_id"], unique=False)
    op.create_index(op.f("ix_brainstorms_moderator_agent_id"), "brainstorms", ["moderator_agent_id"], unique=False)

    op.create_table(
        "brainstorm_participants",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("brainstorm_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=False),
        sa.Column("order_index", sa.Integer(), nullable=False),
        sa.Column("stance", sa.Text(), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["brainstorm_id"], ["brainstorms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brainstorm_participants_brainstorm_id"), "brainstorm_participants", ["brainstorm_id"], unique=False)
    op.create_index(op.f("ix_brainstorm_participants_agent_id"), "brainstorm_participants", ["agent_id"], unique=False)

    op.create_table(
        "brainstorm_messages",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("brainstorm_id", sa.String(), nullable=False),
        sa.Column("agent_id", sa.String(), nullable=True),
        sa.Column("round_number", sa.Integer(), nullable=False),
        sa.Column("message_type", sa.String(length=32), nullable=False),
        sa.Column("content", sa.Text(), nullable=False),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["brainstorm_id"], ["brainstorms.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_brainstorm_messages_brainstorm_id"), "brainstorm_messages", ["brainstorm_id"], unique=False)
    op.create_index(op.f("ix_brainstorm_messages_agent_id"), "brainstorm_messages", ["agent_id"], unique=False)

    op.create_table(
        "task_runs",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("triggered_by_user_id", sa.String(), nullable=True),
        sa.Column("orchestrator_agent_id", sa.String(), nullable=True),
        sa.Column("worker_agent_id", sa.String(), nullable=True),
        sa.Column("reviewer_agent_id", sa.String(), nullable=True),
        sa.Column("provider_config_id", sa.String(), nullable=True),
        sa.Column("brainstorm_id", sa.String(), nullable=True),
        sa.Column("run_mode", sa.String(length=32), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("model_name", sa.String(length=255), nullable=True),
        sa.Column("attempt_number", sa.Integer(), nullable=False),
        sa.Column("token_input", sa.Integer(), nullable=False),
        sa.Column("token_output", sa.Integer(), nullable=False),
        sa.Column("token_total", sa.Integer(), nullable=False),
        sa.Column("estimated_cost_micros", sa.Integer(), nullable=False),
        sa.Column("latency_ms", sa.Integer(), nullable=True),
        sa.Column("error_message", sa.Text(), nullable=True),
        sa.Column("retry_count", sa.Integer(), nullable=False),
        sa.Column("checkpoint_json", sa.JSON(), nullable=False),
        sa.Column("input_payload_json", sa.JSON(), nullable=False),
        sa.Column("output_payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("cancelled_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["brainstorm_id"], ["brainstorms.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["orchestrator_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["provider_config_id"], ["provider_configs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["reviewer_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["triggered_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["worker_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_runs_project_id"), "task_runs", ["project_id"], unique=False)
    op.create_index(op.f("ix_task_runs_task_id"), "task_runs", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_runs_triggered_by_user_id"), "task_runs", ["triggered_by_user_id"], unique=False)
    op.create_index(op.f("ix_task_runs_orchestrator_agent_id"), "task_runs", ["orchestrator_agent_id"], unique=False)
    op.create_index(op.f("ix_task_runs_worker_agent_id"), "task_runs", ["worker_agent_id"], unique=False)
    op.create_index(op.f("ix_task_runs_reviewer_agent_id"), "task_runs", ["reviewer_agent_id"], unique=False)
    op.create_index(op.f("ix_task_runs_provider_config_id"), "task_runs", ["provider_config_id"], unique=False)
    op.create_index(op.f("ix_task_runs_brainstorm_id"), "task_runs", ["brainstorm_id"], unique=False)
    op.create_index(op.f("ix_task_runs_status"), "task_runs", ["status"], unique=False)

    op.create_table(
        "run_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("level", sa.String(length=16), nullable=False),
        sa.Column("event_type", sa.String(length=64), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["task_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_run_events_run_id"), "run_events", ["run_id"], unique=False)
    op.create_index(op.f("ix_run_events_task_id"), "run_events", ["task_id"], unique=False)
    op.create_index(op.f("ix_run_events_created_at"), "run_events", ["created_at"], unique=False)

    op.create_table(
        "task_comments",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("author_user_id", sa.String(), nullable=True),
        sa.Column("author_agent_id", sa.String(), nullable=True),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["author_agent_id"], ["agent_profiles.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["author_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_comments_task_id"), "task_comments", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_comments_author_user_id"), "task_comments", ["author_user_id"], unique=False)
    op.create_index(op.f("ix_task_comments_author_agent_id"), "task_comments", ["author_agent_id"], unique=False)

    op.create_table(
        "task_artifacts",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("kind", sa.String(length=64), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("content", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["run_id"], ["task_runs.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_artifacts_task_id"), "task_artifacts", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_artifacts_run_id"), "task_artifacts", ["run_id"], unique=False)

    op.create_table(
        "project_documents",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("uploaded_by_user_id", sa.String(), nullable=False),
        sa.Column("filename", sa.String(length=255), nullable=False),
        sa.Column("content_type", sa.String(length=128), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("object_key", sa.String(length=500), nullable=True),
        sa.Column("size_bytes", sa.Integer(), nullable=False),
        sa.Column("summary_text", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["uploaded_by_user_id"], ["users.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_project_documents_project_id"), "project_documents", ["project_id"], unique=False)
    op.create_index(op.f("ix_project_documents_task_id"), "project_documents", ["task_id"], unique=False)
    op.create_index(op.f("ix_project_documents_uploaded_by_user_id"), "project_documents", ["uploaded_by_user_id"], unique=False)

    op.create_table(
        "task_dependencies",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=False),
        sa.Column("depends_on_task_id", sa.String(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["depends_on_task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_task_dependencies_task_id"), "task_dependencies", ["task_id"], unique=False)
    op.create_index(op.f("ix_task_dependencies_depends_on_task_id"), "task_dependencies", ["depends_on_task_id"], unique=False)

    op.create_table(
        "github_issue_links",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("repository_id", sa.String(), nullable=False),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("issue_number", sa.Integer(), nullable=False),
        sa.Column("title", sa.String(length=255), nullable=False),
        sa.Column("body", sa.Text(), nullable=True),
        sa.Column("state", sa.String(length=32), nullable=False),
        sa.Column("labels_json", sa.JSON(), nullable=False),
        sa.Column("assignee_login", sa.String(length=255), nullable=True),
        sa.Column("issue_url", sa.String(length=1000), nullable=True),
        sa.Column("sync_status", sa.String(length=32), nullable=False),
        sa.Column("last_comment_posted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_synced_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_error", sa.Text(), nullable=True),
        sa.Column("metadata_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["repository_id"], ["github_repositories.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="SET NULL"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_github_issue_links_repository_id"), "github_issue_links", ["repository_id"], unique=False)
    op.create_index(op.f("ix_github_issue_links_task_id"), "github_issue_links", ["task_id"], unique=False)

    op.create_foreign_key(
        "fk_orchestrator_tasks_github_issue_link_id",
        "orchestrator_tasks",
        "github_issue_links",
        ["github_issue_link_id"],
        ["id"],
        ondelete="SET NULL",
    )

    op.create_table(
        "github_sync_events",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("repository_id", sa.String(), nullable=True),
        sa.Column("issue_link_id", sa.String(), nullable=True),
        sa.Column("action", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("detail", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["issue_link_id"], ["github_issue_links.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["repository_id"], ["github_repositories.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_github_sync_events_repository_id"), "github_sync_events", ["repository_id"], unique=False)
    op.create_index(op.f("ix_github_sync_events_issue_link_id"), "github_sync_events", ["issue_link_id"], unique=False)

    op.create_table(
        "approval_requests",
        sa.Column("id", sa.String(), nullable=False),
        sa.Column("project_id", sa.String(), nullable=True),
        sa.Column("task_id", sa.String(), nullable=True),
        sa.Column("run_id", sa.String(), nullable=True),
        sa.Column("issue_link_id", sa.String(), nullable=True),
        sa.Column("requested_by_user_id", sa.String(), nullable=True),
        sa.Column("approved_by_user_id", sa.String(), nullable=True),
        sa.Column("approval_type", sa.String(length=64), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("reason", sa.Text(), nullable=True),
        sa.Column("payload_json", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("resolved_at", sa.DateTime(timezone=True), nullable=True),
        sa.ForeignKeyConstraint(["approved_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["issue_link_id"], ["github_issue_links.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["project_id"], ["orchestrator_projects.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["requested_by_user_id"], ["users.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["run_id"], ["task_runs.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["task_id"], ["orchestrator_tasks.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(op.f("ix_approval_requests_project_id"), "approval_requests", ["project_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_task_id"), "approval_requests", ["task_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_run_id"), "approval_requests", ["run_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_issue_link_id"), "approval_requests", ["issue_link_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_requested_by_user_id"), "approval_requests", ["requested_by_user_id"], unique=False)
    op.create_index(op.f("ix_approval_requests_approved_by_user_id"), "approval_requests", ["approved_by_user_id"], unique=False)


def downgrade() -> None:
    op.drop_index(op.f("ix_approval_requests_approved_by_user_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_requested_by_user_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_issue_link_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_run_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_task_id"), table_name="approval_requests")
    op.drop_index(op.f("ix_approval_requests_project_id"), table_name="approval_requests")
    op.drop_table("approval_requests")
    op.drop_index(op.f("ix_github_sync_events_issue_link_id"), table_name="github_sync_events")
    op.drop_index(op.f("ix_github_sync_events_repository_id"), table_name="github_sync_events")
    op.drop_table("github_sync_events")
    op.drop_constraint("fk_orchestrator_tasks_github_issue_link_id", "orchestrator_tasks", type_="foreignkey")
    op.drop_index(op.f("ix_github_issue_links_task_id"), table_name="github_issue_links")
    op.drop_index(op.f("ix_github_issue_links_repository_id"), table_name="github_issue_links")
    op.drop_table("github_issue_links")
    op.drop_index(op.f("ix_task_dependencies_depends_on_task_id"), table_name="task_dependencies")
    op.drop_index(op.f("ix_task_dependencies_task_id"), table_name="task_dependencies")
    op.drop_table("task_dependencies")
    op.drop_index(op.f("ix_project_documents_uploaded_by_user_id"), table_name="project_documents")
    op.drop_index(op.f("ix_project_documents_task_id"), table_name="project_documents")
    op.drop_index(op.f("ix_project_documents_project_id"), table_name="project_documents")
    op.drop_table("project_documents")
    op.drop_index(op.f("ix_task_artifacts_run_id"), table_name="task_artifacts")
    op.drop_index(op.f("ix_task_artifacts_task_id"), table_name="task_artifacts")
    op.drop_table("task_artifacts")
    op.drop_index(op.f("ix_task_comments_author_agent_id"), table_name="task_comments")
    op.drop_index(op.f("ix_task_comments_author_user_id"), table_name="task_comments")
    op.drop_index(op.f("ix_task_comments_task_id"), table_name="task_comments")
    op.drop_table("task_comments")
    op.drop_index(op.f("ix_run_events_created_at"), table_name="run_events")
    op.drop_index(op.f("ix_run_events_task_id"), table_name="run_events")
    op.drop_index(op.f("ix_run_events_run_id"), table_name="run_events")
    op.drop_table("run_events")
    op.drop_index(op.f("ix_task_runs_status"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_brainstorm_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_provider_config_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_reviewer_agent_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_worker_agent_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_orchestrator_agent_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_triggered_by_user_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_task_id"), table_name="task_runs")
    op.drop_index(op.f("ix_task_runs_project_id"), table_name="task_runs")
    op.drop_table("task_runs")
    op.drop_index(op.f("ix_brainstorm_messages_agent_id"), table_name="brainstorm_messages")
    op.drop_index(op.f("ix_brainstorm_messages_brainstorm_id"), table_name="brainstorm_messages")
    op.drop_table("brainstorm_messages")
    op.drop_index(op.f("ix_brainstorm_participants_agent_id"), table_name="brainstorm_participants")
    op.drop_index(op.f("ix_brainstorm_participants_brainstorm_id"), table_name="brainstorm_participants")
    op.drop_table("brainstorm_participants")
    op.drop_index(op.f("ix_brainstorms_moderator_agent_id"), table_name="brainstorms")
    op.drop_index(op.f("ix_brainstorms_initiator_user_id"), table_name="brainstorms")
    op.drop_index(op.f("ix_brainstorms_task_id"), table_name="brainstorms")
    op.drop_index(op.f("ix_brainstorms_project_id"), table_name="brainstorms")
    op.drop_table("brainstorms")
    op.drop_index(op.f("ix_orchestrator_tasks_status"), table_name="orchestrator_tasks")
    op.drop_index(op.f("ix_orchestrator_tasks_github_issue_link_id"), table_name="orchestrator_tasks")
    op.drop_index(op.f("ix_orchestrator_tasks_reviewer_agent_id"), table_name="orchestrator_tasks")
    op.drop_index(op.f("ix_orchestrator_tasks_assigned_agent_id"), table_name="orchestrator_tasks")
    op.drop_index(op.f("ix_orchestrator_tasks_created_by_user_id"), table_name="orchestrator_tasks")
    op.drop_index(op.f("ix_orchestrator_tasks_project_id"), table_name="orchestrator_tasks")
    op.drop_table("orchestrator_tasks")
    op.drop_index(op.f("ix_project_repositories_github_repository_id"), table_name="project_repositories")
    op.drop_index(op.f("ix_project_repositories_project_id"), table_name="project_repositories")
    op.drop_table("project_repositories")
    op.drop_index(op.f("ix_github_repositories_full_name"), table_name="github_repositories")
    op.drop_index(op.f("ix_github_repositories_project_id"), table_name="github_repositories")
    op.drop_index(op.f("ix_github_repositories_connection_id"), table_name="github_repositories")
    op.drop_table("github_repositories")
    op.drop_index(op.f("ix_github_connections_owner_id"), table_name="github_connections")
    op.drop_table("github_connections")
    op.drop_index(op.f("ix_project_agent_memberships_agent_id"), table_name="project_agent_memberships")
    op.drop_index(op.f("ix_project_agent_memberships_project_id"), table_name="project_agent_memberships")
    op.drop_table("project_agent_memberships")
    op.drop_index(op.f("ix_agent_profile_versions_created_by_user_id"), table_name="agent_profile_versions")
    op.drop_index(op.f("ix_agent_profile_versions_agent_profile_id"), table_name="agent_profile_versions")
    op.drop_table("agent_profile_versions")
    op.drop_index(op.f("ix_agent_profiles_provider_config_id"), table_name="agent_profiles")
    op.drop_index(op.f("ix_agent_profiles_reviewer_agent_id"), table_name="agent_profiles")
    op.drop_index(op.f("ix_agent_profiles_parent_agent_id"), table_name="agent_profiles")
    op.drop_index(op.f("ix_agent_profiles_slug"), table_name="agent_profiles")
    op.drop_index(op.f("ix_agent_profiles_project_id"), table_name="agent_profiles")
    op.drop_index(op.f("ix_agent_profiles_owner_id"), table_name="agent_profiles")
    op.drop_table("agent_profiles")
    op.drop_index(op.f("ix_provider_configs_project_id"), table_name="provider_configs")
    op.drop_index(op.f("ix_provider_configs_owner_id"), table_name="provider_configs")
    op.drop_table("provider_configs")
    op.drop_index(op.f("ix_orchestrator_projects_slug"), table_name="orchestrator_projects")
    op.drop_index(op.f("ix_orchestrator_projects_owner_id"), table_name="orchestrator_projects")
    op.drop_table("orchestrator_projects")
