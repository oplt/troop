"""MCP + A2A tool providers backed by ConnectorInstallation configs."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import ConnectorDefinition, ConnectorInstallation
from backend.modules.workforce.services.a2a_client import A2AClient, A2AClientError
from backend.modules.workforce.services.connector_service import resolve_installation_config
from backend.modules.workforce.services.mcp_client import MCPClient, MCPClientError
from backend.modules.workforce.services.outbound_url import UnsafeURLError, validate_outbound_url
from backend.modules.workforce.services.tool_registry import NativeToolProvider


def _auth_headers(config: dict[str, Any]) -> dict[str, str]:
    headers: dict[str, str] = {}
    token = config.get("auth_token") or config.get("api_key")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    extra = config.get("headers")
    if isinstance(extra, dict):
        headers.update({str(k): str(v) for k, v in extra.items()})
    return headers


def _client_config(installation: ConnectorInstallation) -> dict[str, Any]:
    config = resolve_installation_config(installation)
    base_url = str(config.get("base_url") or config.get("url") or "").strip()
    validate_outbound_url(base_url)
    return config


class MCPToolProvider:
    """Live MCP tool discovery/execution via installed connectors."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._native = NativeToolProvider(db)
        self._cache: dict[str, list[dict[str, Any]]] = {}

    async def _installations(self, owner_id: str | None) -> list[ConnectorInstallation]:
        if self.db is None or not owner_id:
            return []
        result = await self.db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.provider_type == "mcp",
            )
        )
        return [row[0] for row in result.all()]

    def _client_for(self, installation: ConnectorInstallation) -> MCPClient:
        config = _client_config(installation)
        base_url = str(config.get("base_url") or config.get("url") or "").strip()
        if not base_url:
            raise MCPClientError(f"MCP installation {installation.id} missing base_url")
        return MCPClient(base_url=base_url, headers=_auth_headers(config))

    async def discover_tools(self, context: dict | None = None) -> list[dict]:
        owner_id = (context or {}).get("owner_id")
        tools: list[dict] = []
        for installation in await self._installations(str(owner_id) if owner_id else None):
            try:
                client = self._client_for(installation)
                discovered = await client.list_tools()
                for tool in discovered:
                    tool = {
                        **tool,
                        "metadata_json": {
                            **(tool.get("metadata_json") or {}),
                            "connector_installation_id": installation.id,
                            "connector_name": installation.name,
                        },
                    }
                    tools.append(tool)
                self._cache[installation.id] = discovered
            except Exception:
                continue
        return tools

    async def get_schema(self, tool_slug: str) -> dict:
        name = tool_slug[4:] if tool_slug.startswith("mcp.") else tool_slug
        for tools in self._cache.values():
            for tool in tools:
                if tool.get("name") == name or tool.get("slug") == tool_slug:
                    return tool.get("schema_json") or {}
        return {}

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        if not tool_slug.startswith("mcp."):
            return False
        return await self._native.validate_permissions(tool_slug, context)

    async def estimate_risk(self, tool_slug: str) -> str:
        return "high"

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        if not await self.validate_permissions(tool_slug, context):
            return {
                "status": "denied",
                "provider": "mcp",
                "tool_slug": tool_slug,
                "policy": context.get("_policy_resolution"),
            }
        owner_id = context.get("owner_id")
        installation_id = context.get("connector_installation_id") or params.get("_installation_id")
        installations = await self._installations(str(owner_id) if owner_id else None)
        selected = None
        if installation_id:
            selected = next((i for i in installations if i.id == installation_id), None)
        if selected is None and installations:
            selected = installations[0]
        if selected is None:
            return {"status": "error", "provider": "mcp", "error": "no active MCP connector"}
        try:
            client = self._client_for(selected)
            result = await client.call_tool(tool_slug, params)
            return {
                "status": "completed",
                "provider": "mcp",
                "tool_slug": tool_slug,
                "connector_installation_id": selected.id,
                "result": result,
            }
        except (MCPClientError, UnsafeURLError, Exception) as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "provider": "mcp",
                "tool_slug": tool_slug,
                "error": str(exc),
            }


class A2AToolProvider:
    """Call external A2A agents as tools (`a2a.send_task`)."""

    def __init__(self, db: AsyncSession | None = None) -> None:
        self.db = db
        self._native = NativeToolProvider(db)

    async def _installations(self, owner_id: str | None) -> list[ConnectorInstallation]:
        if self.db is None or not owner_id:
            return []
        result = await self.db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.provider_type == "a2a",
            )
        )
        return [row[0] for row in result.all()]

    async def discover_tools(self, context: dict | None = None) -> list[dict]:
        owner_id = (context or {}).get("owner_id")
        tools = [
            {
                "slug": "a2a.send_task",
                "name": "A2A Send Task",
                "description": "Send a task/message to an installed external A2A agent",
                "provider_type": "a2a",
                "risk_level": "high",
                "requires_approval": True,
                "schema_json": {
                    "type": "object",
                    "properties": {
                        "message": {"type": "string"},
                        "installation_id": {"type": "string"},
                        "context": {"type": "object"},
                    },
                    "required": ["message"],
                },
            }
        ]
        for installation in await self._installations(str(owner_id) if owner_id else None):
            config = dict(installation.config_json or {})
            tools.append(
                {
                    "slug": f"a2a.{installation.id[:8]}",
                    "name": f"A2A:{installation.name}",
                    "description": str(config.get("description") or installation.name),
                    "provider_type": "a2a",
                    "risk_level": "high",
                    "requires_approval": True,
                    "metadata_json": {"connector_installation_id": installation.id},
                }
            )
        return tools

    async def get_schema(self, tool_slug: str) -> dict:
        tools = await self.discover_tools()
        for tool in tools:
            if tool["slug"] == tool_slug:
                return tool.get("schema_json") or {}
        return {}

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        if not tool_slug.startswith("a2a."):
            return False
        return await self._native.validate_permissions(tool_slug, context)

    async def estimate_risk(self, tool_slug: str) -> str:
        return "high"

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        if not await self.validate_permissions(tool_slug, context):
            return {
                "status": "denied",
                "provider": "a2a",
                "tool_slug": tool_slug,
                "policy": context.get("_policy_resolution"),
            }
        owner_id = context.get("owner_id")
        installations = await self._installations(str(owner_id) if owner_id else None)
        installation_id = params.get("installation_id") or context.get("connector_installation_id")
        selected = None
        if installation_id:
            selected = next((i for i in installations if i.id == installation_id), None)
        if selected is None and tool_slug.startswith("a2a.") and tool_slug != "a2a.send_task":
            prefix = tool_slug.split(".", 1)[1]
            selected = next((i for i in installations if i.id.startswith(prefix)), None)
        if selected is None and installations:
            selected = installations[0]
        if selected is None:
            return {"status": "error", "provider": "a2a", "error": "no active A2A connector"}
        config = _client_config(selected)
        base_url = str(config.get("base_url") or config.get("url") or "").strip()
        if not base_url:
            return {"status": "error", "provider": "a2a", "error": "missing base_url"}
        message = str(params.get("message") or params.get("text") or "").strip()
        if not message:
            return {"status": "error", "provider": "a2a", "error": "message required"}
        try:
            client = A2AClient(
                base_url=base_url,
                card_url=config.get("card_url"),
                headers=_auth_headers(config),
            )
            result = await client.send_task(
                message=message,
                context=params.get("context") if isinstance(params.get("context"), dict) else {},
                metadata={"tool_slug": tool_slug, "installation_id": selected.id},
            )
            return {
                "status": "completed",
                "provider": "a2a",
                "tool_slug": tool_slug,
                "connector_installation_id": selected.id,
                "result": result,
            }
        except (A2AClientError, UnsafeURLError, Exception) as exc:  # noqa: BLE001
            return {
                "status": "failed",
                "provider": "a2a",
                "tool_slug": tool_slug,
                "error": str(exc),
            }
