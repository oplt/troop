"""Marketplace catalog + install endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.api.deps.workspace import get_workspace_context
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.identity_access.workspace_context import WorkspaceContext
from backend.modules.workforce.authz import assert_company_owned
from backend.modules.workforce.services.marketplace_service import MarketplaceService
from backend.modules.workforce.services.workspace_package_service import WorkspacePackageService
from backend.modules.workforce.workspace_package_catalog import marketplace_policy

router = APIRouter(prefix="/marketplace")


class MarketplaceInstallRequest(RequestModel):
    slug: str
    company_id: str | None = None
    publish: bool = True
    connector_installation_ids: dict[str, str] = Field(default_factory=dict)
    agent_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None


@router.get("")
async def get_marketplace_catalog(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = user
    payload = MarketplaceService(db).list_all()
    payload["policy"] = marketplace_policy()
    return payload


@router.get("/skills")
async def list_marketplace_skills(
    category: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    _ = user
    return MarketplaceService(db).list_skills(category=category)


@router.get("/workflows")
async def list_marketplace_workflows(
    category: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    _ = user
    return MarketplaceService(db).list_workflows(category=category)


@router.get("/departments")
async def list_marketplace_departments(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    _ = user
    return MarketplaceService(db).list_departments()


@router.get("/agent-templates")
async def list_marketplace_agent_templates(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    _ = user
    return MarketplaceService(db).list_agent_templates()


class EmailApprovalBootstrapRequest(RequestModel):
    company_id: str | None = None
    gmail_installation_id: str
    telegram_installation_id: str | None = None
    approval_channel: str = "in_app"
    publish: bool = False
    project_id: str | None = None
    task_id: str | None = None
    agent_id: str | None = None


@router.post("/workflows/email-approval/bootstrap")
async def bootstrap_email_approval_template(
    payload: EmailApprovalBootstrapRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await assert_company_owned(db, user.id, payload.company_id)
    from backend.modules.workforce.authz import assert_project_owned, assert_task_owned

    await assert_project_owned(db, user.id, payload.project_id)
    await assert_task_owned(db, user.id, payload.task_id)
    return await MarketplaceService(db).bootstrap_email_approval(
        user,
        company_id=payload.company_id,
        gmail_installation_id=payload.gmail_installation_id,
        telegram_installation_id=payload.telegram_installation_id,
        approval_channel=payload.approval_channel,
        publish=payload.publish,
        project_id=payload.project_id,
        task_id=payload.task_id,
        agent_id=payload.agent_id,
    )


@router.post("/skills/install")
async def install_marketplace_skill(
    payload: MarketplaceInstallRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await assert_company_owned(db, user.id, payload.company_id)
    return await MarketplaceService(db).install_skill(
        user.id,
        payload.slug,
        company_id=payload.company_id,
        publish=payload.publish,
    )


@router.post("/workflows/install")
async def install_marketplace_workflow(
    payload: MarketplaceInstallRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await assert_company_owned(db, user.id, payload.company_id)
    from backend.modules.workforce.authz import assert_project_owned, assert_task_owned

    await assert_project_owned(db, user.id, payload.project_id)
    await assert_task_owned(db, user.id, payload.task_id)
    return await MarketplaceService(db).install_workflow(
        user.id,
        payload.slug,
        company_id=payload.company_id,
        publish=payload.publish,
        connector_installation_ids=payload.connector_installation_ids,
        agent_id=payload.agent_id,
        project_id=payload.project_id,
        task_id=payload.task_id,
    )


@router.post("/departments/install")
async def install_marketplace_department(
    payload: MarketplaceInstallRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    if not payload.company_id:
        from fastapi import HTTPException, status

        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="company_id required")
    await assert_company_owned(db, user.id, payload.company_id)
    return await MarketplaceService(db).install_department(
        user.id, payload.company_id, payload.slug
    )


@router.post("/agent-templates/install")
async def install_marketplace_agent_template(
    payload: MarketplaceInstallRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = user
    return await MarketplaceService(db).install_agent_template(payload.slug)


@router.post("/agent-templates/seed")
async def seed_marketplace_agent_templates(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = user
    return await MarketplaceService(db).seed_agent_templates()


class WorkspacePackageCreateRequest(RequestModel):
    kind: str
    marketplace_slug: str
    changelog: str = ""


class WorkspacePackagePublishRequest(RequestModel):
    payload: dict = Field(default_factory=dict)
    changelog: str = ""


class WorkspacePackageInstallRequest(RequestModel):
    version_id: str
    accept_permission_changes: bool = False
    apply_marketplace_install: bool = True


@router.get("/policy")
async def get_marketplace_policy(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = user, db
    return marketplace_policy()


@router.get("/workspace-packages")
async def list_workspace_packages(
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    return await WorkspacePackageService(db).list_packages(workspace.workspace_id)


@router.get("/workspace-packages/{package_id}")
async def get_workspace_package(
    package_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WorkspacePackageService(db).get_package(workspace.workspace_id, package_id)


@router.post("/workspace-packages/import")
async def import_workspace_package(
    payload: WorkspacePackageCreateRequest,
    user: User = Depends(get_authenticated_user),
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WorkspacePackageService(db).create_from_marketplace(
        workspace_id=workspace.workspace_id,
        user=user,
        kind=payload.kind,
        marketplace_slug=payload.marketplace_slug,
        changelog=payload.changelog,
    )


@router.post("/workspace-packages/{package_id}/versions")
async def publish_workspace_package_version(
    package_id: str,
    payload: WorkspacePackagePublishRequest,
    user: User = Depends(get_authenticated_user),
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WorkspacePackageService(db).publish_version(
        workspace_id=workspace.workspace_id,
        user=user,
        package_id=package_id,
        payload=payload.payload,
        changelog=payload.changelog,
    )


@router.get("/workspace-packages/{package_id}/permission-diff")
async def workspace_package_permission_diff(
    package_id: str,
    to_version_id: str,
    from_version_id: str | None = None,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WorkspacePackageService(db).permission_diff(
        workspace_id=workspace.workspace_id,
        package_id=package_id,
        from_version_id=from_version_id,
        to_version_id=to_version_id,
    )


@router.post("/workspace-packages/{package_id}/install")
async def install_workspace_package(
    package_id: str,
    payload: WorkspacePackageInstallRequest,
    user: User = Depends(get_authenticated_user),
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await WorkspacePackageService(db).install_or_upgrade(
        workspace_id=workspace.workspace_id,
        user=user,
        package_id=package_id,
        version_id=payload.version_id,
        accept_permission_changes=payload.accept_permission_changes,
        apply_marketplace_install=payload.apply_marketplace_install,
    )


@router.post("/workspace-packages/{package_id}/publish-public")
async def publish_workspace_package_public(
    package_id: str,
    workspace: WorkspaceContext = Depends(get_workspace_context),
    db: AsyncSession = Depends(get_db),
) -> dict:
    await WorkspacePackageService(db).attempt_public_publish(
        workspace_id=workspace.workspace_id,
        package_id=package_id,
    )
    return {"status": "published"}
