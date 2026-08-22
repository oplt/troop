"""Gmail OAuth, API operations, push watches, and safe send execution."""

from __future__ import annotations

import base64
import hashlib
import json
import secrets
from contextlib import suppress
from datetime import UTC, datetime, timedelta
from email.message import EmailMessage
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
    email_action_arguments_hash,
    thread_fingerprint,
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

GMAIL_API_BASE = "https://gmail.googleapis.com/gmail/v1"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GMAIL_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.compose",
    "https://www.googleapis.com/auth/gmail.send",
)


class GmailAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


def _encoded_message(arguments: dict[str, Any]) -> str:
    message = EmailMessage()
    message["To"] = ", ".join(
        str(item.get("email") if isinstance(item, dict) else item)
        for item in arguments.get("to") or []
    )
    for header, key in (("Cc", "cc"), ("Bcc", "bcc")):
        values = arguments.get(key) or []
        if values:
            message[header] = ", ".join(
                str(item.get("email") if isinstance(item, dict) else item) for item in values
            )
    if arguments.get("from"):
        message["From"] = str(arguments["from"])
    message["Subject"] = str(arguments.get("subject") or "")
    if arguments.get("in_reply_to"):
        message["In-Reply-To"] = str(arguments["in_reply_to"])
        message["References"] = str(arguments.get("references") or arguments["in_reply_to"])
    message.set_content(str(arguments.get("body") or arguments.get("body_text") or ""))
    return base64.urlsafe_b64encode(message.as_bytes()).decode().rstrip("=")


class GmailOAuthService:
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
        if not settings.GOOGLE_CLIENT_ID or not settings.GOOGLE_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "gmail_not_configured",
                    "detail": "Required OAuth configuration is missing.",
                },
            )
        if not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "gmail_not_configured",
                    "detail": "Required OAuth client secret is missing.",
                },
            )
        requested = list(dict.fromkeys(scopes or GMAIL_SCOPES))
        if not set(requested).issubset(GMAIL_SCOPES):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Unsupported Gmail OAuth scope"
            )
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="gmail",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret(verifier),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                "response_type": "code",
                "scope": " ".join(requested),
                "state": state,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
                "include_granted_scopes": "true",
            }
        )
        return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "gmail",
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
        verifier = decrypt_secret(oauth_state.encrypted_code_verifier)
        if not verifier:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth verifier unavailable")
        async with managed_http_client("google-oauth") as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": settings.GOOGLE_OAUTH_REDIRECT_URI,
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google OAuth exchange failed")
        token = response.json()
        if not token.get("access_token") or not token.get("refresh_token"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                "Google did not return the required offline refresh token",
            )
        definition = await self._gmail_definition()
        expires_at = _utcnow() + timedelta(seconds=max(0, int(token.get("expires_in") or 0)))
        secrets_payload = {
            "access_token": token["access_token"],
            "refresh_token": token["refresh_token"],
        }
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Gmail",
            status="active",
            config_json={
                "token_expires_at": expires_at.isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
                "token_type": token.get("token_type", "Bearer"),
            },
            secrets_ref=encrypt_secret(json.dumps(secrets_payload)),
            metadata_json={"provider": "gmail", "connection_state": "connected"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await self.db.flush()
        adapter = GmailAdapter(self.db, installation)
        profile = await adapter.request("GET", "/users/me/profile")
        installation.name = str(profile.get("emailAddress") or "Gmail")
        installation.metadata_json = {
            **installation.metadata_json,
            "email_address": profile.get("emailAddress"),
            "history_id": profile.get("historyId"),
        }
        await AuditRepository(self.db).log(
            "connector.gmail.connected",
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
            metadata={"provider": "gmail"},
        )
        await self.db.commit()
        return installation, oauth_state.redirect_after

    async def _gmail_definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "gmail")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="gmail",
                name="Gmail",
                description="Native Gmail OAuth connector",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class GmailAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> GmailAdapter:
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
                ConnectorDefinition.slug == "gmail",
            )
        )
        row = result.first()
        if row is None:
            raise GmailAPIError("Authorized Gmail installation not found")
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
            raise GmailAPIError("Gmail refresh token unavailable")
        async with managed_http_client("google-oauth") as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise GmailAPIError("Gmail token refresh rejected", status_code=response.status_code)
        token = response.json()
        access_token = str(token["access_token"])
        self.installation.secrets_ref = encrypt_secret(
            json.dumps({"access_token": access_token, "refresh_token": refresh_token})
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
    ) -> dict[str, Any]:
        token = await self._access_token()
        async with managed_http_client("gmail-api", base_url=GMAIL_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code == 401:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
        if response.status_code >= 400:
            message = "Gmail API request failed"
            with suppress(ValueError, AttributeError):
                message = str(response.json().get("error", {}).get("message") or message)
            raise GmailAPIError(
                message,
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "gmail.search_messages":
            return await self.request(
                "GET",
                "/users/me/messages",
                params={
                    "q": str(arguments.get("query") or ""),
                    "maxResults": min(max(int(arguments.get("limit") or 25), 1), 100),
                },
            )
        if operation == "gmail.get_message":
            return await self.request(
                "GET",
                f"/users/me/messages/{arguments['message_id']}",
                params={"format": arguments.get("format", "full")},
            )
        if operation == "gmail.get_thread":
            return await self.request(
                "GET",
                f"/users/me/threads/{arguments['thread_id']}",
                params={"format": arguments.get("format", "full")},
            )
        if operation == "gmail.create_draft":
            return await self.request(
                "POST",
                "/users/me/drafts",
                json_payload={
                    "message": {
                        "raw": _encoded_message(arguments),
                        **(
                            {"threadId": arguments["thread_id"]}
                            if arguments.get("thread_id")
                            else {}
                        ),
                    }
                },
            )
        if operation == "gmail.update_draft":
            return await self.request(
                "PUT",
                f"/users/me/drafts/{arguments['gmail_draft_id']}",
                json_payload={
                    "message": {
                        "raw": _encoded_message(arguments),
                        **(
                            {"threadId": arguments["thread_id"]}
                            if arguments.get("thread_id")
                            else {}
                        ),
                    }
                },
            )
        if operation == "gmail.add_label":
            return await self.request(
                "POST",
                f"/users/me/messages/{arguments['message_id']}/modify",
                json_payload={
                    "addLabelIds": list(arguments.get("add_label_ids") or []),
                    "removeLabelIds": list(arguments.get("remove_label_ids") or []),
                },
            )
        if operation == "gmail.send_draft":
            return await self.send_draft_exactly_once(arguments)
        raise GmailAPIError(f"Unsupported Gmail operation: {operation}")

    async def _reconcile_ambiguous_gmail_send(
        self,
        existing: ExternalActionExecution,
        draft_id: str,
    ) -> None:
        """Avoid duplicate provider POST when a prior attempt may have already sent."""
        try:
            await self.request("GET", f"/users/me/drafts/{draft_id}")
        except GmailAPIError as exc:
            if exc.status_code == 404:
                existing.status = "outcome_unknown"
                existing.error = (
                    "Draft disappeared after an ambiguous send; manual reconciliation "
                    "is required before retry"
                )
                await self.db.flush()
                raise GmailAPIError(existing.error) from exc
            raise
        if existing.status == "sending":
            raise GmailAPIError("Email send is already in progress", retryable=True)

    async def send_draft_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        owner_id = self.installation.owner_id
        workflow_run_id = str(arguments.get("workflow_run_id") or "")
        approval_id = str(arguments.get("approval_request_id") or "")
        draft_id = str(arguments.get("gmail_draft_id") or "")
        if not all((workflow_run_id, approval_id, draft_id)):
            raise GmailAPIError(
                "gmail.send_draft requires workflow_run_id, approval_request_id, and gmail_draft_id"
            )
        args_hash = email_action_arguments_hash(arguments)
        try:
            claim = await authorize_and_claim_execution(
                self.db,
                owner_id=owner_id,
                action_key="gmail.send_draft",
                raw_arguments=arguments,
                approval_id=approval_id,
                idempotency_key=build_idempotency_key(
                    workflow_run_id, approval_id, draft_id, "gmail.send_draft"
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
            raise GmailAPIError(message, retryable=retryable) from exc

        existing = claim.execution
        approval = claim.approval
        if claim.replayed:
            return dict(existing.result_json or {})

        if existing.status in {"sending", "retryable_failure"}:
            await self._reconcile_ambiguous_gmail_send(existing, draft_id)

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
            raise GmailAPIError("Draft content does not match approval fingerprint")
        if metadata.thread_id:
            thread = await self.execute(
                "gmail.get_thread", {"thread_id": metadata.thread_id, "format": "minimal"}
            )
            if thread_fingerprint(thread) != metadata.thread_fingerprint:
                metadata.status = "stale"
                stale_error = "Gmail thread changed while approval was pending"
                await mark_execution_stale(self.db, existing, approval, error=stale_error)
                raise GmailAPIError(stale_error)
        await mark_execution_sending(
            self.db,
            existing,
            owner_id=owner_id,
            audit_action="connector.gmail.send_attempted",
            audit_metadata={
                "workflow_run_id": workflow_run_id,
                "approval_request_id": approval_id,
                "draft_id": draft_id,
                "arguments_hash": args_hash,
            },
        )
        try:
            sent = await self.request(
                "POST", "/users/me/drafts/send", json_payload={"id": draft_id}
            )
        except GmailAPIError as exc:
            await mark_execution_failed(
                self.db,
                existing,
                owner_id=owner_id,
                error=str(exc),
                retryable=exc.retryable,
                audit_action="connector.gmail.send_failed",
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
            external_result_id=str(sent.get("id") or ""),
            audit_action="connector.gmail.send_succeeded",
            audit_metadata={"external_message_id": str(sent.get("id") or "")},
        )

    async def register_watch(self, subscription: TriggerSubscription) -> dict[str, Any]:
        watch = await self.request(
            "POST",
            "/users/me/watch",
            json_payload={
                "topicName": settings.GOOGLE_PUBSUB_TOPIC,
                "labelIds": ["INBOX"],
                "labelFilterBehavior": "include",
            },
        )
        subscription.external_cursor = str(watch.get("historyId") or "")
        subscription.external_subscription_id = settings.GOOGLE_PUBSUB_TOPIC
        expiration_ms = int(watch.get("expiration") or 0)
        subscription.expires_at = (
            datetime.fromtimestamp(expiration_ms / 1000, tz=UTC) if expiration_ms else None
        )
        subscription.status = "active"
        subscription.metadata_json = {
            **dict(subscription.metadata_json or {}),
            "watch_response": {"historyId": watch.get("historyId")},
        }
        await self.db.flush()
        return watch

    async def stop_watch(self) -> None:
        await self.request("POST", "/users/me/stop")

    async def revoke(self) -> None:
        config = resolve_installation_config(self.installation)
        token = str(config.get("refresh_token") or config.get("access_token") or "")
        if token:
            async with managed_http_client("google-oauth") as client:
                await client.post(
                    GOOGLE_REVOKE_URL,
                    data={"token": token},
                    headers=external_headers(),
                )
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        self.installation.metadata_json = {
            **dict(self.installation.metadata_json or {}),
            "connection_state": "revoked",
        }
        await AuditRepository(self.db).log(
            "connector.gmail.revoked",
            user_id=self.installation.owner_id,
            resource_type="connector_installation",
            resource_id=self.installation.id,
        )
        await self.db.flush()
