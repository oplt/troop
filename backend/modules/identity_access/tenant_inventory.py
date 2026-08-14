"""Inventory of tenant-owned tables for workspace_id migration (RBAC-001A).

Phase ``top_level`` tables receive a nullable ``workspace_id`` in RBAC-001C.
Phase ``child`` rows inherit workspace scope through a parent FK.
Phase ``user_scoped`` remain user-bound (sessions, preferences).
Phase ``platform`` are global catalog rows.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

MigrationPhase = Literal["top_level", "child", "user_scoped", "platform", "audit"]


@dataclass(frozen=True)
class TenantTableInventoryEntry:
    table_name: str
    owner_column: str | None
    phase: MigrationPhase
    parent_table: str | None = None
    parent_fk_column: str | None = None
    notes: str = ""


TENANT_TABLE_INVENTORY: tuple[TenantTableInventoryEntry, ...] = (
    # --- Top-level workspace candidates (backfill workspace_id from owner_user_id) ---
    TenantTableInventoryEntry("companies", "owner_id", "top_level"),
    TenantTableInventoryEntry("orchestrator_projects", "owner_id", "top_level"),
    TenantTableInventoryEntry("projects", "owner_id", "top_level"),
    TenantTableInventoryEntry("agent_profiles", "owner_id", "top_level"),
    TenantTableInventoryEntry("team_profiles", "owner_id", "top_level"),
    TenantTableInventoryEntry("skill_packs", "owner_id", "top_level"),
    TenantTableInventoryEntry("team_templates", "owner_id", "top_level"),
    TenantTableInventoryEntry("agent_templates", "owner_id", "top_level"),
    TenantTableInventoryEntry("provider_configs", "owner_id", "top_level"),
    TenantTableInventoryEntry("github_connections", "owner_id", "top_level"),
    TenantTableInventoryEntry("connector_installations", "owner_id", "top_level"),
    TenantTableInventoryEntry("connector_oauth_states", "owner_id", "top_level"),
    TenantTableInventoryEntry("trigger_subscriptions", "owner_id", "top_level"),
    TenantTableInventoryEntry("external_events", "owner_id", "top_level"),
    TenantTableInventoryEntry("workflow_definitions", "owner_id", "top_level"),
    TenantTableInventoryEntry("action_policies", "owner_id", "top_level"),
    TenantTableInventoryEntry("skills", "owner_id", "top_level"),
    TenantTableInventoryEntry("procedural_playbooks", "owner_id", "top_level"),
    TenantTableInventoryEntry("memory_ingest_jobs", "owner_id", "top_level"),
    TenantTableInventoryEntry("episodic_archive_manifests", "owner_id", "top_level"),
    TenantTableInventoryEntry("episodic_search_index", "owner_id", "top_level"),
    TenantTableInventoryEntry("knowledge_graph_edges", "owner_id", "top_level"),
    TenantTableInventoryEntry("semantic_memory_links", "owner_id", "top_level"),
    TenantTableInventoryEntry(
        "ai_prompt_templates",
        "user_id",
        "top_level",
        notes="Rename scope to workspace in RBAC-001C",
    ),
    TenantTableInventoryEntry("ai_documents", "user_id", "top_level"),
    TenantTableInventoryEntry("ai_runs", "user_id", "top_level"),
    TenantTableInventoryEntry("ai_evaluation_datasets", "user_id", "top_level"),
    TenantTableInventoryEntry("calendar_entries", "user_id", "top_level"),
    TenantTableInventoryEntry("api_keys", "user_id", "top_level"),
    TenantTableInventoryEntry("webhook_endpoints", "user_id", "top_level"),
    # --- Child rows (workspace via parent) ---
    TenantTableInventoryEntry(
        "orchestrator_tasks",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    TenantTableInventoryEntry(
        "task_runs",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    TenantTableInventoryEntry(
        "approval_requests",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
        notes="Nullable project_id rows fall back to requested_by_user_id default workspace",
    ),
    TenantTableInventoryEntry(
        "workflow_runs",
        None,
        "child",
        parent_table="workflow_definitions",
        parent_fk_column="workflow_id",
    ),
    TenantTableInventoryEntry(
        "departments",
        None,
        "child",
        parent_table="companies",
        parent_fk_column="company_id",
    ),
    TenantTableInventoryEntry(
        "project_analyses",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    TenantTableInventoryEntry(
        "github_repositories",
        None,
        "child",
        parent_table="github_connections",
        parent_fk_column="connection_id",
    ),
    TenantTableInventoryEntry(
        "github_issue_links",
        None,
        "child",
        parent_table="github_repositories",
        parent_fk_column="repository_id",
    ),
    TenantTableInventoryEntry(
        "github_sync_events",
        None,
        "child",
        parent_table="github_repositories",
        parent_fk_column="repository_id",
    ),
    TenantTableInventoryEntry(
        "github_entity_mappings",
        None,
        "child",
        parent_table="github_repositories",
        parent_fk_column="repository_id",
    ),
    TenantTableInventoryEntry(
        "github_outbound_dedup",
        "owner_id",
        "child",
        notes="Denormalized owner_id; workspace via issue_link in RBAC-001C",
    ),
    TenantTableInventoryEntry(
        "connector_operations",
        None,
        "child",
        parent_table="connector_installations",
        parent_fk_column="connector_installation_id",
    ),
    TenantTableInventoryEntry(
        "approval_deliveries",
        None,
        "child",
        parent_table="approval_requests",
        parent_fk_column="approval_request_id",
    ),
    TenantTableInventoryEntry(
        "draft_execution_metadata",
        "owner_id",
        "child",
        parent_table="connector_installations",
        parent_fk_column="connector_installation_id",
    ),
    TenantTableInventoryEntry(
        "external_action_executions",
        "owner_id",
        "child",
        notes="Workspace via connector_installation or approval_request",
    ),
    TenantTableInventoryEntry(
        "workflow_versions",
        None,
        "child",
        parent_table="workflow_definitions",
        parent_fk_column="workflow_definition_id",
    ),
    TenantTableInventoryEntry(
        "workflow_step_runs",
        None,
        "child",
        parent_table="workflow_runs",
        parent_fk_column="workflow_run_id",
    ),
    TenantTableInventoryEntry(
        "project_documents",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    TenantTableInventoryEntry(
        "agent_memory_entries",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    TenantTableInventoryEntry(
        "semantic_memory_entries",
        "owner_id",
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    TenantTableInventoryEntry(
        "skill_versions",
        None,
        "child",
        parent_table="skills",
        parent_fk_column="skill_id",
    ),
    TenantTableInventoryEntry(
        "skill_drafts",
        "owner_id",
        "child",
        parent_table="skills",
        parent_fk_column="skill_id",
    ),
    TenantTableInventoryEntry(
        "run_events",
        None,
        "child",
        parent_table="task_runs",
        parent_fk_column="run_id",
    ),
    TenantTableInventoryEntry(
        "eval_records",
        None,
        "child",
        parent_table="orchestrator_projects",
        parent_fk_column="project_id",
    ),
    # --- User-scoped (no workspace_id) ---
    TenantTableInventoryEntry("users", None, "user_scoped"),
    TenantTableInventoryEntry("refresh_sessions", "user_id", "user_scoped"),
    TenantTableInventoryEntry("user_profiles", "user_id", "user_scoped"),
    TenantTableInventoryEntry("notifications", "user_id", "user_scoped"),
    TenantTableInventoryEntry("notification_preferences", "user_id", "user_scoped"),
    TenantTableInventoryEntry("user_subscriptions", "user_id", "user_scoped"),
    # --- Platform / catalog ---
    TenantTableInventoryEntry(
        "tool_definitions",
        None,
        "platform",
        notes="Global native tool catalog",
    ),
    TenantTableInventoryEntry("connector_definitions", None, "platform"),
    TenantTableInventoryEntry("subscription_plans", None, "platform"),
    TenantTableInventoryEntry("feature_flags", None, "platform"),
    TenantTableInventoryEntry("email_templates", None, "platform"),
    TenantTableInventoryEntry("app_settings", None, "platform"),
    TenantTableInventoryEntry(
        "model_capabilities",
        None,
        "platform",
        parent_table="provider_configs",
    ),
    # --- Audit ---
    TenantTableInventoryEntry(
        "audit_logs",
        "user_id",
        "audit",
        notes="Actor user; workspace_id optional later",
    ),
    # --- New RBAC tables ---
    TenantTableInventoryEntry("workspaces", "owner_user_id", "top_level", notes="RBAC tenant root"),
    TenantTableInventoryEntry(
        "workspace_memberships",
        "user_id",
        "child",
        parent_table="workspaces",
        parent_fk_column="workspace_id",
    ),
)


def inventory_by_phase(phase: MigrationPhase) -> list[TenantTableInventoryEntry]:
    return [entry for entry in TENANT_TABLE_INVENTORY if entry.phase == phase]


def top_level_tables() -> list[str]:
    return [entry.table_name for entry in inventory_by_phase("top_level")]


def inventory_table_names() -> frozenset[str]:
    return frozenset(entry.table_name for entry in TENANT_TABLE_INVENTORY)
