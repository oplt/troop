"""Outlook Mail connector provider."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.connectors._helpers import load_installation
from backend.modules.workforce.connectors.builtins import build_outlook_manifest
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
from backend.modules.workforce.integrations.outlook import (
    OutlookAdapter,
    OutlookAPIError,
    OutlookOAuthService,
    validate_outlook_webhook_client_state,
)
from backend.modules.workforce.models import TriggerSubscription


class OutlookConnectorProvider:
    @property
    def manifest(self) -> ConnectorManifest:
        return build_outlook_manifest()

    async def authorize(
        self,
        db: AsyncSession,
        context: ConnectorAuthContext,
    ) -> ConnectorAuthResult:
        try:
            result = await OutlookOAuthService(db).begin(
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

    async def refresh(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorAuthResult:
        installation = await load_installation(db, installation_id, provider_slug="outlook")
        adapter = OutlookAdapter(db, installation)
        try:
            await adapter._access_token()
            await db.commit()
            return ConnectorAuthResult(
                status=str(installation.status or "active"),
                installation_id=installation_id,
            )
        except OutlookAPIError as exc:
            await db.commit()
            return ConnectorAuthResult(
                status="reauthorization_required",
                installation_id=installation_id,
                metadata={"error": str(exc)},
            )

    async def health(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorHealthResult:
        installation = await load_installation(db, installation_id, provider_slug="outlook")
        adapter = OutlookAdapter(db, installation)
        try:
            profile = await adapter.request("GET", "/me")
            await db.commit()
            email_address = str(profile.get("mail") or profile.get("userPrincipalName") or "")
            return ConnectorHealthResult(
                ok=True,
                status="healthy",
                reauth_required=installation.status == "reauthorization_required",
                details={"email_address": email_address},
            )
        except OutlookAPIError as exc:
            await db.commit()
            return ConnectorHealthResult(
                ok=False,
                status=str(installation.status or "unhealthy"),
                reauth_required=installation.status == "reauthorization_required",
                details={"error": str(exc), "status_code": exc.status_code},
            )

    async def register_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        trigger_slug: str,
        config: dict[str, Any],
    ) -> ConnectorTriggerRegistration:
        if trigger_slug != "outlook.new_message":
            raise ValueError(f"Unsupported Outlook trigger: {trigger_slug}")
        subscription = await self._resolve_subscription(
            db,
            installation_id=installation_id,
            config=config,
        )
        adapter = await OutlookAdapter.for_owner(
            db,
            owner_id=subscription.owner_id,
            installation_id=installation_id,
        )
        created = await adapter.register_subscription(subscription)
        await db.commit()
        return ConnectorTriggerRegistration(
            trigger_slug=trigger_slug,
            subscription_id=subscription.id,
            metadata={"subscription_id": created.get("id"), "expiration": created.get("expirationDateTime")},
        )

    async def unregister_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        subscription_id: str,
    ) -> None:
        subscription = await db.get(TriggerSubscription, subscription_id)
        if subscription is None or subscription.connector_installation_id != installation_id:
            raise ValueError("Outlook trigger subscription not found")
        adapter = await OutlookAdapter.for_owner(
            db,
            owner_id=subscription.owner_id,
            installation_id=installation_id,
        )
        await adapter.stop_subscription(subscription)
        subscription.status = "disabled"
        await db.commit()

    async def normalize_event(
        self,
        raw_event: dict[str, Any],
        *,
        installation_id: str | None = None,
    ) -> ConnectorNormalizedEvent:
        resource = str(raw_event.get("resource") or "")
        change_type = str(raw_event.get("changeType") or "created")
        message_id = resource.rsplit("/", 1)[-1] if resource else str(raw_event.get("id") or "")
        dedupe = event_dedupe_key(
            "outlook",
            installation_id or "",
            change_type,
            message_id,
            str(raw_event.get("subscriptionId") or ""),
        )
        return ConnectorNormalizedEvent(
            event_type="outlook.mail_notification",
            dedupe_key=dedupe,
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
        if not owner_id:
            return ConnectorActionResult(status="denied", error="owner_id required")
        try:
            adapter = await OutlookAdapter.for_owner(
                db,
                owner_id=owner_id,
                installation_id=installation_id,
            )
            output = await adapter.execute(action_slug, arguments)
            await db.commit()
            return ConnectorActionResult(status="succeeded", output=output)
        except OutlookAPIError as exc:
            await db.commit()
            return ConnectorActionResult(
                status="failed",
                error=str(exc),
                retryable=exc.retryable,
                provider_status_code=exc.status_code,
            )

    async def _resolve_subscription(
        self,
        db: AsyncSession,
        *,
        installation_id: str,
        config: dict[str, Any],
    ) -> TriggerSubscription:
        subscription_id = str(config.get("subscription_id") or "")
        if subscription_id:
            subscription = await db.get(TriggerSubscription, subscription_id)
            if subscription is None or subscription.connector_installation_id != installation_id:
                raise ValueError("Outlook trigger subscription not found")
            return subscription
        owner_id = str(config.get("owner_id") or "")
        if not owner_id:
            raise ValueError("Outlook trigger registration requires owner_id or subscription_id")
        subscription = TriggerSubscription(
            owner_id=owner_id,
            company_id=config.get("company_id"),
            connector_installation_id=installation_id,
            workflow_id=str(config.get("workflow_id") or ""),
            workflow_version_id=str(config.get("workflow_version_id") or ""),
            node_id=str(config.get("node_id") or ""),
            provider="outlook",
            status="provisioning",
            metadata_json=dict(config.get("metadata_json") or {}),
        )
        db.add(subscription)
        await db.flush()
        return subscription


def outlook_webhook_client_state_valid(raw_event: dict[str, Any]) -> bool:
    return validate_outlook_webhook_client_state(str(raw_event.get("clientState") or ""))
