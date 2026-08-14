"""Canonical workspace-scoped authorization (RBAC-001B)."""

from __future__ import annotations

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User, Workspace, WorkspaceMembership
from backend.modules.identity_access.workspace_context import WorkspaceContext
from backend.modules.identity_access.workspace_permissions import (
    PERM_PROJECT_READ,
    PERM_PROJECT_WRITE,
    permissions_for_role,
    role_has_permission,
)
from backend.modules.identity_access.workspace_repository import WorkspaceRepository


class WorkspaceAuthorizationError(PermissionError):
    """Raised when workspace authorization fails."""


class WorkspaceAuthorizationService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.repo = WorkspaceRepository(db)

    async def resolve_active_workspace(
        self,
        user: User,
        *,
        workspace_id: str | None = None,
    ) -> WorkspaceContext:
        """Resolve the active workspace for a request.

        Falls back to the user's default workspace when no explicit workspace is provided.
        """
        if workspace_id:
            workspace = await self.repo.get_workspace(workspace_id)
            if workspace is None:
                raise HTTPException(status_code=404, detail="Workspace not found")
            membership = await self.repo.get_active_membership(workspace.id, user.id)
            if membership is None:
                raise HTTPException(
                    status_code=403,
                    detail="You are not a member of this workspace",
                )
            return self._build_context(user, workspace, membership)

        workspace, membership, created = await self.repo.ensure_default_workspace(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        if created:
            await self.db.commit()
        return self._build_context(user, workspace, membership)

    async def list_accessible_workspaces(
        self, user: User
    ) -> list[tuple[Workspace, WorkspaceMembership]]:
        _, _, created = await self.repo.ensure_default_workspace(
            user_id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        if created:
            await self.db.commit()
        return await self.repo.list_memberships_for_user(user.id)

    def require_permission(self, ctx: WorkspaceContext, permission: str) -> None:
        if not role_has_permission(ctx.primary_role, permission):
            raise HTTPException(
                status_code=403,
                detail=f"Role {ctx.primary_role!r} cannot perform {permission}",
            )

    def authorize_project_read(
        self,
        ctx: WorkspaceContext,
        *,
        project_owner_id: str,
    ) -> None:
        """Authorize read access to a project within the active workspace."""
        self.require_permission(ctx, PERM_PROJECT_READ)
        if str(project_owner_id) != str(ctx.workspace.owner_user_id):
            raise HTTPException(
                status_code=403,
                detail="Resource is not authorized for this workspace",
            )

    def authorize_project_write(
        self,
        ctx: WorkspaceContext,
        *,
        project_owner_id: str,
    ) -> None:
        self.require_permission(ctx, PERM_PROJECT_WRITE)
        if str(project_owner_id) != str(ctx.workspace.owner_user_id):
            raise HTTPException(
                status_code=403,
                detail="Resource is not authorized for this workspace",
            )

    @staticmethod
    def assert_commit_owner(*, resource_owner_id: str, ctx: WorkspaceContext) -> None:
        """Final side-effect boundary: resource owner must match workspace owner."""
        if str(resource_owner_id) != str(ctx.workspace.owner_user_id):
            raise WorkspaceAuthorizationError(
                "Resource owner does not match active workspace owner at commit time"
            )

    @staticmethod
    def _build_context(
        user: User,
        workspace: Workspace,
        membership: WorkspaceMembership,
    ) -> WorkspaceContext:
        return WorkspaceContext(
            workspace=workspace,
            membership=membership,
            actor=user,
            roles=frozenset({membership.role}),
        )


def permission_summary(role: str) -> list[str]:
    return sorted(permissions_for_role(role))
