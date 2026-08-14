"""FastAPI dependencies for workspace-scoped authorization (RBAC-001B)."""

from __future__ import annotations

from fastapi import Depends, Header, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user, get_current_user
from backend.core.request_context import set_context
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.identity_access.workspace_authorization import WorkspaceAuthorizationService
from backend.modules.identity_access.workspace_context import (
    WorkspaceContext,
    set_active_workspace_id,
)
from backend.modules.identity_access.workspace_permissions import WORKSPACE_HEADER_NAME


async def get_workspace_context(
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
    x_workspace_id: str | None = Header(default=None, alias=WORKSPACE_HEADER_NAME),
) -> WorkspaceContext:
    """Resolve active workspace, bind request context, and return authorization context."""
    auth = WorkspaceAuthorizationService(db)
    ctx = await auth.resolve_active_workspace(current_user, workspace_id=x_workspace_id)
    set_active_workspace_id(ctx.workspace_id)
    set_context(tenant_id=ctx.workspace_id)
    request.state.workspace_id = ctx.workspace_id
    request.state.workspace_context = ctx
    return ctx


async def get_session_workspace_context(
    request: Request,
    current_user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
    x_workspace_id: str | None = Header(default=None, alias=WORKSPACE_HEADER_NAME),
) -> WorkspaceContext:
    """Like ``get_workspace_context`` but allows unverified users (session/me endpoints)."""
    auth = WorkspaceAuthorizationService(db)
    ctx = await auth.resolve_active_workspace(current_user, workspace_id=x_workspace_id)
    set_active_workspace_id(ctx.workspace_id)
    set_context(tenant_id=ctx.workspace_id)
    request.state.workspace_id = ctx.workspace_id
    request.state.workspace_context = ctx
    return ctx
