"""Microsoft Calendar connector provider."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.connectors._helpers import load_installation
from backend.modules.workforce.connectors.builtins import build_microsoft_calendar_manifest
from backend.modules.workforce.connectors.manifest import ConnectorManifest
from backend.modules.workforce.connectors.provider import (
    ConnectorActionResult,
    ConnectorAuthContext,
    ConnectorAuthResult,
    ConnectorHealthResult,
    ConnectorTriggerRegistration,
)
from backend.modules.workforce.integrations.microsoft_calendar import (
    MicrosoftCalendarAdapter,
    MicrosoftCalendarAPIError,
    MicrosoftCalendarOAuthService,
)


class MicrosoftCalendarConnectorProvider:
    @property
    def manifest(self) -> ConnectorManifest:
        return build_microsoft_calendar_manifest()

    async def authorize(
        self, db: AsyncSession, context: ConnectorAuthContext
    ) -> ConnectorAuthResult:
        try:
            result = await MicrosoftCalendarOAuthService(db).begin(
                context.owner_id,
                company_id=context.company_id,
                scopes=context.scopes,
                redirect_after=context.metadata.get("redirect_after"),
            )
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            return ConnectorAuthResult(status="failed", metadata={"error": detail})
        return ConnectorAuthResult(
            status="pending",
            authorization_url=str(result.get("authorization_url") or ""),
            metadata={"scopes": list(result.get("scopes") or [])},
        )

    async def refresh(self, db: AsyncSession, installation_id: str) -> ConnectorAuthResult:
        installation = await load_installation(db, installation_id, provider_slug="microsoft_calendar")
        adapter = MicrosoftCalendarAdapter(db, installation)
        try:
            await adapter._access_token()
            await db.commit()
            return ConnectorAuthResult(status=str(installation.status or "active"), installation_id=installation_id)
        except MicrosoftCalendarAPIError as exc:
            await db.commit()
            return ConnectorAuthResult(
                status="reauthorization_required",
                installation_id=installation_id,
                metadata={"error": str(exc)},
            )

    async def health(self, db: AsyncSession, installation_id: str) -> ConnectorHealthResult:
        installation = await load_installation(db, installation_id, provider_slug="microsoft_calendar")
        adapter = MicrosoftCalendarAdapter(db, installation)
        try:
            await adapter.request("GET", "/me/calendar")
            await db.commit()
            return ConnectorHealthResult(
                ok=True,
                status="healthy",
                reauth_required=installation.status == "reauthorization_required",
                details={"email_address": (installation.metadata_json or {}).get("email_address")},
            )
        except MicrosoftCalendarAPIError as exc:
            await db.commit()
            return ConnectorHealthResult(
                ok=False,
                status=str(installation.status or "unhealthy"),
                reauth_required=installation.status == "reauthorization_required",
                details={"error": str(exc), "status_code": exc.status_code},
            )

    async def register_trigger(
        self, db: AsyncSession, installation_id: str, trigger_slug: str, config: dict[str, Any]
    ) -> ConnectorTriggerRegistration:
        _ = (db, installation_id, trigger_slug, config)
        raise ValueError("Microsoft Calendar triggers are not supported yet")

    async def unregister_trigger(
        self, db: AsyncSession, installation_id: str, subscription_id: str
    ) -> None:
        _ = (db, installation_id, subscription_id)

    async def normalize_event(self, raw_event: dict[str, Any], *, installation_id: str | None = None):
        _ = (raw_event, installation_id)
        raise ValueError("Microsoft Calendar webhooks are not supported yet")

    async def execute_action(
        self,
        db: AsyncSession,
        installation_id: str,
        action_slug: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ConnectorActionResult:
        owner_id = str(context.get("owner_id") or "")
        if not owner_id:
            return ConnectorActionResult(status="denied", error="owner_id required")
        try:
            adapter = await MicrosoftCalendarAdapter.for_owner(
                db, owner_id=owner_id, installation_id=installation_id
            )
            output = await adapter.execute(action_slug, arguments)
            await db.commit()
            return ConnectorActionResult(status="succeeded", output=output)
        except MicrosoftCalendarAPIError as exc:
            await db.commit()
            return ConnectorActionResult(
                status="failed",
                error=str(exc),
                retryable=exc.retryable,
                provider_status_code=exc.status_code,
            )
