"""Minimal MCP (Model Context Protocol) JSON-RPC client over HTTP.

Supports Streamable HTTP / JSON-RPC endpoints that implement:
  - tools/list
  - tools/call
  - initialize (optional handshake)

No extra dependency beyond httpx.
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx


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

    async def _rpc(self, method: str, params: dict[str, Any] | None = None) -> Any:
        payload = {
            "jsonrpc": "2.0",
            "id": self._next_id(),
            "method": method,
            "params": params or {},
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(self.base_url, json=payload, headers=self.headers)
            response.raise_for_status()
            # Some MCP HTTP gateways return SSE; try JSON first.
            try:
                data = response.json()
            except Exception as exc:  # noqa: BLE001
                text = response.text
                # Naive SSE data extraction: first "data: {...}" line
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
        # Strip mcp. prefix if present
        tool_name = name[4:] if name.startswith("mcp.") else name
        result = await self._rpc(
            "tools/call",
            {"name": tool_name, "arguments": arguments or {}, "callId": str(uuid4())},
        )
        return result if isinstance(result, dict) else {"content": result}
