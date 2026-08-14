"""Outlook Mail OAuth, Microsoft Graph mail operations, subscriptions, and safe send."""

from __future__ import annotations

import hashlib
import json
import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.audit.repository import AuditRepository
from backend.modules.orchestration.execution.hitl.commit_authorization import (
    CommitAuthorizationError,
    authorize_and_claim_execution,
    build_idempotency_key,
    mark_execution_failed,
    mark_execution_sending,
    mark_execution_stale,
    mark_execution_succeeded,
)
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret
from backend.modules.workforce.integrations.email import (
    outlook_email_action_arguments_hash,
    outlook_thread_fingerprint,
)
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
    DraftExecutionMetadata,
    ExternalActionExecution,
    TriggerSubscription,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
OUTLOOK_AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
OUTLOOK_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
OUTLOOK_SCOPES = (
    "offline_access",
    "openid",
    "profile",
    "email",
    "Mail.Read",
    "Mail.ReadWrite",
    "Mail.Send",
)


class OutlookAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _graph_recipients(addresses: Any) -> list[dict[str, Any]]:
    raw = addresses if isinstance(addresses, list) else ([addresses] if addresses else [])
    recipients: list[dict[str, Any]] = []
    for item in raw:
        address = item.get("email") if isinstance(item, dict) else item
        if address:
            name = item.get("name") if isinstance(item, dict) else ""
            recipients.append(
                {"emailAddress": {"address": str(address), "name": str(name or "")}}
            )
    return recipients


def _graph_message_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "subject": str(arguments.get("subject") or ""),
        "body": {
            "contentType": "Text",
            "content": str(arguments.get("body") or arguments.get("body_text") or ""),
        },
        "toRecipients": _graph_recipients(arguments.get("to")),
    }
    cc = _graph_recipients(arguments.get("cc"))
    bcc = _graph_recipients(arguments.get("bcc"))
    if cc:
        payload["ccRecipients"] = cc
    if bcc:
        payload["bccRecipients"] = bcc
    return payload


class OutlookOAuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def begin(
        self,
        owner_id: str,
        *,
        company_id: str | None = None,
        scopes: list[str] | None = None,
        redirect_after: str | None = None,
    ) -> dict[str, Any]:
        if not settings.OUTLOOK_CLIENT_ID or not settings.OUTLOOK_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "outlook_not_configured",
                    "detail": "Required OAuth configuration is missing.",
                },
            )
        if not settings.OUTLOOK_CLIENT_SECRET:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "outlook_not_configured",
                    "detail": "Required OAuth client secret is missing.",
                },
            )
        requested = list(dict.fromkeys(scopes or OUTLOOK_SCOPES))
        if not set(requested).issubset(OUTLOOK_SCOPES):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported Outlook OAuth scope"
            )
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="outlook",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("outlook"),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.OUTLOOK_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": settings.OUTLOOK_OAUTH_REDIRECT_URI,
                "response_mode": "query",
                "scope": " ".join(requested),
                "state": state,
            }
        )
        return {"authorization_url": f"{OUTLOOK_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "outlook",
                ConnectorOAuthState.state_hash == state_hash,
            )
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if (
            oauth_state is None
            or oauth_state.consumed_at is not None
            or oauth_state.expires_at <= _utcnow()
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        async with managed_http_client("outlook-oauth") as client:
            response = await client.post(
                OUTLOOK_TOKEN_URL,
                data={
                    "client_id": settings.OUTLOOK_CLIENT_ID,
                    "client_secret": settings.OUTLOOK_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.OUTLOOK_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers=external_headers(),
            )
        token = response.json()
        if response.status_code >= 400 or "access_token" not in token:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                str(token.get("error_description") or token.get("error") or "Outlook OAuth failed"),
            )
        if not token.get("refresh_token"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Microsoft did not return the required offline refresh token",
            )
        definition = await self._outlook_definition()
        expires_at = _utcnow() + timedelta(seconds=max(0, int(token.get("expires_in") or 0)))
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Outlook Mail",
            status="active",
            config_json={
                "token_expires_at": expires_at.isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
                "token_type": token.get("token_type", "Bearer"),
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": token["access_token"],
                        "refresh_token": token["refresh_token"],
                    }
                )
            ),
            metadata_json={"provider": "outlook", "connection_state": "connected"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await self.db.flush()
        adapter = OutlookAdapter(self.db, installation)
        profile = await adapter.request("GET", "/me")
        email_address = str(profile.get("mail") or profile.get("userPrincipalName") or "")
        installation.name = email_address or "Outlook Mail"
        installation.metadata_json = {
            **installation.metadata_json,
            "email_address": email_address,
            "display_name": profile.get("displayName"),
        }
        await AuditRepository(self.db).log(
            "connector.outlook.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
            metadata={"company_id": installation.company_id},
        )
        await self.db.commit()
        await self.db.refresh(installation)
        from backend.modules.platform.activation_hooks import record_activation_for_owner

        await record_activation_for_owner(
            self.db,
            installation.owner_id,
            "first_connected_integration",
            at=installation.created_at,
            resource_type="connector_installation",
            resource_id=installation.id,
            metadata={"provider": "outlook"},
        )
        await self.db.commit()
        return installation, oauth_state.redirect_after

    async def _outlook_definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "outlook")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="outlook",
                name="Outlook Mail",
                description="Native Outlook Mail OAuth connector",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class OutlookAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> OutlookAdapter:
        result = await db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.slug == "outlook",
            )
        )
        row = result.first()
        if row is None:
            raise OutlookAPIError("Authorized Outlook installation not found")
        return cls(db, row[0])

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        access_token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if access_token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return access_token
        refresh_token = str(config.get("refresh_token") or "")
        if not refresh_token:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise OutlookAPIError("Outlook refresh token unavailable")
        async with managed_http_client("outlook-oauth") as client:
            response = await client.post(
                OUTLOOK_TOKEN_URL,
                data={
                    "client_id": settings.OUTLOOK_CLIENT_ID,
                    "client_secret": settings.OUTLOOK_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise OutlookAPIError(
                "Outlook token refresh rejected", status_code=response.status_code
            )
        token = response.json()
        access_token = str(token["access_token"])
        new_refresh = str(token.get("refresh_token") or refresh_token)
        self.installation.secrets_ref = encrypt_secret(
            json.dumps({"access_token": access_token, "refresh_token": new_refresh})
        )
        public = dict(self.installation.config_json or {})
        public["token_expires_at"] = (
            _utcnow() + timedelta(seconds=int(token.get("expires_in") or 3600))
        ).isoformat()
        self.installation.config_json = public
        await self.db.flush()
        return access_token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        headers = external_headers({"Authorization": f"Bearer {token}"})
        if extra_headers:
            headers.update(extra_headers)
        async with managed_http_client("microsoft-graph", base_url=GRAPH_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=headers,
            )
        if response.status_code == 401:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
        if response.status_code >= 400:
            message = "Outlook Graph request failed"
            with suppress(ValueError, AttributeError):
                body = response.json()
                message = str(body.get("error", {}).get("message") or body.get("message") or message)
            raise OutlookAPIError(
                message,
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "outlook.search_messages":
            return await self.request(
                "GET",
                "/me/messages",
                params={
                    "$search": f'"{str(arguments.get("query") or "")}"',
                    "$top": min(max(int(arguments.get("limit") or 25), 1), 100),
                },
                extra_headers={"ConsistencyLevel": "eventual"},
            )
        if operation == "outlook.get_message":
            return await self.request(
                "GET",
                f"/me/messages/{arguments['message_id']}",
                params={"$expand": "attachments"},
            )
        if operation == "outlook.get_thread":
            thread_id = str(arguments["thread_id"])
            result = await self.request(
                "GET",
                "/me/messages",
                params={
                    "$filter": f"conversationId eq '{thread_id}'",
                    "$orderby": "receivedDateTime asc",
                    "$top": 100,
                },
            )
            return {"conversation_id": thread_id, "value": result.get("value") or []}
        if operation == "outlook.create_draft":
            thread_id = str(arguments.get("thread_id") or "")
            if thread_id:
                anchor = await self._latest_thread_message(thread_id)
                draft = await self.request(
                    "POST",
                    f"/me/messages/{anchor['id']}/createReply",
                )
                return await self.request(
                    "PATCH",
                    f"/me/messages/{draft['id']}",
                    json_payload=_graph_message_payload(arguments),
                )
            return await self.request(
                "POST",
                "/me/messages",
                json_payload={**_graph_message_payload(arguments), "isDraft": True},
            )
        if operation == "outlook.update_draft":
            return await self.request(
                "PATCH",
                f"/me/messages/{arguments['outlook_draft_id']}",
                json_payload=_graph_message_payload(arguments),
            )
        if operation == "outlook.add_label":
            categories = list(arguments.get("add_label_ids") or arguments.get("categories") or [])
            return await self.request(
                "PATCH",
                f"/me/messages/{arguments['message_id']}",
                json_payload={"categories": categories},
            )
        if operation == "outlook.send_draft":
            return await self.send_draft_exactly_once(arguments)
        raise OutlookAPIError(f"Unsupported Outlook operation: {operation}")

    async def _latest_thread_message(self, thread_id: str) -> dict[str, Any]:
        thread = await self.execute("outlook.get_thread", {"thread_id": thread_id})
        messages = [
            item
            for item in thread.get("value") or []
            if not item.get("isDraft")
        ]
        if not messages:
            raise OutlookAPIError("Outlook conversation has no anchor message for reply draft")
        return messages[-1]

    async def _reconcile_ambiguous_outlook_send(
        self,
        existing: ExternalActionExecution,
        draft_id: str,
    ) -> None:
        try:
            await self.request("GET", f"/me/messages/{draft_id}")
        except OutlookAPIError as exc:
            if exc.status_code == 404:
                existing.status = "outcome_unknown"
                existing.error = (
                    "Draft disappeared after an ambiguous send; manual reconciliation "
                    "is required before retry"
                )
                await self.db.flush()
                raise OutlookAPIError(existing.error) from exc
            raise
        if existing.status == "sending":
            raise OutlookAPIError("Email send is already in progress", retryable=True)

    async def send_draft_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        owner_id = self.installation.owner_id
        workflow_run_id = str(arguments.get("workflow_run_id") or "")
        approval_id = str(arguments.get("approval_request_id") or "")
        draft_id = str(arguments.get("outlook_draft_id") or "")
        if not all((workflow_run_id, approval_id, draft_id)):
            raise OutlookAPIError(
                "outlook.send_draft requires workflow_run_id, approval_request_id, "
                "and outlook_draft_id"
            )
        args_hash = outlook_email_action_arguments_hash(arguments)
        try:
            claim = await authorize_and_claim_execution(
                self.db,
                owner_id=owner_id,
                action_key="outlook.send_draft",
                raw_arguments=arguments,
                approval_id=approval_id,
                idempotency_key=build_idempotency_key(
                    workflow_run_id, approval_id, draft_id, "outlook.send_draft"
                ),
                arguments_hash=args_hash,
                connector_installation_id=self.installation.id,
                workflow_run_id=workflow_run_id,
                require_consumed=True,
            )
        except CommitAuthorizationError as exc:
            message = str(exc)
            retryable = "Concurrent duplicate" in message
            if message == "Concurrent duplicate external action blocked":
                message = "Concurrent duplicate email send blocked"
            raise OutlookAPIError(message, retryable=retryable) from exc

        existing = claim.execution
        approval = claim.approval
        if claim.replayed:
            return dict(existing.result_json or {})

        if existing.status in {"sending", "retryable_failure"}:
            await self._reconcile_ambiguous_outlook_send(existing, draft_id)

        metadata_result = await self.db.execute(
            select(DraftExecutionMetadata).where(
                DraftExecutionMetadata.owner_id == owner_id,
                DraftExecutionMetadata.connector_installation_id == self.installation.id,
                DraftExecutionMetadata.provider_draft_id == draft_id,
            )
        )
        metadata = metadata_result.scalar_one_or_none()
        if metadata is None or metadata.content_hash != args_hash:
            await mark_execution_failed(
                self.db,
                existing,
                owner_id=owner_id,
                error="Draft content does not match approval fingerprint",
            )
            raise OutlookAPIError("Draft content does not match approval fingerprint")
        if metadata.thread_id:
            thread = await self.execute(
                "outlook.get_thread", {"thread_id": metadata.thread_id}
            )
            if outlook_thread_fingerprint(thread) != metadata.thread_fingerprint:
                metadata.status = "stale"
                stale_error = "Outlook thread changed while approval was pending"
                await mark_execution_stale(
                    self.db, existing, approval, error=stale_error
                )
                raise OutlookAPIError(stale_error)
        await mark_execution_sending(
            self.db,
            existing,
            owner_id=owner_id,
            audit_action="connector.outlook.send_attempted",
            audit_metadata={
                "workflow_run_id": workflow_run_id,
                "approval_request_id": approval_id,
                "draft_id": draft_id,
                "arguments_hash": args_hash,
            },
        )
        try:
            await self.request("POST", f"/me/messages/{draft_id}/send")
            sent = await self.request("GET", f"/me/messages/{draft_id}")
        except OutlookAPIError as exc:
            if exc.status_code == 404:
                sent = {"id": draft_id, "status": "sent"}
            else:
                await mark_execution_failed(
                    self.db,
                    existing,
                    owner_id=owner_id,
                    error=str(exc),
                    retryable=exc.retryable,
                    audit_action="connector.outlook.send_failed",
                    audit_metadata={
                        "retryable": exc.retryable,
                        "status_code": exc.status_code,
                    },
                )
                raise
        metadata.status = "sent"
        return await mark_execution_succeeded(
            self.db,
            existing,
            owner_id=owner_id,
            result_json=sent,
            external_result_id=str(sent.get("id") or draft_id),
            audit_action="connector.outlook.send_succeeded",
            audit_metadata={"external_message_id": str(sent.get("id") or draft_id)},
        )

    async def register_subscription(self, subscription: TriggerSubscription) -> dict[str, Any]:
        webhook_url = (settings.OUTLOOK_WEBHOOK_URL or "").strip()
        client_state = (settings.OUTLOOK_WEBHOOK_CLIENT_STATE or "").strip()
        if not webhook_url or not client_state:
            raise OutlookAPIError("Outlook webhook URL/client state are not configured")
        expiration = _utcnow() + timedelta(hours=48)
        body = {
            "changeType": "created",
            "notificationUrl": webhook_url,
            "resource": "me/mailFolders('Inbox')/messages",
            "expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%SZ"),
            "clientState": client_state,
        }
        created = await self.request("POST", "/subscriptions", json_payload=body)
        subscription.external_subscription_id = str(created.get("id") or "")
        subscription.external_cursor = str(created.get("resource") or "")
        subscription.expires_at = expiration
        subscription.status = "active"
        subscription.metadata_json = {
            **dict(subscription.metadata_json or {}),
            "subscription_response": {"id": created.get("id")},
        }
        await self.db.flush()
        return created

    async def renew_subscription(self, subscription: TriggerSubscription) -> dict[str, Any]:
        subscription_id = str(subscription.external_subscription_id or "")
        if not subscription_id:
            return await self.register_subscription(subscription)
        expiration = _utcnow() + timedelta(hours=48)
        renewed = await self.request(
            "PATCH",
            f"/subscriptions/{subscription_id}",
            json_payload={"expirationDateTime": expiration.strftime("%Y-%m-%dT%H:%M:%SZ")},
        )
        subscription.expires_at = expiration
        subscription.status = "active"
        await self.db.flush()
        return renewed

    async def stop_subscription(self, subscription: TriggerSubscription) -> None:
        subscription_id = str(subscription.external_subscription_id or "")
        if subscription_id:
            with suppress(OutlookAPIError):
                await self.request("DELETE", f"/subscriptions/{subscription_id}")

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        self.installation.metadata_json = {
            **dict(self.installation.metadata_json or {}),
            "connection_state": "revoked",
        }
        await AuditRepository(self.db).log(
            "connector.outlook.revoked",
            user_id=self.installation.owner_id,
            resource_type="connector_installation",
            resource_id=self.installation.id,
        )
        await self.db.flush()


def validate_outlook_webhook_client_state(client_state: str | None) -> bool:
    configured = (settings.OUTLOOK_WEBHOOK_CLIENT_STATE or "").strip()
    if not configured or not client_state:
        return False
    return secrets.compare_digest(client_state, configured)
