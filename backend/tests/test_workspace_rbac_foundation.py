"""Tests for workspace RBAC foundation (RBAC-001A)."""

from __future__ import annotations

import pytest
from backend.modules.identity_access.models import Workspace, WorkspaceMembership
from backend.modules.identity_access.tenant_inventory import (
    TENANT_TABLE_INVENTORY,
    inventory_by_phase,
    top_level_tables,
)
from backend.modules.identity_access.workspace_backfill import (
    default_workspace_name,
    default_workspace_slug,
)
from backend.modules.identity_access.workspace_roles import (
    WORKSPACE_ROLE_OWNER,
    WORKSPACE_ROLES,
)


def test_workspace_roles_include_required_set() -> None:
    assert WORKSPACE_ROLE_OWNER in WORKSPACE_ROLES
    assert frozenset(
        {"owner", "admin", "builder", "operator", "approver", "viewer"}
    ) == WORKSPACE_ROLES


def test_default_workspace_name_uses_full_name() -> None:
    assert default_workspace_name(email="a@example.com", full_name="Ada Lovelace") == (
        "Ada Lovelace's workspace"
    )


def test_default_workspace_name_falls_back_to_email_local_part() -> None:
    assert default_workspace_name(email="ada@example.com", full_name=None) == "ada's workspace"


def test_default_workspace_slug_is_stable() -> None:
    assert default_workspace_slug() == "default"


def test_workspace_models_define_unique_constraints() -> None:
    workspace_constraints = {c.name for c in Workspace.__table__.constraints if c.name}
    membership_constraints = {c.name for c in WorkspaceMembership.__table__.constraints if c.name}
    assert "uq_workspaces_owner_slug" in workspace_constraints
    assert "uq_workspace_memberships_workspace_user" in membership_constraints


def test_tenant_inventory_covers_core_top_level_tables() -> None:
    tables = set(top_level_tables())
    for required in (
        "orchestrator_projects",
        "github_connections",
        "connector_installations",
        "workflow_definitions",
        "companies",
        "workspaces",
    ):
        assert required in tables


def test_tenant_inventory_has_no_duplicate_table_names() -> None:
    names = [entry.table_name for entry in TENANT_TABLE_INVENTORY]
    assert len(names) == len(set(names))


@pytest.mark.parametrize("phase", ["top_level", "child", "user_scoped", "platform", "audit"])
def test_inventory_phase_lists_are_non_empty(phase: str) -> None:
    assert inventory_by_phase(phase)  # type: ignore[arg-type]
