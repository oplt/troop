"""Workspace RBAC role definitions (RBAC-001A foundation)."""

from __future__ import annotations

from typing import Final

WORKSPACE_ROLE_OWNER: Final[str] = "owner"
WORKSPACE_ROLE_ADMIN: Final[str] = "admin"
WORKSPACE_ROLE_BUILDER: Final[str] = "builder"
WORKSPACE_ROLE_OPERATOR: Final[str] = "operator"
WORKSPACE_ROLE_APPROVER: Final[str] = "approver"
WORKSPACE_ROLE_VIEWER: Final[str] = "viewer"

WORKSPACE_ROLES: frozenset[str] = frozenset(
    {
        WORKSPACE_ROLE_OWNER,
        WORKSPACE_ROLE_ADMIN,
        WORKSPACE_ROLE_BUILDER,
        WORKSPACE_ROLE_OPERATOR,
        WORKSPACE_ROLE_APPROVER,
        WORKSPACE_ROLE_VIEWER,
    }
)

WORKSPACE_MEMBERSHIP_ACTIVE: Final[str] = "active"
WORKSPACE_MEMBERSHIP_INVITED: Final[str] = "invited"
WORKSPACE_MEMBERSHIP_SUSPENDED: Final[str] = "suspended"

WORKSPACE_MEMBERSHIP_STATUSES: frozenset[str] = frozenset(
    {
        WORKSPACE_MEMBERSHIP_ACTIVE,
        WORKSPACE_MEMBERSHIP_INVITED,
        WORKSPACE_MEMBERSHIP_SUSPENDED,
    }
)

DEFAULT_WORKSPACE_SLUG: Final[str] = "default"
