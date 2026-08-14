"""Active workspace context carried on authenticated requests."""

from __future__ import annotations

from contextvars import ContextVar
from dataclasses import dataclass

from backend.modules.identity_access.models import User, Workspace, WorkspaceMembership

_active_workspace_id: ContextVar[str | None] = ContextVar("active_workspace_id", default=None)


def set_active_workspace_id(workspace_id: str | None) -> None:
    _active_workspace_id.set(workspace_id)


def get_active_workspace_id() -> str | None:
    return _active_workspace_id.get()


@dataclass(frozen=True, slots=True)
class WorkspaceContext:
    workspace: Workspace
    membership: WorkspaceMembership
    actor: User
    roles: frozenset[str]

    @property
    def workspace_id(self) -> str:
        return self.workspace.id

    @property
    def actor_user_id(self) -> str:
        return self.actor.id

    @property
    def primary_role(self) -> str:
        return self.membership.role
