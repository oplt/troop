"""Pure helpers for default workspace bootstrap (RBAC-001A)."""

from __future__ import annotations

from backend.modules.identity_access.workspace_roles import DEFAULT_WORKSPACE_SLUG


def default_workspace_name(*, email: str, full_name: str | None = None) -> str:
    label = (full_name or "").strip() or (email.split("@", 1)[0] if email else "User")
    return f"{label}'s workspace"


def default_workspace_slug() -> str:
    return DEFAULT_WORKSPACE_SLUG
