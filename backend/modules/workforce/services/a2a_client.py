"""A2A (Agent-to-Agent) client — discover agent cards and send tasks.

Compatible with agent-card based HTTP agents:
  GET  {base}/.well-known/agent.json  (or configured card_url)
  POST {base}/v1/message:send         (or card endpoints.message)
"""

from __future__ import annotations

from typing import Any
from uuid import uuid4

import httpx


class A2AClientError(RuntimeError):
    pass


class A2AClient:
    def __init__(
        self,
        *,
        base_url: str,
        card_url: str | None = None,
        headers: dict[str, str] | None = None,
        timeout_seconds: float = 45.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.card_url = (card_url or f"{self.base_url}/.well-known/agent.json").rstrip("/")
        self.headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            **(headers or {}),
        }
        self.timeout_seconds = timeout_seconds
        self._card: dict[str, Any] | None = None

    async def fetch_agent_card(self) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.get(self.card_url, headers=self.headers)
            response.raise_for_status()
            card = response.json()
        if not isinstance(card, dict):
            raise A2AClientError("Agent card must be a JSON object")
        self._card = card
        return card

    async def get_agent_card(self) -> dict[str, Any]:
        if self._card is None:
            return await self.fetch_agent_card()
        return self._card

    def _message_endpoint(self, card: dict[str, Any]) -> str:
        endpoints = card.get("endpoints") or card.get("url") or {}
        if isinstance(endpoints, str):
            return endpoints
        if isinstance(endpoints, dict):
            for key in ("message", "tasks", "rpc", "url"):
                if endpoints.get(key):
                    return str(endpoints[key])
        return f"{self.base_url}/v1/message:send"

    async def send_task(
        self,
        *,
        message: str,
        context: dict[str, Any] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        card = await self.get_agent_card()
        endpoint = self._message_endpoint(card)
        payload = {
            "id": str(uuid4()),
            "message": {
                "role": "user",
                "parts": [{"type": "text", "text": message}],
            },
            "context": context or {},
            "metadata": {
                "source": "troop",
                **(metadata or {}),
            },
        }
        async with httpx.AsyncClient(timeout=self.timeout_seconds) as client:
            response = await client.post(endpoint, json=payload, headers=self.headers)
            response.raise_for_status()
            data = response.json()
        return data if isinstance(data, dict) else {"result": data}

    async def describe(self) -> dict[str, Any]:
        card = await self.get_agent_card()
        return {
            "name": card.get("name") or card.get("id") or "external-agent",
            "description": card.get("description") or "",
            "capabilities": card.get("capabilities") or card.get("skills") or [],
            "url": self.base_url,
            "card_url": self.card_url,
            "provider": "a2a",
        }
