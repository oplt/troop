"""Slack connector provider."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.workforce.connectors._helpers import load_installation
from backend.modules.workforce.connectors.builtins import build_slack_manifest
from backend.modules.workforce.connectors.manifest import ConnectorManifest
from backend.modules.workforce.connectors.provider import (
    ConnectorActionResult,
    ConnectorAuthContext,
    ConnectorAuthResult,
    ConnectorHealthResult,
    ConnectorNormalizedEvent,
    ConnectorTriggerRegistration,
)
from backend.modules.workforce.integrations.email import event_dedupe_key
from backend.modules.workforce.integrations.slack import (
    SLACK_API_BASE,
    SlackAdapter,
    SlackAPIError,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config


class SlackConnectorProvider:
    @property
    def manifest(self) -> ConnectorManifest:
        return build_slack_manifest()

    async def authorize(
        self,
        db: AsyncSession,
        context: ConnectorAuthContext,
    ) -> ConnectorAuthResult:
        if context.installation_id:
            health = await self.health(db, context.installation_id)
            return ConnectorAuthResult(
                status="active" if health.ok else "failed",
                installation_id=context.installation_id,
                metadata=health.details,
            )
        return ConnectorAuthResult(
            status="oauth_required",
            metadata={"detail": "Use /connectors/slack/authorize to connect Slack"},
        )

    async def refresh(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorAuthResult:
        health = await self.health(db, installation_id)
        return ConnectorAuthResult(
            status="active" if health.ok else "failed",
            installation_id=installation_id,
            metadata=health.details,
        )

    async def health(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorHealthResult:
        installation = await load_installation(db, installation_id, provider_slug="slack")
        config = resolve_installation_config(installation)
        token = str(config.get("bot_token") or "")
        if not token:
            return ConnectorHealthResult(
                ok=False,
                status="misconfigured",
                details={"error": "bot_token unavailable"},
            )
        async with managed_http_client("slack-api", base_url=SLACK_API_BASE) as client:
            response = await client.post(
                "/auth.test",
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        body = response.json()
        if response.status_code >= 400 or not body.get("ok"):
            return ConnectorHealthResult(
                ok=False,
                status="unhealthy",
                details={"error": str(body.get("error") or "auth.test failed")},
            )
        return ConnectorHealthResult(
            ok=True,
            status="healthy",
            details={
                "team": body.get("team"),
                "team_id": body.get("team_id"),
                "user_id": body.get("user_id"),
            },
        )

    async def register_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        trigger_slug: str,
        config: dict[str, Any],
    ) -> ConnectorTriggerRegistration:
        _ = (db, installation_id, trigger_slug, config)
        raise ValueError("Slack triggers are configured via Events API webhooks")

    async def unregister_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        subscription_id: str,
    ) -> None:
        _ = (db, installation_id, subscription_id)

    async def normalize_event(
        self,
        raw_event: dict[str, Any],
        *,
        installation_id: str | None = None,
    ) -> ConnectorNormalizedEvent:
        event_id = raw_event.get("event_id") or raw_event.get("event_time")
        if event_id is None:
            raise ValueError("Slack event is missing event_id")
        event = dict(raw_event.get("event") or {})
        event_type = str(event.get("type") or raw_event.get("type") or "slack.event")
        return ConnectorNormalizedEvent(
            event_type=f"slack.{event_type}",
            dedupe_key=event_dedupe_key("slack", installation_id or "", event_id),
            payload=raw_event,
            installation_id=installation_id,
        )

    async def execute_action(
        self,
        db: AsyncSession,
        installation_id: str,
        action_slug: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ConnectorActionResult:
        owner_id = str(context.get("owner_id") or "")
        try:
            adapter = await SlackAdapter.for_owner(
                db,
                owner_id=owner_id,
                installation_id=installation_id,
            )
            output = await adapter.execute(action_slug, arguments)
            await db.commit()
            return ConnectorActionResult(status="succeeded", output=output)
        except (SlackAPIError, ValueError) as exc:
            return ConnectorActionResult(status="failed", error=str(exc))
