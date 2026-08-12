"""Connector definition seed + installation management for MCP/A2A."""

from __future__ import annotations

import json
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.security import decrypt_secret, encrypt_secret
from backend.modules.workforce.catalog import CONNECTOR_CATALOG
from backend.modules.workforce.models import ConnectorDefinition, ConnectorInstallation
from backend.modules.workforce.services.a2a_client import A2AClient, A2AClientError
from backend.modules.workforce.services.mcp_client import MCPClient, MCPClientError
from backend.modules.workforce.services.outbound_url import UnsafeURLError, validate_outbound_url

_SECRET_KEYS = ("auth_token", "api_key", "password", "secret", "token")


def _split_secrets(config: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    public: dict[str, Any] = {}
    secrets: dict[str, Any] = {}
    for key, value in (config or {}).items():
        if key in _SECRET_KEYS and value:
            secrets[key] = value
        else:
            public[key] = value
    return public, secrets


def resolve_installation_config(installation: ConnectorInstallation) -> dict[str, Any]:
    """Merge public config with decrypted secrets for runtime use."""
    config = dict(installation.config_json or {})
    secrets_ref = installation.secrets_ref
    if secrets_ref and isinstance(secrets_ref, str):
        raw = decrypt_secret(secrets_ref)
        if raw:
            try:
                secrets = json.loads(raw)
            except json.JSONDecodeError:
                secrets = {"auth_token": raw}
            if isinstance(secrets, dict):
                config.update(secrets)
    return config


class ConnectorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def seed_definitions(self) -> dict[str, Any]:
        created = 0
        for item in CONNECTOR_CATALOG:
            result = await self.db.execute(
                select(ConnectorDefinition).where(ConnectorDefinition.slug == item["slug"])
            )
            if result.scalar_one_or_none():
                continue
            self.db.add(
                ConnectorDefinition(
                    slug=item["slug"],
                    name=item["name"],
                    description=item.get("description") or "",
                    provider_type=item.get("provider_type") or "native",
                    config_schema_json=item.get("config_schema_json") or {},
                    metadata_json={"catalog": True},
                )
            )
            created += 1
        await self.db.commit()
        return {"created": created, "total_catalog": len(CONNECTOR_CATALOG)}

    async def list_definitions(self) -> list[ConnectorDefinition]:
        await self.seed_definitions()
        result = await self.db.execute(
            select(ConnectorDefinition).order_by(ConnectorDefinition.name.asc())
        )
        return list(result.scalars().all())

    async def get_definition(self, definition_id: str) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.id == definition_id)
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connector definition not found")
        return item

    async def get_definition_by_slug(self, slug: str) -> ConnectorDefinition | None:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == slug)
        )
        return result.scalar_one_or_none()

    async def list_installations(self, owner_id: str) -> list[ConnectorInstallation]:
        result = await self.db.execute(
            select(ConnectorInstallation)
            .where(ConnectorInstallation.owner_id == owner_id)
            .order_by(ConnectorInstallation.created_at.desc())
        )
        return list(result.scalars().all())

    async def install(
        self,
        owner_id: str,
        *,
        connector_slug: str | None = None,
        connector_definition_id: str | None = None,
        name: str,
        config_json: dict[str, Any] | None = None,
        company_id: str | None = None,
    ) -> ConnectorInstallation:
        definition: ConnectorDefinition | None = None
        if connector_definition_id:
            definition = await self.get_definition(connector_definition_id)
        elif connector_slug:
            await self.seed_definitions()
            definition = await self.get_definition_by_slug(connector_slug)
        if definition is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connector definition not found")

        config = dict(config_json or {})
        base_url = str(config.get("base_url") or config.get("url") or "").strip()
        if not base_url:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="config_json.base_url is required",
            )
        try:
            validate_outbound_url(base_url, allow_http=True)
            if config.get("card_url"):
                validate_outbound_url(str(config["card_url"]), allow_http=True)
        except UnsafeURLError as exc:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)) from exc

        public_config, secrets = _split_secrets(config)
        secrets_ref = encrypt_secret(json.dumps(secrets)) if secrets else None

        installation = ConnectorInstallation(
            connector_definition_id=definition.id,
            owner_id=owner_id,
            company_id=company_id,
            name=name.strip() or definition.name,
            status="active",
            config_json=public_config,
            secrets_ref=secrets_ref,
            metadata_json={"provider_type": definition.provider_type},
        )
        self.db.add(installation)
        await self.db.commit()
        await self.db.refresh(installation)
        return installation

    async def get_installation(self, owner_id: str, installation_id: str) -> ConnectorInstallation:
        result = await self.db.execute(
            select(ConnectorInstallation).where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="connector installation not found")
        return item

    async def update_installation(
        self,
        owner_id: str,
        installation_id: str,
        *,
        name: str | None = None,
        status: str | None = None,
        config_json: dict[str, Any] | None = None,
    ) -> ConnectorInstallation:
        installation = await self.get_installation(owner_id, installation_id)
        if name is not None:
            installation.name = name.strip()
        if status is not None:
            if status not in {"active", "disabled", "error"}:
                raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, detail="invalid status")
            installation.status = status
        if config_json is not None:
            base_url = str(config_json.get("base_url") or config_json.get("url") or "").strip()
            if base_url:
                try:
                    validate_outbound_url(base_url, allow_http=True)
                except UnsafeURLError as exc:
                    raise HTTPException(
                        status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
                    ) from exc
            public_config, secrets = _split_secrets(dict(config_json))
            installation.config_json = public_config
            if secrets:
                installation.secrets_ref = encrypt_secret(json.dumps(secrets))
        await self.db.commit()
        await self.db.refresh(installation)
        return installation

    async def test_installation(self, owner_id: str, installation_id: str) -> dict[str, Any]:
        installation = await self.get_installation(owner_id, installation_id)
        definition = await self.get_definition(installation.connector_definition_id)
        config = resolve_installation_config(installation)
        base_url = str(config.get("base_url") or config.get("url") or "").strip()
        try:
            validate_outbound_url(base_url, allow_http=True)
        except UnsafeURLError as exc:
            return {"ok": False, "error": str(exc)}
        headers: dict[str, str] = {}
        token = config.get("auth_token") or config.get("api_key")
        if token:
            headers["Authorization"] = f"Bearer {token}"
        try:
            if definition.provider_type == "mcp":
                client = MCPClient(base_url=base_url, headers=headers)
                tools = await client.list_tools()
                return {
                    "ok": True,
                    "provider_type": "mcp",
                    "tool_count": len(tools),
                    "tools": [t.get("slug") for t in tools[:20]],
                }
            if definition.provider_type == "a2a":
                client = A2AClient(
                    base_url=base_url,
                    card_url=config.get("card_url"),
                    headers=headers,
                )
                card = await client.describe()
                return {"ok": True, "provider_type": "a2a", "agent": card}
            return {"ok": False, "error": f"unsupported provider {definition.provider_type}"}
        except (MCPClientError, A2AClientError, Exception) as exc:  # noqa: BLE001
            return {"ok": False, "provider_type": definition.provider_type, "error": str(exc)}
