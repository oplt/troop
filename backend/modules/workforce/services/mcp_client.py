"""Minimal MCP (Model Context Protocol) JSON-RPC client over HTTP.

Supports Streamable HTTP / JSON-RPC endpoints that implement:
  - tools/list
  - tools/call
  - initialize (optional handshake)
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx

from backend.core.http_clients import managed_http_client
from backend.modules.workforce.services.http_resilience import request_with_retry
from backend.modules.workforce.services.outbound_url import validate_outbound_url


class MCPClientError(RuntimeError):
    pass


class MCPClient:
    def __init__(
        self,
        *,
        base_url: str,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json, text/event-stream",
            **(headers or {}),
        }
        self.timeout_seconds = timeout_seconds
        self._request_id = 0

    def _next_id(self) -> int:
        self._request_id += 1
        return self._request_id

    def _validated_url(self) -> str:
        return validate_outbound_url(self.base_url)

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        url = self._validated_url()
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }

        async def _post() -> httpx.Response:
            async with managed_http_client(
                "mcp-client",
                base_url=url,
                timeout_seconds=self.timeout_seconds,
            ) as client:
                response = await client.post(url, json=payload, headers=self.headers)
                response.raise_for_status()
                return response

        try:
            response = await request_with_retry(_post, base_url=url)
        except httpx.HTTPError as exc:
            raise MCPClientError(str(exc)) from exc

        try:
            data = response.json()
        except Exception as exc:  # noqa: BLE001
            text = response.text
            for line in text.splitlines():
                if line.startswith("data:"):
                    import json

                    data = json.loads(line[5:].strip())
                    break
            else:
                raise MCPClientError(f"MCP response was not JSON: {text[:200]}") from exc
        if isinstance(data, dict) and data.get("error"):
            raise MCPClientError(str(data["error"]))
        if isinstance(data, dict) and "result" in data:
            return data["result"]
        return data

    async def initialize(self) -> dict[str, Any]:
        try:
            result = await self._rpc(
                "initialize",
                {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {},
                    "clientInfo": {"name": "troop", "version": "1.0.0"},
                },
            )
            return result if isinstance(result, dict) else {"raw": result}
        except Exception as exc:  # noqa: BLE001
            return {"status": "skipped", "reason": str(exc)}

    async def list_tools(self) -> list[dict[str, Any]]:
        await self.initialize()
        result = await self._rpc("tools/list", {})
        tools = []
        if isinstance(result, dict):
            tools = list(result.get("tools") or [])
        elif isinstance(result, list):
            tools = result
        normalized = []
        for tool in tools:
            if not isinstance(tool, dict):
                continue
            name = str(tool.get("name") or "").strip()
            if not name:
                continue
            normalized.append(
                {
                    "slug": f"mcp.{name}",
                    "name": name,
                    "description": str(tool.get("description") or ""),
                    "schema_json": tool.get("inputSchema") or tool.get("input_schema") or {},
                    "provider_type": "mcp",
                    "risk_level": "high",
                    "requires_approval": True,
                    "metadata_json": {"mcp_tool": tool},
                }
            )
        return normalized

    async def call_tool(self, name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
        await self.initialize()
        tool_name = name[4:] if name.startswith("mcp.") else name
        result = await self._rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}, "callId": str(uuid4())},
        )
        return result if isinstance(result, dict) else {"content": result}
