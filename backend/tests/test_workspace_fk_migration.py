"""Tests for workspace FK migration plan (RBAC-001C)."""

from __future__ import annotations

from backend.modules.identity_access.tenant_inventory import (
    inventory_by_phase,
    top_level_tables,
)
from backend.modules.identity_access.workspace_fk_migration import (
    WORKSPACE_COMPOSITE_INDEXES,
    direct_backfill_sql,
    workspace_fk_targets,
)


def test_workspace_fk_targets_cover_all_top_level_except_workspaces() -> None:
    expected = {
        entry.table_name
        for entry in inventory_by_phase("top_level")
        if entry.table_name != "workspaces" and entry.owner_column
    }
    actual = {target.table_name for target in workspace_fk_targets()}
    assert actual == expected


def test_workspace_fk_targets_include_core_tables() -> None:
    tables = {target.table_name for target in workspace_fk_targets()}
    for required in (
        "companies",
        "orchestrator_projects",
        "github_connections",
        "connector_installations",
        "workflow_definitions",
        "skills",
        "ai_documents",
    ):
        assert required in tables


def test_child_tables_are_not_direct_workspace_fk_targets() -> None:
    targets = {target.table_name for target in workspace_fk_targets()}
    for child_only in ("workflow_runs", "departments", "project_analyses"):
        assert child_only not in targets
        assert child_only in {entry.table_name for entry in inventory_by_phase("child")}


def test_direct_backfill_sql_uses_default_workspace() -> None:
    sql = direct_backfill_sql(table_name="orchestrator_projects", owner_column="owner_id")
    assert "UPDATE orchestrator_projects" in sql
    assert "w.is_default IS TRUE" in sql
    assert "t.owner_id" in sql


def test_composite_indexes_target_list_query_tables() -> None:
    indexed_tables = {entry[1] for entry in WORKSPACE_COMPOSITE_INDEXES}
    assert "orchestrator_projects" in indexed_tables
    assert "workflow_definitions" in indexed_tables
    assert all(entry[0].startswith("ix_") for entry in WORKSPACE_COMPOSITE_INDEXES)


def test_top_level_inventory_still_lists_workspaces_root() -> None:
    assert "workspaces" in top_level_tables()
