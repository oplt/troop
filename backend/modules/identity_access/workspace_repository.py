"""Persistence helpers for workspace RBAC."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import Workspace, WorkspaceMembership
from backend.modules.identity_access.workspace_backfill import (
    default_workspace_name,
    default_workspace_slug,
)
from backend.modules.identity_access.workspace_roles import (
    WORKSPACE_MEMBERSHIP_ACTIVE,
    WORKSPACE_ROLE_OWNER,
)


class WorkspaceRepository:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_workspace(self, workspace_id: str) -> Workspace | None:
        result = await self.db.execute(select(Workspace).where(Workspace.id == workspace_id))
        return result.scalar_one_or_none()

    async def get_default_workspace_for_user(self, user_id: str) -> Workspace | None:
        result = await self.db.execute(
            select(Workspace).where(
                Workspace.owner_user_id == user_id,
                Workspace.is_default.is_(True),
            )
        )
        return result.scalar_one_or_none()

    async def list_memberships_for_user(
        self, user_id: str, *, status: str = WORKSPACE_MEMBERSHIP_ACTIVE
    ) -> list[tuple[Workspace, WorkspaceMembership]]:
        result = await self.db.execute(
            select(Workspace, WorkspaceMembership)
            .join(WorkspaceMembership, WorkspaceMembership.workspace_id == Workspace.id)
            .where(
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == status,
            )
            .order_by(Workspace.is_default.desc(), Workspace.created_at.asc())
        )
        return list(result.all())

    async def get_active_membership(
        self, workspace_id: str, user_id: str
    ) -> WorkspaceMembership | None:
        result = await self.db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.user_id == user_id,
                WorkspaceMembership.status == WORKSPACE_MEMBERSHIP_ACTIVE,
            )
        )
        return result.scalar_one_or_none()

    async def list_active_memberships_by_roles(
        self,
        workspace_id: str,
        roles: list[str] | frozenset[str],
    ) -> list[WorkspaceMembership]:
        role_values = [str(role) for role in roles if str(role).strip()]
        if not role_values:
            return []
        result = await self.db.execute(
            select(WorkspaceMembership).where(
                WorkspaceMembership.workspace_id == workspace_id,
                WorkspaceMembership.status == WORKSPACE_MEMBERSHIP_ACTIVE,
                WorkspaceMembership.role.in_(role_values),
            )
        )
        return list(result.scalars().all())

    async def ensure_default_workspace(
        self,
        *,
        user_id: str,
        email: str,
        full_name: str | None,
    ) -> tuple[Workspace, WorkspaceMembership, bool]:
        existing = await self.get_default_workspace_for_user(user_id)
        if existing is not None:
            membership = await self.get_active_membership(existing.id, user_id)
            if membership is not None:
                return existing, membership, False

        workspace = Workspace(
            owner_user_id=user_id,
            name=default_workspace_name(email=email, full_name=full_name),
            slug=default_workspace_slug(),
            is_default=True,
        )
        self.db.add(workspace)
        await self.db.flush()
        membership = WorkspaceMembership(
            workspace_id=workspace.id,
            user_id=user_id,
            role=WORKSPACE_ROLE_OWNER,
            status=WORKSPACE_MEMBERSHIP_ACTIVE,
        )
        self.db.add(membership)
        await self.db.flush()
        return workspace, membership, True
