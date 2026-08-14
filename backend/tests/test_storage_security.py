"""SEC-002: private object storage defaults and authorized access."""

from __future__ import annotations

import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.core.config import Settings
from backend.core.storage import ObjectStorage, StorageAssetClass
from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User
from backend.modules.memory.models import EpisodicArchiveManifest
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.projects.orchestration_models import OrchestratorProject
from pydantic import ValidationError
from sqlalchemy import delete


@pytest.mark.asyncio
async def test_private_upload_uses_private_cache_control() -> None:
    storage = ObjectStorage()
    captured: dict = {}

    def _put_object(**kwargs):
        captured.update(kwargs)

    storage._client = MagicMock()
    storage._client.put_object = _put_object

    with patch("backend.core.storage.settings.STORAGE_BUCKET", "private-bucket"), patch(
        "backend.core.storage.settings.STORAGE_PUBLIC_READ", False
    ), patch(
        "backend.core.storage.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())
    ):
        stored = await storage.upload_bytes(
            object_key="episodic-archives/o1/p1/2026.jsonl.gz",
            body=b"gz",
            content_type="application/gzip",
            asset_class=StorageAssetClass.PRIVATE,
        )

    assert stored.access_url is None
    assert captured["CacheControl"] == "private, no-store"
    assert "ACL" not in captured


@pytest.mark.asyncio
async def test_private_upload_does_not_return_public_url() -> None:
    storage = ObjectStorage()
    storage._client = MagicMock()
    storage._client.put_object = MagicMock()

    with patch("backend.core.storage.settings.STORAGE_BUCKET", "private-bucket"), patch(
        "backend.core.storage.settings.STORAGE_PUBLIC_READ", False
    ), patch(
        "backend.core.storage.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())
    ):
        stored = await storage.upload_bytes(
            object_key="orchestration/p1/doc.txt",
            body=b"hello",
            content_type="text/plain",
            asset_class=StorageAssetClass.PRIVATE,
        )

    assert stored.access_url is None


@pytest.mark.asyncio
async def test_resolve_access_url_uses_presigned_for_private_avatar_bucket() -> None:
    storage = ObjectStorage()
    storage._client = MagicMock()
    storage._client.generate_presigned_url = MagicMock(return_value="https://signed.example/avatar")

    with patch("backend.core.storage.settings.STORAGE_BUCKET", "private-bucket"), patch(
        "backend.core.storage.settings.STORAGE_PUBLIC_ASSET_BUCKET", ""
    ), patch("backend.core.storage.settings.STORAGE_PUBLIC_READ", False), patch(
        "backend.core.storage.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())
    ):
        url = await storage.resolve_access_url(
            "avatars/user-1/abc.png",
            asset_class=StorageAssetClass.PUBLIC_ASSET,
        )

    assert url == "https://signed.example/avatar"
    storage._client.generate_presigned_url.assert_called_once()


def test_production_rejects_public_read_on_primary_bucket() -> None:
    with pytest.raises(ValidationError, match="STORAGE_PUBLIC_READ must be false"):
        Settings(
            APP_ENV="production",
            JWT_SECRET="x" * 32,
            COOKIE_SECURE=True,
            FRONTEND_URL="https://app.example.com",
            CORS_ALLOWED_ORIGINS=["https://app.example.com"],
            STORAGE_BUCKET="private-artifacts",
            STORAGE_PUBLIC_READ=True,
        )


@pytest.mark.asyncio
async def test_ensure_bucket_skips_public_policy_for_private_default() -> None:
    storage = ObjectStorage()
    storage._client = MagicMock()
    storage._client.head_bucket = MagicMock()

    with patch("backend.core.storage.settings.STORAGE_BUCKET", "private-bucket"), patch(
        "backend.core.storage.settings.STORAGE_AUTO_CREATE_BUCKET", True
    ), patch("backend.core.storage.settings.STORAGE_PUBLIC_READ", False), patch(
        "backend.core.storage.settings.STORAGE_PUBLIC_ASSET_BUCKET", ""
    ), patch(
        "backend.core.storage.asyncio.to_thread", new=AsyncMock(side_effect=lambda fn: fn())
    ):
        await storage.ensure_bucket()

    storage._client.put_bucket_policy.assert_not_called()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_episodic_archive_download_denies_other_tenant(
    tenant_pair: tuple[User, User],
    api_client,
) -> None:
    user_a, user_b = tenant_pair
    suffix = uuid.uuid4().hex[:8]
    project_id: str | None = None
    archive_id: str | None = None

    async with SessionLocal() as db:
        repo = OrchestrationRepository(db)
        project = await repo.create_project(
            owner_id=user_a.id,
            name=f"Storage test {suffix}",
            slug=f"storage-test-{suffix}",
        )
        archive = EpisodicArchiveManifest(
            owner_id=user_a.id,
            project_id=project.id,
            object_key=f"episodic-archives/{user_a.id}/{project.id}/{suffix}.jsonl.gz",
            period_start=project.created_at,
            period_end=project.created_at,
            record_count=1,
            byte_size=10,
            stats_json={},
        )
        db.add(archive)
        await db.commit()
        project_id = project.id
        archive_id = archive.id

    download_path = (
        f"/api/v1/orchestration/projects/{project_id}/episodic-memory/archives/"
        f"{archive_id}/download"
    )

    sign_in_b = await api_client.post(
        "/api/v1/auth/sign-in",
        json={"email": user_b.email, "password": "IntegrationTestPass123!"},
    )
    assert sign_in_b.status_code == 200
    denied = await api_client.get(download_path, cookies=sign_in_b.cookies)
    assert denied.status_code in {403, 404}

    api_client.cookies.clear()
    anonymous = await api_client.get(download_path)
    assert anonymous.status_code in {401, 403, 404}

    sign_in_a = await api_client.post(
        "/api/v1/auth/sign-in",
        json={"email": user_a.email, "password": "IntegrationTestPass123!"},
    )
    assert sign_in_a.status_code == 200

    with patch("backend.core.storage.settings.STORAGE_BUCKET", "test-bucket"), patch(
        "backend.core.storage.object_storage.presigned_get_url",
        new=AsyncMock(return_value="https://signed.example/archive"),
    ):
        allowed = await api_client.get(
            download_path,
            cookies=sign_in_a.cookies,
            follow_redirects=False,
        )
    assert allowed.status_code == 307
    assert allowed.headers["location"] == "https://signed.example/archive"

    async with SessionLocal() as db:
        await db.execute(
            delete(EpisodicArchiveManifest).where(EpisodicArchiveManifest.id == archive_id)
        )
        await db.execute(delete(OrchestratorProject).where(OrchestratorProject.id == project_id))
        await db.commit()
