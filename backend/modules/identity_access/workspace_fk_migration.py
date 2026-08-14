"""Workspace FK rollout helpers for RBAC-001C."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from backend.modules.identity_access.tenant_inventory import inventory_by_phase


@dataclass(frozen=True, slots=True)
class WorkspaceFkTarget:
    table_name: str
    owner_column: str


def workspace_fk_targets() -> tuple[WorkspaceFkTarget, ...]:
    """Top-level tables that receive a direct ``workspace_id`` column."""
    targets: list[WorkspaceFkTarget] = []
    for entry in inventory_by_phase("top_level"):
        if entry.table_name == "workspaces":
            continue
        if not entry.owner_column:
            raise ValueError(
                f"top_level table {entry.table_name!r} missing owner_column for RBAC-001C"
            )
        targets.append(WorkspaceFkTarget(entry.table_name, entry.owner_column))
    return tuple(targets)


def direct_backfill_sql(*, table_name: str, owner_column: str) -> str:
    """Backfill ``workspace_id`` from the owner's default workspace."""
    return f"""
        UPDATE {table_name} AS t
        SET workspace_id = w.id
        FROM workspaces AS w
        WHERE w.owner_user_id = t.{owner_column}
          AND w.is_default IS TRUE
          AND t.workspace_id IS NULL
    """


def null_workspace_count_sql(table_name: str) -> str:
    return f"SELECT COUNT(*) FROM {table_name} WHERE workspace_id IS NULL"


# Composite indexes validated against workspace-scoped list query patterns.
# See backend/docs/RBAC_WORKSPACE_MIGRATION.md (RBAC-001C index notes).
WORKSPACE_COMPOSITE_INDEXES: Final[
    tuple[tuple[str, str, tuple[str, ...], dict[str, str] | None], ...]
] = (
    (
        "ix_orchestrator_projects_workspace_status_created",
        "orchestrator_projects",
        ("workspace_id", "status", "created_at"),
        {"created_at": "DESC"},
    ),
    (
        "ix_workflow_definitions_workspace_status_created",
        "workflow_definitions",
        ("workspace_id", "status", "created_at"),
        {"created_at": "DESC"},
    ),
    (
        "ix_connector_installations_workspace_status_created",
        "connector_installations",
        ("workspace_id", "status", "created_at"),
        {"created_at": "DESC"},
    ),
    (
        "ix_skills_workspace_status_created",
        "skills",
        ("workspace_id", "status", "created_at"),
        {"created_at": "DESC"},
    ),
    (
        "ix_external_events_workspace_status_received",
        "external_events",
        ("workspace_id", "status", "received_at"),
        {"received_at": "DESC"},
    ),
)
