"""Outbound webhook endpoints and delivery tests."""

from __future__ import annotations

import json
import secrets
from datetime import UTC, datetime

import httpx
from fastapi import HTTPException

from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.identity_access.models import User
from backend.modules.orchestration.security import encrypt_secret
from backend.modules.platform.models import WebhookEndpoint
from backend.modules.platform.webhooks.signing import (
    sign_webhook_body,
    validate_webhook_target,
    webhook_signing_secret,
)


class PlatformWebhooksMixin:
    async def list_webhooks_for_user(self, user: User) -> list[WebhookEndpoint]:
        await self.ensure_module_enabled("webhooks")
        return await self.repo.list_webhooks_for_user(user.id)

    async def create_webhook_for_user(
        self,
        user: User,
        *,
        target_url: str,
        description: str | None,
        events: list[str],
    ) -> tuple[WebhookEndpoint, str]:
        await self.ensure_module_enabled("webhooks")
        validate_webhook_target(target_url)
        signing_secret = secrets.token_urlsafe(20)
        webhook = await self.repo.create_webhook(
            user_id=user.id,
            target_url=target_url,
            description=description,
            secret=encrypt_secret(signing_secret),
            is_active=True,
            events_json=events,
        )
        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook, signing_secret

    async def update_webhook_for_user(
        self, user: User, webhook_id: str, payload: dict
    ) -> WebhookEndpoint:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        for field, value in payload.items():
            if field == "events":
                webhook.events_json = value
            elif field == "target_url" and value is not None:
                validate_webhook_target(str(value))
                webhook.target_url = str(value)
            elif value is not None:
                setattr(webhook, field, value)

        await self.db.commit()
        await self.db.refresh(webhook)
        return webhook

    async def delete_webhook_for_user(self, user: User, webhook_id: str) -> None:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")
        await self.repo.delete_webhook(webhook)
        await self.db.commit()

    async def test_webhook_for_user(self, user: User, webhook_id: str) -> dict:
        await self.ensure_module_enabled("webhooks")
        webhook = await self.repo.get_webhook_for_user(user.id, webhook_id)
        if not webhook:
            raise HTTPException(status_code=404, detail="Webhook endpoint not found")

        metadata = await self.get_platform_metadata()
        payload = {
            "event": "platform.test",
            "sent_at": datetime.now(UTC).isoformat(),
            "app_name": metadata.app_name,
            "core_domain_plural": metadata.core_domain_plural,
            "target_user_id": user.id,
        }
        raw_body = json.dumps(payload).encode("utf-8")
        signing_secret = webhook_signing_secret(webhook.secret)
        signature = sign_webhook_body(raw_body, signing_secret)

        try:
            async with managed_http_client("platform", timeout_seconds=10) as client:
                response = await client.post(
                    webhook.target_url,
                    content=raw_body,
                    headers=external_headers(
                        {
                            "Content-Type": "application/json",
                            "X-Generic-App-Event": payload["event"],
                            "X-Generic-App-Signature": signature,
                        }
                    ),
                )
            webhook.last_tested_at = datetime.now(UTC)
            webhook.last_response_status = response.status_code
            await self.db.commit()
            await self.db.refresh(webhook)
            return {
                "delivered": response.is_success,
                "status_code": response.status_code,
                "response_preview": response.text[:500] if response.text else None,
                "error": None,
            }
        except httpx.HTTPError as exc:
            webhook.last_tested_at = datetime.now(UTC)
            webhook.last_response_status = None
            await self.db.commit()
            await self.db.refresh(webhook)
            return {
                "delivered": False,
                "status_code": None,
                "response_preview": None,
                "error": str(exc),
            }
