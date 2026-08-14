"""Workspace role → permission mapping (RBAC-001B)."""

from __future__ import annotations

from typing import Final

WORKSPACE_HEADER_NAME: Final[str] = "X-Workspace-Id"

# Permission strings are stable API for authorization checks.
PERM_PROJECT_READ: Final[str] = "project:read"
PERM_PROJECT_WRITE: Final[str] = "project:write"
PERM_RUN_EXECUTE: Final[str] = "run:execute"
PERM_APPROVAL_DECIDE: Final[str] = "approval:decide"
PERM_WORKFLOW_PUBLISH: Final[str] = "workflow:publish"
PERM_INTEGRATION_MANAGE: Final[str] = "integration:manage"
PERM_WORKSPACE_ADMIN: Final[str] = "workspace:admin"

_ROLE_PERMISSIONS: dict[str, frozenset[str]] = {
    "owner": frozenset(
        {
            PERM_PROJECT_READ,
            PERM_PROJECT_WRITE,
            PERM_RUN_EXECUTE,
            PERM_APPROVAL_DECIDE,
            PERM_WORKFLOW_PUBLISH,
            PERM_INTEGRATION_MANAGE,
            PERM_WORKSPACE_ADMIN,
        }
    ),
    "admin": frozenset(
        {
            PERM_PROJECT_READ,
            PERM_PROJECT_WRITE,
            PERM_RUN_EXECUTE,
            PERM_APPROVAL_DECIDE,
            PERM_WORKFLOW_PUBLISH,
            PERM_INTEGRATION_MANAGE,
            PERM_WORKSPACE_ADMIN,
        }
    ),
    "builder": frozenset(
        {
            PERM_PROJECT_READ,
            PERM_PROJECT_WRITE,
            PERM_RUN_EXECUTE,
            PERM_WORKFLOW_PUBLISH,
            PERM_INTEGRATION_MANAGE,
        }
    ),
    "operator": frozenset({PERM_PROJECT_READ, PERM_RUN_EXECUTE}),
    "approver": frozenset({PERM_PROJECT_READ, PERM_APPROVAL_DECIDE}),
    "viewer": frozenset({PERM_PROJECT_READ}),
}


def permissions_for_role(role: str) -> frozenset[str]:
    return _ROLE_PERMISSIONS.get(role, frozenset())


def role_has_permission(role: str, permission: str) -> bool:
    granted = permissions_for_role(role)
    return permission in granted or PERM_WORKSPACE_ADMIN in granted
