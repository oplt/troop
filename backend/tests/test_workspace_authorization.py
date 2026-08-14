"""Tests for workspace-scoped authorization service (RBAC-001B)."""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest
from backend.api.main import app
from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User, Workspace, WorkspaceMembership
from backend.modules.identity_access.workspace_authorization import (
    WorkspaceAuthorizationError,
    WorkspaceAuthorizationService,
)
from backend.modules.identity_access.workspace_context import WorkspaceContext
from backend.modules.identity_access.workspace_permissions import (
    PERM_PROJECT_READ,
    PERM_PROJECT_WRITE,
    WORKSPACE_HEADER_NAME,
)
from backend.modules.identity_access.workspace_roles import (
    WORKSPACE_MEMBERSHIP_ACTIVE,
    WORKSPACE_ROLE_OWNER,
    WORKSPACE_ROLE_VIEWER,
)
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.services.service import OrchestrationService
from backend.modules.projects.orchestration_models import OrchestratorProject
from fastapi import HTTPException
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete


def _make_context(*, owner_id: str, role: str) -> WorkspaceContext:
    workspace = SimpleNamespace(id="ws-1", owner_user_id=owner_id, is_default=True)
    membership = SimpleNamespace(role=role)
    actor = SimpleNamespace(id="actor-1")
    return WorkspaceContext(
        workspace=workspace,  # type: ignore[arg-type]
        membership=membership,  # type: ignore[arg-type]
        actor=actor,  # type: ignore[arg-type]
        roles=frozenset({role}),
    )


def test_role_permission_matrix() -> None:
    svc = WorkspaceAuthorizationService(db=None)  # type: ignore[arg-type]
    owner_ctx = _make_context(owner_id="owner-1", role=WORKSPACE_ROLE_OWNER)
    viewer_ctx = _make_context(owner_id="owner-1", role=WORKSPACE_ROLE_VIEWER)

    svc.require_permission(owner_ctx, PERM_PROJECT_WRITE)
    svc.require_permission(viewer_ctx, PERM_PROJECT_READ)

    with pytest.raises(HTTPException) as exc:
        svc.require_permission(viewer_ctx, PERM_PROJECT_WRITE)
    assert exc.value.status_code == 403


def test_authorize_project_read_rejects_cross_workspace_owner() -> None:
    svc = WorkspaceAuthorizationService(db=None)  # type: ignore[arg-type]
    ctx = _make_context(owner_id="owner-a", role=WORKSPACE_ROLE_OWNER)

    with pytest.raises(HTTPException) as exc:
        svc.authorize_project_read(ctx, project_owner_id="owner-b")
    assert exc.value.status_code == 403


def test_assert_commit_owner_rejects_mismatch() -> None:
    ctx = _make_context(owner_id="owner-a", role=WORKSPACE_ROLE_OWNER)
    with pytest.raises(WorkspaceAuthorizationError):
        WorkspaceAuthorizationService.assert_commit_owner(
            resource_owner_id="owner-b",
            ctx=ctx,
        )


async def _create_project(owner_id: str, *, suffix: str) -> OrchestratorProject:
    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        project = await repo.create_project(
            owner_id=owner_id,
            name=f"Workspace auth test {suffix}",
            slug=f"ws-auth-{suffix}",
        )
        await db.commit()
        await db.refresh(project)
        return project


async def _ensure_workspace(user: User) -> Workspace:
    async with SessionLocal() as db:
        auth = WorkspaceAuthorizationService(db)
        ctx = await auth.resolve_active_workspace(user)
        return ctx.workspace


async def _cleanup_project(project_id: str) -> None:
    async with SessionLocal() as db:
        await db.execute(delete(OrchestratorProject).where(OrchestratorProject.id == project_id))
        await db.commit()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_project_allows_owner_default_workspace(tenant_pair: tuple[User, User]) -> None:
    user_a, _user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    await _ensure_workspace(user_a)
    project = await _create_project(user_a.id, suffix=suffix)

    try:
        async with SessionLocal() as db:
            service = OrchestrationService(db)
            loaded = await service.get_project(user_a, project.id)
            assert loaded.id == project.id
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_get_project_hides_cross_tenant_project(tenant_pair: tuple[User, User]) -> None:
    user_a, user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    await _ensure_workspace(user_b)
    project = await _create_project(user_a.id, suffix=suffix)

    try:
        async with SessionLocal() as db:
            service = OrchestrationService(db)
            with pytest.raises(HTTPException) as exc:
                await service.get_project(user_b, project.id)
            assert exc.value.status_code == 404
    finally:
        await _cleanup_project(project.id)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_resolve_active_workspace_rejects_non_member_header(
    tenant_pair: tuple[User, User],
) -> None:
    user_a, user_b = tenant_pair
    workspace_a = await _ensure_workspace(user_a)

    async with SessionLocal() as db:
        auth = WorkspaceAuthorizationService(db)
        with pytest.raises(HTTPException) as exc:
            await auth.resolve_active_workspace(user_b, workspace_id=workspace_a.id)
        assert exc.value.status_code == 403


@pytest.mark.asyncio
@pytest.mark.integration
async def test_sign_in_includes_active_workspace(tenant_pair: tuple[User, User]) -> None:
    user, _ = tenant_pair
    await _ensure_workspace(user)
    password = "IntegrationTestPass123!"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        response = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": user.email, "password": password},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["active_workspace"] is not None
    assert body["user"]["active_workspace"]["role"] == WORKSPACE_ROLE_OWNER


@pytest.mark.asyncio
@pytest.mark.integration
async def test_me_honors_workspace_header(tenant_pair: tuple[User, User]) -> None:
    user, _ = tenant_pair
    workspace = await _ensure_workspace(user)
    password = "IntegrationTestPass123!"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        sign_in = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": user.email, "password": password},
        )
        assert sign_in.status_code == 200, sign_in.text
        response = await client.get(
            "/api/v1/auth/me",
            headers={WORKSPACE_HEADER_NAME: workspace.id},
        )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["active_workspace"]["id"] == workspace.id


@pytest.mark.asyncio
@pytest.mark.integration
async def test_list_workspaces_returns_default_membership(tenant_pair: tuple[User, User]) -> None:
    user, _ = tenant_pair
    workspace = await _ensure_workspace(user)
    password = "IntegrationTestPass123!"

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        sign_in = await client.post(
            "/api/v1/auth/sign-in",
            json={"email": user.email, "password": password},
        )
        assert sign_in.status_code == 200, sign_in.text
        response = await client.get("/api/v1/auth/workspaces")
    assert response.status_code == 200, response.text
    items = response.json()["items"]
    assert any(item["id"] == workspace.id for item in items)


@pytest.mark.asyncio
@pytest.mark.integration
async def test_viewer_membership_cannot_authorize_project_write(
    tenant_pair: tuple[User, User],
) -> None:
    owner, member = tenant_pair
    workspace = await _ensure_workspace(owner)
    suffix = uuid.uuid4().hex[:8]
    project = await _create_project(owner.id, suffix=suffix)

    async with SessionLocal() as db:
        db.add(
            WorkspaceMembership(
                workspace_id=workspace.id,
                user_id=member.id,
                role=WORKSPACE_ROLE_VIEWER,
                status=WORKSPACE_MEMBERSHIP_ACTIVE,
            )
        )
        await db.commit()

    try:
        async with SessionLocal() as db:
            auth = WorkspaceAuthorizationService(db)
            ctx = await auth.resolve_active_workspace(member, workspace_id=workspace.id)
            with pytest.raises(HTTPException) as exc:
                auth.authorize_project_write(ctx, project_owner_id=owner.id)
            assert exc.value.status_code == 403
    finally:
        async with SessionLocal() as db:
            await db.execute(
                delete(WorkspaceMembership).where(
                    WorkspaceMembership.workspace_id == workspace.id,
                    WorkspaceMembership.user_id == member.id,
                )
            )
            await db.commit()
        await _cleanup_project(project.id)
