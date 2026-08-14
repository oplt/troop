"""MCP/A2A connector definition + installation endpoints."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.authz import assert_company_owned
from backend.modules.workforce.connectors.registry import ConnectorManifestRegistry
from backend.modules.workforce.services.connector_service import ConnectorService

router = APIRouter(prefix="/connectors")


class ConnectorDefinitionResponse(BaseModel):
    id: str
    slug: str
    name: str
    description: str
    provider_type: str
    config_schema_json: dict = Field(default_factory=dict)


class ConnectorInstallationResponse(BaseModel):
    id: str
    connector_definition_id: str
    owner_id: str
    company_id: str | None = None
    name: str
    status: str
    environment: str = "dev"
    config_json: dict = Field(default_factory=dict)
    metadata_json: dict = Field(default_factory=dict)


class ConnectorInstallRequest(RequestModel):
    name: str
    connector_slug: str | None = None
    connector_definition_id: str | None = None
    company_id: str | None = None
    environment: str = "dev"
    config_json: dict = Field(default_factory=dict)


class ConnectorUpdateRequest(RequestModel):
    name: str | None = None
    status: str | None = None
    environment: str | None = None
    config_json: dict | None = None


def _public_config(config: dict) -> dict:
    """Strip secrets from API responses."""
    cleaned = dict(config or {})
    for key in ("auth_token", "api_key", "password", "secret"):
        if key in cleaned and cleaned[key]:
            cleaned[key] = "***"
    return cleaned


@router.get("/definitions", response_model=list[ConnectorDefinitionResponse])
async def list_connector_definitions(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectorDefinitionResponse]:
    _ = user
    items = await ConnectorService(db).list_definitions()
    return [ConnectorDefinitionResponse.model_validate(i) for i in items]


@router.post("/definitions/seed")
async def seed_connector_definitions(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    _ = user
    return await ConnectorService(db).seed_definitions()


@router.get("/manifests")
async def list_connector_manifests(
    user: User = Depends(get_authenticated_user),
) -> list[dict]:
    _ = user
    return [manifest.to_dict() for manifest in ConnectorManifestRegistry.list_manifests()]


@router.get("/manifests/{provider_slug}")
async def get_connector_manifest(
    provider_slug: str,
    user: User = Depends(get_authenticated_user),
) -> dict:
    _ = user
    manifest = ConnectorManifestRegistry.get_manifest(provider_slug)
    if manifest is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connector manifest not found")
    return manifest.to_dict()


@router.get("/installations", response_model=list[ConnectorInstallationResponse])
async def list_connector_installations(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[ConnectorInstallationResponse]:
    items = await ConnectorService(db).list_installations(user.id)
    return [
        ConnectorInstallationResponse(
            id=i.id,
            connector_definition_id=i.connector_definition_id,
            owner_id=i.owner_id,
            company_id=i.company_id,
            name=i.name,
            status=i.status,
            environment=i.environment or "dev",
            config_json=_public_config(i.config_json or {}),
            metadata_json=i.metadata_json or {},
        )
        for i in items
    ]


@router.post("/installations", response_model=ConnectorInstallationResponse, status_code=201)
async def install_connector(
    payload: ConnectorInstallRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> ConnectorInstallationResponse:
    await assert_company_owned(db, user.id, payload.company_id)
    installation = await ConnectorService(db).install(
        user.id,
        connector_slug=payload.connector_slug,
        connector_definition_id=payload.connector_definition_id,
        name=payload.name,
        config_json=payload.config_json,
        company_id=payload.company_id,
        environment=payload.environment,
    )
    from backend.modules.platform.activation_hooks import record_activation_for_owner

    await record_activation_for_owner(
        db,
        user.id,
        "first_connected_integration",
        at=installation.created_at,
        resource_type="connector_installation",
        resource_id=installation.id,
        metadata={"provider": (installation.metadata_json or {}).get("provider")},
    )
    await db.commit()
    return ConnectorInstallationResponse(
        id=installation.id,
        connector_definition_id=installation.connector_definition_id,
        owner_id=installation.owner_id,
        company_id=installation.company_id,
        name=installation.name,
        status=installation.status,
        environment=installation.environment or "dev",
        config_json=_public_config(installation.config_json or {}),
        metadata_json=installation.metadata_json or {},
    )


@router.patch("/installations/{installation_id}", response_model=ConnectorInstallationResponse)
async def update_connector_installation(
    installation_id: str,
    payload: ConnectorUpdateRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> ConnectorInstallationResponse:
    installation = await ConnectorService(db).update_installation(
        user.id,
        installation_id,
        name=payload.name,
        status=payload.status,
        environment=payload.environment,
        config_json=payload.config_json,
    )
    return ConnectorInstallationResponse(
        id=installation.id,
        connector_definition_id=installation.connector_definition_id,
        owner_id=installation.owner_id,
        company_id=installation.company_id,
        name=installation.name,
        status=installation.status,
        environment=installation.environment or "dev",
        config_json=_public_config(installation.config_json or {}),
        metadata_json=installation.metadata_json or {},
    )


@router.post("/installations/{installation_id}/test")
async def test_connector_installation(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict:
    return await ConnectorService(db).test_installation(user.id, installation_id)
