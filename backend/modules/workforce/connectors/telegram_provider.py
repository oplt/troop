"""Telegram connector provider — wraps existing bot API and webhook adapters."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.workforce.connectors._helpers import load_installation
from backend.modules.workforce.connectors.builtins import build_telegram_manifest
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
from backend.modules.workforce.integrations.telegram import TelegramAdapter, TelegramAPIError
from backend.modules.workforce.services.connector_service import resolve_installation_config


class TelegramConnectorProvider:
    @property
    def manifest(self) -> ConnectorManifest:
        return build_telegram_manifest()

    async def authorize(
        self,
        db: AsyncSession,
        context: ConnectorAuthContext,
    ) -> ConnectorAuthResult:
        token = str(context.metadata.get("bot_token") or "")
        if context.installation_id and not token:
            installation = await load_installation(
                db,
                context.installation_id,
                provider_slug="telegram",
                owner_id=context.owner_id,
            )
            config = resolve_installation_config(installation)
            token = str(config.get("bot_token") or config.get("token") or "")
        if not token:
            return ConnectorAuthResult(
                status="manual",
                metadata={
                    "detail": "Install Telegram connector with bot_token via /connectors/installations"
                },
            )
        health = await self._health_for_token(token)
        if not health.ok:
            return ConnectorAuthResult(status="failed", metadata=health.details)
        return ConnectorAuthResult(
            status="active",
            installation_id=context.installation_id,
            metadata=health.details,
        )

    async def refresh(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorAuthResult:
        health = await self.health(db, installation_id)
        status = "active" if health.ok else "failed"
        return ConnectorAuthResult(
            status=status,
            installation_id=installation_id,
            metadata=health.details,
        )

    async def health(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorHealthResult:
        installation = await load_installation(db, installation_id, provider_slug="telegram")
        config = resolve_installation_config(installation)
        token = str(config.get("bot_token") or config.get("token") or "")
        if not token:
            return ConnectorHealthResult(
                ok=False,
                status="misconfigured",
                details={"error": "bot_token unavailable"},
            )
        return await self._health_for_token(token)

    async def register_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        trigger_slug: str,
        config: dict[str, Any],
    ) -> ConnectorTriggerRegistration:
        if trigger_slug not in {"telegram.webhook", "telegram.update"}:
            raise ValueError(f"Unsupported Telegram trigger: {trigger_slug}")
        installation = await load_installation(db, installation_id, provider_slug="telegram")
        result = await TelegramAdapter(installation).configure_webhook()
        _ = config
        return ConnectorTriggerRegistration(
            trigger_slug=trigger_slug,
            subscription_id=installation_id,
            metadata=result,
        )

    async def unregister_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        subscription_id: str,
    ) -> None:
        installation = await load_installation(db, installation_id, provider_slug="telegram")
        config = resolve_installation_config(installation)
        token = str(config.get("bot_token") or config.get("token") or "")
        if not token:
            raise TelegramAPIError("Telegram bot token unavailable")
        async with managed_http_client("telegram-api") as client:
            response = await client.post(
                f"https://api.telegram.org/bot{token}/deleteWebhook",
                headers=external_headers(),
            )
        body = response.json()
        if response.status_code >= 400 or not body.get("ok"):
            raise TelegramAPIError("Telegram webhook deregistration failed")
        _ = subscription_id

    async def normalize_event(
        self,
        raw_event: dict[str, Any],
        *,
        installation_id: str | None = None,
    ) -> ConnectorNormalizedEvent:
        update_id = raw_event.get("update_id")
        if update_id is None:
            raise ValueError("Telegram update is missing update_id")
        if raw_event.get("callback_query"):
            event_type = "telegram.callback_query"
        elif raw_event.get("message"):
            event_type = "telegram.message"
        else:
            event_type = "telegram.update"
        return ConnectorNormalizedEvent(
            event_type=event_type,
            dedupe_key=event_dedupe_key("telegram", installation_id or "", update_id),
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
            installation = await load_installation(
                db,
                installation_id,
                provider_slug="telegram",
                owner_id=owner_id or None,
            )
            output = await TelegramAdapter(installation).execute(action_slug, arguments)
            return ConnectorActionResult(status="succeeded", output=output)
        except (TelegramAPIError, ValueError) as exc:
            return ConnectorActionResult(status="failed", error=str(exc))

    async def _health_for_token(self, token: str) -> ConnectorHealthResult:
        async with managed_http_client("telegram-api") as client:
            response = await client.get(
                f"https://api.telegram.org/bot{token}/getMe",
                headers=external_headers(),
            )
        if response.status_code >= 400:
            return ConnectorHealthResult(
                ok=False,
                status="unhealthy",
                details={"error": f"getMe failed ({response.status_code})"},
            )
        body = response.json()
        if not body.get("ok"):
            return ConnectorHealthResult(
                ok=False,
                status="unhealthy",
                details={"error": str(body.get("description") or "getMe failed")},
            )
        result = dict(body.get("result") or {})
        return ConnectorHealthResult(
            ok=True,
            status="healthy",
            details={"username": result.get("username"), "bot_id": result.get("id")},
        )
