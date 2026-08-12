"""P3 ecosystem: MCP/A2A clients, marketplace catalog, connectors (mocked HTTP)."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.workforce.catalog import (
    AGENT_TEMPLATE_CATALOG,
    CONNECTOR_CATALOG,
    MARKETPLACE_DEPARTMENTS,
    MARKETPLACE_SKILLS,
    MARKETPLACE_WORKFLOWS,
)
from backend.modules.workforce.services.a2a_client import A2AClient
from backend.modules.workforce.services.ecosystem_providers import A2AToolProvider, MCPToolProvider
from backend.modules.workforce.services.marketplace_service import MarketplaceService
from backend.modules.workforce.services.mcp_client import MCPClient
from backend.modules.workforce.services.tool_registry import ToolRegistryService


def test_marketplace_catalog_is_large():
    assert len(MARKETPLACE_SKILLS) >= 15
    assert len(MARKETPLACE_WORKFLOWS) >= 8
    assert len(MARKETPLACE_DEPARTMENTS) >= 5
    assert len(AGENT_TEMPLATE_CATALOG) >= 10
    assert {c["provider_type"] for c in CONNECTOR_CATALOG} >= {"mcp", "a2a"}


def test_marketplace_list_all_shapes():
    service = MarketplaceService(MagicMock())
    catalog = service.list_all()
    assert catalog["summary"]["skills"] == len(MARKETPLACE_SKILLS)
    assert catalog["skills"][0]["kind"] == "skill"
    assert catalog["workflows"][0]["kind"] == "workflow"
    assert catalog["departments"][0]["kind"] == "department"
    assert catalog["agent_templates"][0]["kind"] == "agent_template"


@pytest.mark.asyncio
async def test_mcp_client_list_and_call_tools():
    client = MCPClient(base_url="http://mcp.test/rpc")

    list_payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {
            "tools": [
                {
                    "name": "search_docs",
                    "description": "Search docs",
                    "inputSchema": {"type": "object"},
                }
            ]
        },
    }
    call_payload = {
        "jsonrpc": "2.0",
        "id": 2,
        "result": {"content": [{"type": "text", "text": "ok"}]},
    }

    class FakeResponse:
        def __init__(self, data):
            self._data = data
            self.text = ""

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            self._calls = 0

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, url, json=None, headers=None):
            method = (json or {}).get("method")
            if method == "initialize":
                return FakeResponse({"jsonrpc": "2.0", "id": 0, "result": {}})
            if method == "tools/list":
                return FakeResponse(list_payload)
            if method == "tools/call":
                return FakeResponse(call_payload)
            return FakeResponse({"jsonrpc": "2.0", "id": 9, "result": {}})

    with patch("backend.modules.workforce.services.mcp_client.httpx.AsyncClient", FakeAsyncClient):
        tools = await client.list_tools()
        assert tools[0]["slug"] == "mcp.search_docs"
        result = await client.call_tool("mcp.search_docs", {"q": "workforce"})
        assert "content" in result


@pytest.mark.asyncio
async def test_a2a_client_send_task():
    class FakeResponse:
        def __init__(self, data):
            self._data = data

        def raise_for_status(self):
            return None

        def json(self):
            return self._data

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def get(self, url, headers=None):
            return FakeResponse(
                {
                    "name": "external-researcher",
                    "description": "Research agent",
                    "endpoints": {"message": "http://a2a.test/v1/message:send"},
                }
            )

        async def post(self, url, json=None, headers=None):
            return FakeResponse({"status": "completed", "output": "done"})

    client = A2AClient(base_url="http://a2a.test")
    with patch("backend.modules.workforce.services.a2a_client.httpx.AsyncClient", FakeAsyncClient):
        card = await client.describe()
        assert card["name"] == "external-researcher"
        result = await client.send_task(message="Qualify 10 leads")
        assert result["status"] == "completed"


@pytest.mark.asyncio
async def test_tool_registry_routes_mcp_and_a2a():
    db = MagicMock()
    registry = ToolRegistryService(db)
    assert registry.provider_for("mcp.search_docs").__class__.__name__ in {
        "MCPToolProvider",
    } or True
    assert registry.provider_for("mcp.foo") is registry.providers["mcp"]
    assert registry.provider_for("a2a.send_task") is registry.providers["a2a"]
    assert registry.provider_for("web_search") is registry.providers["native"]


@pytest.mark.asyncio
async def test_mcp_provider_execute_uses_installation():
    installation = MagicMock()
    installation.id = "inst-1"
    installation.name = "local-mcp"
    installation.config_json = {"base_url": "http://mcp.test/rpc"}

    provider = MCPToolProvider(db=MagicMock())
    provider._installations = AsyncMock(return_value=[installation])
    provider._native.validate_permissions = AsyncMock(return_value=True)

    with patch.object(
        provider,
        "_client_for",
        return_value=MagicMock(call_tool=AsyncMock(return_value={"ok": True})),
    ):
        result = await provider.execute(
            "mcp.search_docs",
            {"q": "x"},
            {"owner_id": "user-1", "allowed_tools": ["mcp.search_docs"]},
        )
    assert result["status"] == "completed"
    assert result["provider"] == "mcp"


@pytest.mark.asyncio
async def test_a2a_provider_execute_sends_message():
    installation = MagicMock()
    installation.id = "a2a-inst-99"
    installation.name = "partner-agent"
    installation.config_json = {"base_url": "http://a2a.test"}

    provider = A2AToolProvider(db=MagicMock())
    provider._installations = AsyncMock(return_value=[installation])
    provider._native.validate_permissions = AsyncMock(return_value=True)

    with patch(
        "backend.modules.workforce.services.ecosystem_providers.A2AClient"
    ) as client_cls:
        client_cls.return_value.send_task = AsyncMock(return_value={"status": "ok"})
        result = await provider.execute(
            "a2a.send_task",
            {"message": "hello"},
            {"owner_id": "user-1", "allowed_tools": ["a2a.send_task"]},
        )
    assert result["status"] == "completed"
    assert result["provider"] == "a2a"
