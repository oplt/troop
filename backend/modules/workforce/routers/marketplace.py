"""Marketplace catalog + install endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.authz import assert_company_owned
from backend.modules.workforce.services.marketplace_service import MarketplaceService

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
    return MarketplaceService(db).list_all()


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
