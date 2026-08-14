from __future__ import annotations

import uuid
from collections.abc import AsyncIterator

import pytest
from backend.api.main import app
from backend.core.config import settings
from backend.core.security import hash_password
from backend.db.session import SessionLocal
from backend.modules.identity_access.models import RefreshSession, User
from httpx import ASGITransport, AsyncClient
from sqlalchemy import delete


def services_available_sync() -> bool:
    try:
        import redis

        redis.from_url(settings.REDIS_URL, decode_responses=True).ping()
    except Exception:
        return False

    db_url = settings.DATABASE_URL.replace("postgresql+asyncpg://", "postgresql://", 1)
    try:
        import subprocess

        result = subprocess.run(
            ["pg_isready", "-d", db_url],
            capture_output=True,
            timeout=3,
            check=False,
        )
        return result.returncode == 0
    except Exception:
        return True


@pytest.fixture(scope="session")
def integration_services_ok() -> None:
    if not services_available_sync():
        pytest.skip("Integration tests require reachable PostgreSQL and Redis")


@pytest.fixture
async def require_integration(integration_services_ok: None) -> None:
    from backend.db.session import engine
    from backend.modules.identity_access.models import Workspace, WorkspaceMembership

    def _create_workspace_tables(sync_conn) -> None:
        Workspace.__table__.create(sync_conn, checkfirst=True)
        WorkspaceMembership.__table__.create(sync_conn, checkfirst=True)

    async with engine.begin() as conn:
        await conn.run_sync(_create_workspace_tables)
    return None


@pytest.fixture
async def app_client() -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def api_client(require_integration) -> AsyncIterator[AsyncClient]:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://testserver") as client:
        yield client


@pytest.fixture
async def verified_user(require_integration) -> AsyncIterator[tuple[User, str]]:
    password = "IntegrationTestPass123!"
    email = f"integration-{uuid.uuid4().hex}@example.com"
    async with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Integration Test User",
            is_active=True,
            is_verified=True,
            is_admin=False,
            mfa_enabled=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
    try:
        yield user, password
    finally:
        async with SessionLocal() as db:
            await db.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
            await db.execute(delete(User).where(User.id == user.id))
            await db.commit()


async def _create_verified_user(*, label: str) -> User:
    password = "IntegrationTestPass123!"
    email = f"tenant-{label}-{uuid.uuid4().hex}@example.com"
    async with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name=f"Tenant User {label.upper()}",
            is_active=True,
            is_verified=True,
            is_admin=False,
            mfa_enabled=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return user


@pytest.fixture
async def tenant_pair(require_integration) -> AsyncIterator[tuple[User, User]]:
    """Two isolated verified users for multi-tenant ACL regression tests."""
    user_a = await _create_verified_user(label="a")
    user_b = await _create_verified_user(label="b")
    try:
        yield user_a, user_b
    finally:
        async with SessionLocal() as db:
            for user in (user_a, user_b):
                await db.execute(delete(RefreshSession).where(RefreshSession.user_id == user.id))
                await db.execute(delete(User).where(User.id == user.id))
            await db.commit()


@pytest.fixture
async def auth_client(api_client: AsyncClient, verified_user: tuple[User, str]) -> AsyncClient:
    user, password = verified_user
    response = await api_client.post(
        "/api/v1/auth/sign-in",
        json={"email": user.email, "password": password},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["user"]["id"] == user.id
    assert body["user"]["email"] == user.email
    return api_client


def csrf_headers(client: AsyncClient) -> dict[str, str]:
    token = client.cookies.get(settings.CSRF_COOKIE_NAME)
    assert token, "Expected CSRF cookie after sign-in"
    return {settings.CSRF_HEADER_NAME: token}
