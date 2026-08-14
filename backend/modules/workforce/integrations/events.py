"""Durable external-event inbox and Gmail push/history processing."""

from __future__ import annotations

import base64
import hmac
import json
import time
from datetime import UTC, datetime, timedelta
from typing import Any

import jwt
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.http_clients import managed_http_client
from backend.modules.audit.repository import AuditRepository
from backend.modules.workforce.integrations.email import (
    event_dedupe_key,
    normalize_gmail_message,
)
from backend.modules.workforce.integrations.gmail import GmailAdapter, GmailAPIError
from backend.modules.workforce.models import (
    ConnectorInstallation,
    ExternalEvent,
    TriggerSubscription,
    WorkflowDefinition,
    WorkflowVersion,
)
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService

_GOOGLE_CERTS: dict[str, str] = {}
_GOOGLE_CERTS_EXPIRES_AT = 0.0


def verify_pubsub_token(authorization: str | None) -> bool:
    configured = settings.GOOGLE_PUBSUB_VERIFICATION_TOKEN
    if not configured or not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    return scheme.lower() == "bearer" and hmac.compare_digest(token, configured)


async def verify_pubsub_authentication(authorization: str | None) -> bool:
    """Validate Google Pub/Sub OIDC JWT; allow shared token only outside production."""
    if not authorization:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    if not settings.is_production and verify_pubsub_token(authorization):
        return True
    audience = settings.GOOGLE_PUBSUB_AUDIENCE.strip()
    service_account = settings.GOOGLE_PUBSUB_SERVICE_ACCOUNT_EMAIL.strip().lower()
    if not audience or not service_account:
        return False
    try:
        kid = str(jwt.get_unverified_header(token).get("kid") or "")
        if not kid:
            return False
        global _GOOGLE_CERTS, _GOOGLE_CERTS_EXPIRES_AT
        if time.monotonic() >= _GOOGLE_CERTS_EXPIRES_AT:
            async with managed_http_client("google-oidc-certs") as client:
                response = await client.get("https://www.googleapis.com/oauth2/v1/certs")
            if response.status_code >= 400:
                return False
            _GOOGLE_CERTS = {
                str(key): str(value) for key, value in dict(response.json()).items()
            }
            _GOOGLE_CERTS_EXPIRES_AT = time.monotonic() + 3600
        certificate = _GOOGLE_CERTS.get(kid)
        if not certificate:
            return False
        claims = jwt.decode(
            token,
            certificate,
            algorithms=["RS256"],
            audience=audience,
            options={"require": ["exp", "iat", "aud", "iss", "email"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        return False
    return (
        str(claims.get("iss") or "")
        in {"accounts.google.com", "https://accounts.google.com"}
        and str(claims.get("email") or "").lower() == service_account
        and claims.get("email_verified") is True
    )


def decode_pubsub_push(payload: dict[str, Any]) -> dict[str, str]:
    message = payload.get("message")
    if not isinstance(message, dict):
        raise ValueError("Pub/Sub message is required")
    encoded = message.get("data")
    if not isinstance(encoded, str):
        raise ValueError("Pub/Sub message.data is required")
    try:
        padded = encoded + "=" * (-len(encoded) % 4)
        decoded = json.loads(base64.b64decode(padded, validate=True))
    except (ValueError, json.JSONDecodeError) as exc:
        raise ValueError("Malformed Pub/Sub message data") from exc
    email_address = str(decoded.get("emailAddress") or "").strip().lower()
    history_id = str(decoded.get("historyId") or "").strip()
    if not email_address or not history_id:
        raise ValueError("Pub/Sub Gmail notification is missing emailAddress/historyId")
    return {
        "email_address": email_address,
        "history_id": history_id,
        "message_id": str(message.get("messageId") or ""),
    }


class ExternalEventService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def ingest_gmail_push(self, payload: dict[str, Any]) -> list[tuple[ExternalEvent, bool]]:
        decoded = decode_pubsub_push(payload)
        subscriptions_result = await self.db.execute(
            select(TriggerSubscription, ConnectorInstallation)
            .join(
                ConnectorInstallation,
                ConnectorInstallation.id == TriggerSubscription.connector_installation_id,
            )
            .where(
                TriggerSubscription.provider == "gmail",
                TriggerSubscription.status == "active",
                ConnectorInstallation.status == "active",
            )
        )
        matches: list[tuple[TriggerSubscription, ConnectorInstallation]] = []
        for subscription, installation in subscriptions_result.all():
            email_address = str(
                (installation.metadata_json or {}).get("email_address") or ""
            ).lower()
            if email_address == decoded["email_address"]:
                matches.append((subscription, installation))
        if not matches:
            raise ValueError("No active Gmail subscription for notification")
        ingested: list[tuple[ExternalEvent, bool]] = []
        for subscription, installation in matches:
            dedupe = event_dedupe_key(
                "gmail",
                installation.id,
                subscription.id,
                decoded["history_id"],
                decoded["message_id"],
            )
            event = ExternalEvent(
                owner_id=installation.owner_id,
                company_id=installation.company_id,
                provider="gmail",
                connector_installation_id=installation.id,
                external_event_id=decoded["message_id"] or None,
                event_type="gmail.history_notification",
                dedupe_key=dedupe,
                payload_json={
                    "history_id": decoded["history_id"],
                    "subscription_id": subscription.id,
                },
                status="pending",
            )
            self.db.add(event)
            try:
                await self.db.flush()
                await AuditRepository(self.db).log(
                    "external_event.gmail.received",
                    user_id=installation.owner_id,
                    resource_type="external_event",
                    resource_id=event.id,
                    metadata={
                        "connector_installation_id": installation.id,
                        "event_type": event.event_type,
                    },
                )
                await self.db.commit()
                await self.db.refresh(event)
                ingested.append((event, True))
            except IntegrityError:
                await self.db.rollback()
                existing_result = await self.db.execute(
                    select(ExternalEvent).where(
                        ExternalEvent.provider == "gmail",
                        ExternalEvent.dedupe_key == dedupe,
                    )
                )
                ingested.append((existing_result.scalar_one(), False))
        return ingested

    async def process(self, event_id: str) -> ExternalEvent:
        result = await self.db.execute(
            select(ExternalEvent).where(ExternalEvent.id == event_id).with_for_update()
        )
        event = result.scalar_one_or_none()
        if event is None:
            raise ValueError("External event not found")
        if event.status == "processed":
            return event
        if event.status == "processing":
            # Another worker holds the claim (or crashed mid-flight). Do not double-process.
            return event
        if event.status not in {"pending", "failed"}:
            return event
        event.status = "processing"
        await self.db.flush()
        try:
            if event.provider == "gmail":
                await self._process_gmail(event)
            else:
                raise ValueError(f"Unsupported external event provider: {event.provider}")
        except Exception as exc:
            event.retry_count += 1
            event.status = "failed"
            event.error = f"{type(exc).__name__}: {str(exc)[:500]}"
            await self.db.commit()
            raise
        event.status = "processed"
        event.processed_at = datetime.now(UTC)
        event.error = None
        await self.db.commit()
        await self.db.refresh(event)
        return event

    async def _process_gmail(self, event: ExternalEvent) -> None:
        subscription_id = str((event.payload_json or {}).get("subscription_id") or "")
        subscription = await self.db.get(TriggerSubscription, subscription_id)
        if (
            subscription is None
            or subscription.owner_id != event.owner_id
            or subscription.connector_installation_id != event.connector_installation_id
        ):
            raise ValueError("Gmail event subscription ownership mismatch")
        adapter = await GmailAdapter.for_owner(
            self.db,
            owner_id=event.owner_id,
            installation_id=event.connector_installation_id,
        )
        start_history_id = str(subscription.external_cursor or "")
        if not start_history_id:
            start_history_id = str((event.payload_json or {}).get("history_id") or "")
        try:
            history = await adapter.request(
                "GET",
                "/users/me/history",
                params={
                    "startHistoryId": start_history_id,
                    "historyTypes": "messageAdded",
                    "labelId": "INBOX",
                    "maxResults": 100,
                },
            )
        except GmailAPIError as exc:
            if exc.status_code == 404:
                subscription.status = "cursor_expired"
            raise
        seen_message_ids: set[str] = set()
        for item in history.get("history") or []:
            for added in item.get("messagesAdded") or []:
                message_id = str((added.get("message") or {}).get("id") or "")
                if not message_id or message_id in seen_message_ids:
                    continue
                seen_message_ids.add(message_id)
                child_dedupe = event_dedupe_key(
                    "gmail", event.connector_installation_id, "message_added", message_id
                )
                existing = await self.db.execute(
                    select(ExternalEvent).where(
                        ExternalEvent.provider == "gmail",
                        ExternalEvent.dedupe_key == child_dedupe,
                    )
                )
                child_event = existing.scalar_one_or_none()
                if child_event is not None and child_event.workflow_run_id:
                    continue
                message = await adapter.execute(
                    "gmail.get_message", {"message_id": message_id, "format": "full"}
                )
                normalized = normalize_gmail_message(
                    message,
                    connector_installation_id=event.connector_installation_id,
                )
                if child_event is None:
                    child_event = ExternalEvent(
                        owner_id=event.owner_id,
                        company_id=event.company_id,
                        provider="gmail",
                        connector_installation_id=event.connector_installation_id,
                        external_event_id=message_id,
                        event_type="gmail.message_added",
                        dedupe_key=child_dedupe,
                        payload_json={"email": normalized},
                        status="processing",
                    )
                    self.db.add(child_event)
                    await self.db.flush()
                runtime = WorkflowRuntimeService(self.db)
                workflow_run = await runtime.start_run(
                    event.owner_id,
                    subscription.workflow_id,
                    project_id=(subscription.metadata_json or {}).get("project_id"),
                    task_id=(subscription.metadata_json or {}).get("task_id"),
                    input_json={"email": normalized, "external_event_id": child_event.id},
                )
                child_event.workflow_run_id = workflow_run.id
                child_event.status = "processed"
                child_event.processed_at = datetime.now(UTC)
        newest = str(history.get("historyId") or (event.payload_json or {}).get("history_id") or "")
        if newest:
            subscription.external_cursor = newest
        subscription.last_event_at = datetime.now(UTC)


class TriggerSubscriptionService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def register_published_gmail_triggers(
        self,
        *,
        owner_id: str,
        definition: WorkflowDefinition,
        version: WorkflowVersion,
    ) -> list[TriggerSubscription]:
        created: list[TriggerSubscription] = []
        for node in version.nodes_json or []:
            if not isinstance(node, dict) or node.get("type") != "trigger":
                continue
            config = dict(node.get("config") or {})
            trigger_type = str(config.get("trigger_type") or "")
            if trigger_type not in {"gmail_new_message", "gmail.new_message"}:
                continue
            installation_id = str(config.get("connector_installation_id") or "")
            if not installation_id:
                raise ValueError("Gmail trigger requires connector_installation_id")
            from backend.modules.workforce.authz import assert_project_owned, assert_task_owned

            await assert_project_owned(self.db, owner_id, config.get("project_id"))
            await assert_task_owned(self.db, owner_id, config.get("task_id"))
            adapter = await GmailAdapter.for_owner(
                self.db, owner_id=owner_id, installation_id=installation_id
            )
            granted = set((adapter.installation.config_json or {}).get("granted_scopes") or [])
            if not granted.intersection(
                {
                    "https://www.googleapis.com/auth/gmail.readonly",
                    "https://www.googleapis.com/auth/gmail.modify",
                    "https://mail.google.com/",
                }
            ):
                raise ValueError("Gmail trigger installation lacks a mailbox read scope")
            existing_result = await self.db.execute(
                select(TriggerSubscription).where(
                    TriggerSubscription.workflow_version_id == version.id,
                    TriggerSubscription.node_id == str(node["id"]),
                    TriggerSubscription.connector_installation_id == installation_id,
                )
            )
            subscription = existing_result.scalar_one_or_none()
            if subscription is None:
                subscription = TriggerSubscription(
                    owner_id=owner_id,
                    company_id=definition.company_id,
                    connector_installation_id=installation_id,
                    workflow_id=definition.id,
                    workflow_version_id=version.id,
                    node_id=str(node["id"]),
                    provider="gmail",
                    status="provisioning",
                    metadata_json={
                        "project_id": config.get("project_id"),
                        "task_id": config.get("task_id"),
                    },
                )
                self.db.add(subscription)
                await self.db.flush()
            subscription.metadata_json = {
                **dict(subscription.metadata_json or {}),
                "project_id": config.get("project_id"),
                "task_id": config.get("task_id"),
            }
            await adapter.register_watch(subscription)
            created.append(subscription)
        return created

    async def renew_due_gmail_watches(self) -> int:
        cutoff = datetime.now(UTC) + timedelta(hours=settings.GMAIL_WATCH_RENEW_BEFORE_HOURS)
        result = await self.db.execute(
            select(TriggerSubscription).where(
                TriggerSubscription.provider == "gmail",
                TriggerSubscription.status.in_(("active", "watch_expiring")),
                TriggerSubscription.expires_at.is_not(None),
                TriggerSubscription.expires_at <= cutoff,
            )
        )
        renewed = 0
        for subscription in result.scalars().all():
            try:
                adapter = await GmailAdapter.for_owner(
                    self.db,
                    owner_id=subscription.owner_id,
                    installation_id=subscription.connector_installation_id,
                )
                await adapter.register_watch(subscription)
                renewed += 1
            except Exception:
                subscription.status = "renewal_failed"
        await self.db.commit()
        return renewed

    async def disable(self, owner_id: str, subscription_id: str) -> TriggerSubscription:
        result = await self.db.execute(
            select(TriggerSubscription).where(
                TriggerSubscription.id == subscription_id,
                TriggerSubscription.owner_id == owner_id,
            )
        )
        subscription = result.scalar_one_or_none()
        if subscription is None:
            raise ValueError("Trigger subscription not found")
        subscription.status = "disabled"
        await self.db.flush()
        if subscription.provider == "gmail":
            remaining_result = await self.db.execute(
                select(TriggerSubscription.id).where(
                    TriggerSubscription.connector_installation_id
                    == subscription.connector_installation_id,
                    TriggerSubscription.id != subscription.id,
                    TriggerSubscription.status == "active",
                )
            )
            if remaining_result.first() is None:
                adapter = await GmailAdapter.for_owner(
                    self.db,
                    owner_id=owner_id,
                    installation_id=subscription.connector_installation_id,
                )
                await adapter.stop_watch()
        await self.db.commit()
        await self.db.refresh(subscription)
        return subscription
