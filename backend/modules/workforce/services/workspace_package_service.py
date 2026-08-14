"""Private workspace package catalog — versioning, trust metadata, permission diffs (MKT-001)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.workforce.models import (
    WorkspacePackage,
    WorkspacePackageInstallation,
    WorkspacePackageVersion,
)
from backend.modules.workforce.services.marketplace_service import MarketplaceService
from backend.modules.workforce.workspace_package_catalog import (
    PUBLIC_MARKETPLACE_ENABLED,
    content_hash,
    diff_permission_manifests,
    extract_permission_manifest,
    marketplace_policy,
    sign_workspace_package,
    verify_workspace_package_signature,
)


class WorkspacePackageService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.marketplace = MarketplaceService(db)

    def get_policy(self) -> dict[str, Any]:
        return marketplace_policy()

    async def list_packages(self, workspace_id: str) -> list[dict[str, Any]]:
        result = await self.db.execute(
            select(WorkspacePackage)
            .where(
                WorkspacePackage.workspace_id == workspace_id,
                WorkspacePackage.visibility == "private",
            )
            .order_by(WorkspacePackage.updated_at.desc())
        )
        packages = list(result.scalars().all())
        rows: list[dict[str, Any]] = []
        for package in packages:
            installation = await self._get_installation(workspace_id, package.id)
            latest = await self._latest_version(package.id)
            rows.append(self._serialize_package(package, installation=installation, latest=latest))
        return rows

    async def get_package(self, workspace_id: str, package_id: str) -> dict[str, Any]:
        package = await self._get_owned_package(workspace_id, package_id)
        installation = await self._get_installation(workspace_id, package.id)
        latest = await self._latest_version(package.id)
        versions = await self.list_versions(workspace_id, package.id)
        return {
            **self._serialize_package(package, installation=installation, latest=latest),
            "versions": versions,
        }

    async def list_versions(self, workspace_id: str, package_id: str) -> list[dict[str, Any]]:
        await self._get_owned_package(workspace_id, package_id)
        result = await self.db.execute(
            select(WorkspacePackageVersion)
            .where(WorkspacePackageVersion.package_id == package_id)
            .order_by(WorkspacePackageVersion.version_number.desc())
        )
        return [self._serialize_version(item) for item in result.scalars().all()]

    async def create_from_marketplace(
        self,
        *,
        workspace_id: str,
        user: User,
        kind: str,
        marketplace_slug: str,
        changelog: str = "",
    ) -> dict[str, Any]:
        payload, name, description = self._snapshot_marketplace_item(kind, marketplace_slug)
        slug = f"{kind}-{marketplace_slug}".replace("/", "-")[:120]
        existing = await self.db.execute(
            select(WorkspacePackage).where(
                WorkspacePackage.workspace_id == workspace_id,
                WorkspacePackage.slug == slug,
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise HTTPException(status.HTTP_409_CONFLICT, detail="workspace package already exists")

        package = WorkspacePackage(
            id=str(uuid4()),
            workspace_id=workspace_id,
            owner_user_id=user.id,
            slug=slug,
            name=name,
            description=description,
            kind=kind,
            visibility="private",
            source_marketplace_slug=marketplace_slug,
            metadata_json={"origin": "builtin_marketplace"},
        )
        self.db.add(package)
        await self.db.flush()
        version = await self._create_signed_version(
            package=package,
            user=user,
            payload=payload,
            version_number=1,
            version_label="1.0.0",
            changelog=changelog or "Initial private workspace import",
        )
        await self.db.commit()
        await self.db.refresh(package)
        return {
            "package": self._serialize_package(package, latest=version),
            "version": self._serialize_version(version),
        }

    async def publish_version(
        self,
        *,
        workspace_id: str,
        user: User,
        package_id: str,
        payload: dict[str, Any],
        changelog: str,
    ) -> dict[str, Any]:
        package = await self._get_owned_package(workspace_id, package_id)
        if package.visibility != "private":
            raise HTTPException(
                status.HTTP_403_FORBIDDEN, detail="only private packages may be versioned here"
            )
        latest = await self._latest_version(package.id)
        next_number = (latest.version_number + 1) if latest else 1
        version_label = f"1.{next_number - 1}.0" if next_number > 1 else "1.0.0"
        version = await self._create_signed_version(
            package=package,
            user=user,
            payload=payload,
            version_number=next_number,
            version_label=version_label,
            changelog=changelog,
        )
        package.updated_at = datetime.now(UTC)
        await self.db.commit()
        return {"package_id": package.id, "version": self._serialize_version(version)}

    async def permission_diff(
        self,
        *,
        workspace_id: str,
        package_id: str,
        from_version_id: str | None = None,
        to_version_id: str,
    ) -> dict[str, Any]:
        package = await self._get_owned_package(workspace_id, package_id)
        to_version = await self._get_version(package.id, to_version_id)
        from_manifest: dict[str, Any] | None = None
        if from_version_id:
            from_version = await self._get_version(package.id, from_version_id)
            from_manifest = dict(from_version.permission_manifest_json or {})
        else:
            installation = await self._get_installation(workspace_id, package.id)
            if installation is not None:
                installed = await self._get_version(package.id, installation.installed_version_id)
                from_manifest = dict(installed.permission_manifest_json or {})
        diff = diff_permission_manifests(
            from_manifest, dict(to_version.permission_manifest_json or {})
        )
        return {
            "package_id": package.id,
            "from_version_id": from_version_id,
            "to_version_id": to_version.id,
            "diff": diff,
        }

    async def install_or_upgrade(
        self,
        *,
        workspace_id: str,
        user: User,
        package_id: str,
        version_id: str,
        accept_permission_changes: bool = False,
        apply_marketplace_install: bool = True,
    ) -> dict[str, Any]:
        package = await self._get_owned_package(workspace_id, package_id)
        version = await self._get_version(package.id, version_id)
        trust = dict(version.trust_json or {})
        digest = str(trust.get("content_hash") or content_hash(version.payload_json or {}))
        if not verify_workspace_package_signature(
            content_digest=digest,
            signer_user_id=str(version.created_by or user.id),
            trust=trust,
        ):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, detail="package signature verification failed"
            )

        installation = await self._get_installation(workspace_id, package.id)
        previous_manifest = (
            await self._installed_manifest(installation, package) if installation else None
        )
        diff = diff_permission_manifests(
            previous_manifest,
            dict(version.permission_manifest_json or {}),
        )
        if diff["requires_explicit_acceptance"] and not accept_permission_changes:
            raise HTTPException(
                status.HTTP_409_CONFLICT,
                detail={
                    "message": "Upgrade adds permissions — explicit acceptance required",
                    "permission_diff": diff,
                },
            )

        marketplace_result: dict[str, Any] | None = None
        if apply_marketplace_install and package.source_marketplace_slug:
            marketplace_result = await self._apply_marketplace_payload(
                user.id,
                package.kind,
                package.source_marketplace_slug,
                dict(version.payload_json or {}),
            )

        now = datetime.now(UTC)
        if installation is None:
            installation = WorkspacePackageInstallation(
                id=str(uuid4()),
                workspace_id=workspace_id,
                package_id=package.id,
                installed_version_id=version.id,
                installed_by=user.id,
                installed_at=now,
                updated_at=now,
                metadata_json={"permission_diff_applied": diff if diff["has_escalation"] else {}},
            )
            self.db.add(installation)
            status_label = "installed"
        else:
            installation.installed_version_id = version.id
            installation.installed_by = user.id
            installation.updated_at = now
            meta = dict(installation.metadata_json or {})
            meta["previous_permission_diff"] = diff if diff["has_escalation"] else {}
            installation.metadata_json = meta
            status_label = "upgraded"

        await self.db.commit()
        return {
            "status": status_label,
            "package_id": package.id,
            "installed_version_id": version.id,
            "permission_diff": diff,
            "marketplace": marketplace_result,
        }

    async def attempt_public_publish(self, *, workspace_id: str, package_id: str) -> None:
        await self._get_owned_package(workspace_id, package_id)
        if not PUBLIC_MARKETPLACE_ENABLED:
            raise HTTPException(
                status.HTTP_403_FORBIDDEN,
                detail="Public marketplace publishing is deferred until private workspace packages are proven",
            )

    async def _installed_manifest(
        self,
        installation: WorkspacePackageInstallation | None,
        package: WorkspacePackage,
    ) -> dict[str, Any]:
        if installation is None:
            return {}
        version = await self._get_version(package.id, installation.installed_version_id)
        return dict(version.permission_manifest_json or {})

    async def _create_signed_version(
        self,
        *,
        package: WorkspacePackage,
        user: User,
        payload: dict[str, Any],
        version_number: int,
        version_label: str,
        changelog: str,
    ) -> WorkspacePackageVersion:
        manifest = extract_permission_manifest(payload, kind=package.kind)
        digest = content_hash(payload)
        trust = sign_workspace_package(content_digest=digest, signer_user_id=user.id)
        trust["signed_by_user_id"] = user.id
        trust["signed_at"] = datetime.now(UTC).isoformat()
        version = WorkspacePackageVersion(
            id=str(uuid4()),
            package_id=package.id,
            version_label=version_label,
            version_number=version_number,
            payload_json=payload,
            permission_manifest_json=manifest,
            trust_json=trust,
            changelog=changelog,
            created_by=user.id,
        )
        self.db.add(version)
        await self.db.flush()
        return version

    async def _apply_marketplace_payload(
        self,
        owner_id: str,
        kind: str,
        marketplace_slug: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        if kind == "skill":
            return await self.marketplace.install_skill(owner_id, marketplace_slug, publish=True)
        if kind == "workflow":
            return await self.marketplace.install_workflow(owner_id, marketplace_slug, publish=True)
        if kind == "department":
            company_id = str(payload.get("company_id") or "")
            if not company_id:
                raise HTTPException(
                    status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="company_id required for department install",
                )
            return await self.marketplace.install_department(owner_id, company_id, marketplace_slug)
        if kind == "agent_template":
            return await self.marketplace.install_agent_template(marketplace_slug)
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="unsupported package kind")

    def _snapshot_marketplace_item(self, kind: str, slug: str) -> tuple[dict[str, Any], str, str]:
        if kind == "skill":
            item = self.marketplace._find_skill(slug)
        elif kind == "workflow":
            item = self.marketplace._find_workflow(slug)
        elif kind == "department":
            item = self.marketplace._find_department(slug)
        elif kind == "agent_template":
            item = self.marketplace._find_agent_template(slug)
        else:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid package kind")
        payload = dict(item)
        if kind == "workflow":
            payload.setdefault("nodes", list(item.get("nodes") or []))
            payload.setdefault("edges", list(item.get("edges") or []))
        if kind == "skill":
            payload["required_tools"] = list(item.get("required_tools") or [])
        if kind == "agent_template":
            payload["allowed_tools"] = list(item.get("allowed_tools") or [])
        return payload, str(item.get("name") or slug), str(item.get("description") or "")

    async def _get_owned_package(self, workspace_id: str, package_id: str) -> WorkspacePackage:
        result = await self.db.execute(
            select(WorkspacePackage).where(
                WorkspacePackage.id == package_id,
                WorkspacePackage.workspace_id == workspace_id,
            )
        )
        package = result.scalar_one_or_none()
        if package is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="workspace package not found")
        return package

    async def _get_version(self, package_id: str, version_id: str) -> WorkspacePackageVersion:
        result = await self.db.execute(
            select(WorkspacePackageVersion).where(
                WorkspacePackageVersion.id == version_id,
                WorkspacePackageVersion.package_id == package_id,
            )
        )
        version = result.scalar_one_or_none()
        if version is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="package version not found")
        return version

    async def _latest_version(self, package_id: str) -> WorkspacePackageVersion | None:
        result = await self.db.execute(
            select(WorkspacePackageVersion)
            .where(WorkspacePackageVersion.package_id == package_id)
            .order_by(WorkspacePackageVersion.version_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _get_installation(
        self, workspace_id: str, package_id: str
    ) -> WorkspacePackageInstallation | None:
        result = await self.db.execute(
            select(WorkspacePackageInstallation).where(
                WorkspacePackageInstallation.workspace_id == workspace_id,
                WorkspacePackageInstallation.package_id == package_id,
            )
        )
        return result.scalar_one_or_none()

    def _serialize_package(
        self,
        package: WorkspacePackage,
        *,
        installation: WorkspacePackageInstallation | None = None,
        latest: WorkspacePackageVersion | None = None,
    ) -> dict[str, Any]:
        return {
            "id": package.id,
            "workspace_id": package.workspace_id,
            "slug": package.slug,
            "name": package.name,
            "description": package.description,
            "kind": package.kind,
            "visibility": package.visibility,
            "source_marketplace_slug": package.source_marketplace_slug,
            "installed_version_id": installation.installed_version_id if installation else None,
            "latest_version_id": latest.id if latest else None,
            "latest_version_label": latest.version_label if latest else None,
            "trust_level": (latest.trust_json or {}).get("trust_level") if latest else None,
            "updated_at": package.updated_at.isoformat() if package.updated_at else None,
        }

    def _serialize_version(self, version: WorkspacePackageVersion) -> dict[str, Any]:
        trust = dict(version.trust_json or {})
        return {
            "id": version.id,
            "package_id": version.package_id,
            "version_label": version.version_label,
            "version_number": version.version_number,
            "permission_manifest": dict(version.permission_manifest_json or {}),
            "trust": {
                "content_hash": trust.get("content_hash"),
                "signature_scheme": trust.get("signature_scheme"),
                "trust_level": trust.get("trust_level"),
                "review_status": trust.get("review_status"),
                "signed_by_user_id": trust.get("signed_by_user_id"),
                "signed_at": trust.get("signed_at"),
            },
            "changelog": version.changelog,
            "created_at": version.created_at.isoformat() if version.created_at else None,
        }
