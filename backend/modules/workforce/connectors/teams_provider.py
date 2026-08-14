"""Microsoft Teams connector provider."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.workforce.connectors._helpers import load_installation
from backend.modules.workforce.connectors.builtins import build_teams_manifest
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
from backend.modules.workforce.integrations.teams import (
    GRAPH_API_BASE,
    TeamsAdapter,
    TeamsAPIError,
)


class TeamsConnectorProvider:
    @property
    def manifest(self) -> ConnectorManifest:
        return build_teams_manifest()

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
            metadata={"detail": "Use /connectors/teams/authorize to connect Microsoft Teams"},
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
        try:
            installation = await load_installation(db, installation_id, provider_slug="teams")
            adapter = TeamsAdapter(db, installation)
            token = await adapter._access_token()
            async with managed_http_client("microsoft-graph", base_url=GRAPH_API_BASE) as client:
                response = await client.get(
                    "/me",
                    headers=external_headers({"Authorization": f"Bearer {token}"}),
                )
            if response.status_code >= 400:
                return ConnectorHealthResult(
                    ok=False,
                    status="unhealthy",
                    details={"error": f"/me failed ({response.status_code})"},
                )
            body = response.json()
            return ConnectorHealthResult(
                ok=True,
                status="healthy",
                details={"displayName": body.get("displayName"), "id": body.get("id")},
            )
        except (TeamsAPIError, ValueError) as exc:
            return ConnectorHealthResult(ok=False, status="unhealthy", details={"error": str(exc)})

    async def register_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        trigger_slug: str,
        config: dict[str, Any],
    ) -> ConnectorTriggerRegistration:
        _ = (db, installation_id, trigger_slug, config)
        raise ValueError("Teams triggers use Bot Framework messaging endpoint")

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
        activity_id = raw_event.get("id") or raw_event.get("timestamp")
        if activity_id is None:
            raise ValueError("Teams activity is missing id")
        event_type = str(raw_event.get("type") or "teams.activity")
        return ConnectorNormalizedEvent(
            event_type=f"teams.{event_type}",
            dedupe_key=event_dedupe_key("teams", installation_id or "", activity_id),
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
            adapter = await TeamsAdapter.for_owner(
                db,
                owner_id=owner_id,
                installation_id=installation_id,
            )
            output = await adapter.execute(action_slug, arguments)
            await db.commit()
            return ConnectorActionResult(status="succeeded", output=output)
        except (TeamsAPIError, ValueError) as exc:
            return ConnectorActionResult(status="failed", error=str(exc))
