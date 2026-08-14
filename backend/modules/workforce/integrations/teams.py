"""Microsoft Teams OAuth, Graph messaging, Bot Framework webhooks, and approval channel."""

from __future__ import annotations

import hashlib
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

import jwt
from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.audit.repository import AuditRepository
from backend.modules.identity_access.models import User
from backend.modules.orchestration.execution.hitl.commit_authorization import (
    CommitAuthorizationError,
    authorize_and_claim_execution,
    build_idempotency_key,
    mark_execution_failed,
    mark_execution_sending,
    mark_execution_succeeded,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.security import encrypt_secret
from backend.modules.orchestration.services.approvals_domain import ApprovalsService
from backend.modules.workforce.models import (
    ApprovalDelivery,
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
    TeamsIdentityBinding,
    WorkflowRun,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
TEAMS_AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
TEAMS_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
BOTFRAMEWORK_OPENID = "https://login.botframework.com/v1/.well-known/openidconfiguration"
TEAMS_SCOPES = (
    "offline_access",
    "openid",
    "profile",
    "Chat.Read",
    "Chat.ReadWrite",
    "ChannelMessage.Read.All",
    "ChannelMessage.Send",
)

_BOTFRAMEWORK_JWKS: dict[str, str] = {}
_BOTFRAMEWORK_JWKS_EXPIRES_AT = 0.0


class TeamsAPIError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_link_token(token: str) -> str:
    return _hash_secret(token)


def teams_action_arguments_hash(arguments: dict[str, Any]) -> str:
    payload = {
        "conversation_id": str(arguments.get("conversation_id") or ""),
        "reply_to_id": str(arguments.get("reply_to_id") or ""),
        "text": str(arguments.get("text") or ""),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


async def validate_teams_bot_jwt(authorization: str | None) -> bool:
    """Validate Bot Framework JWT on incoming Teams activities."""
    app_id = (settings.TEAMS_BOT_APP_ID or settings.TEAMS_CLIENT_ID or "").strip()
    if not authorization or not app_id:
        return False
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return False
    try:
        global _BOTFRAMEWORK_JWKS, _BOTFRAMEWORK_JWKS_EXPIRES_AT
        if time.monotonic() >= _BOTFRAMEWORK_JWKS_EXPIRES_AT:
            async with managed_http_client("botframework-oidc") as client:
                meta = await client.get(BOTFRAMEWORK_OPENID)
            if meta.status_code >= 400:
                return False
            jwks_uri = str(meta.json().get("jwks_uri") or "")
            if not jwks_uri:
                return False
            async with managed_http_client("botframework-jwks") as client:
                jwks = await client.get(jwks_uri)
            if jwks.status_code >= 400:
                return False
            keys = {
                str(item.get("kid")): jwt.algorithms.RSAAlgorithm.from_jwk(json.dumps(item))
                for item in jwks.json().get("keys") or []
                if item.get("kid")
            }
            _BOTFRAMEWORK_JWKS = keys
            _BOTFRAMEWORK_JWKS_EXPIRES_AT = time.monotonic() + 3600
        kid = str(jwt.get_unverified_header(token).get("kid") or "")
        key = _BOTFRAMEWORK_JWKS.get(kid)
        if not key:
            return False
        claims = jwt.decode(
            token,
            key,
            algorithms=["RS256"],
            audience=app_id,
            options={"require": ["exp", "iat", "aud", "iss"]},
        )
    except (jwt.PyJWTError, ValueError, TypeError):
        return False
    issuer = str(claims.get("iss") or "")
    return issuer.startswith("https://") and "botframework" in issuer


class TeamsOAuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def begin(
        self,
        owner_id: str,
        *,
        company_id: str | None = None,
        redirect_after: str | None = None,
    ) -> dict[str, Any]:
        if not settings.TEAMS_CLIENT_ID or not settings.TEAMS_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "teams_not_configured", "detail": "Teams OAuth is not configured"},
            )
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="teams",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("teams"),
            requested_scopes_json=list(TEAMS_SCOPES),
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.TEAMS_CLIENT_ID,
                "response_type": "code",
                "redirect_uri": settings.TEAMS_OAUTH_REDIRECT_URI,
                "response_mode": "query",
                "scope": " ".join(TEAMS_SCOPES),
                "state": state,
            }
        )
        return {"authorization_url": f"{TEAMS_AUTHORIZE_URL}?{query}", "scopes": list(TEAMS_SCOPES)}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "teams",
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
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired Teams OAuth state")
        async with managed_http_client("teams-oauth") as client:
            response = await client.post(
                TEAMS_TOKEN_URL,
                data={
                    "client_id": settings.TEAMS_CLIENT_ID,
                    "client_secret": settings.TEAMS_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.TEAMS_OAUTH_REDIRECT_URI,
                    "grant_type": "authorization_code",
                },
                headers=external_headers(),
            )
        body = response.json()
        if response.status_code >= 400 or "access_token" not in body:
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                str(body.get("error_description") or body.get("error") or "Teams OAuth failed"),
            )
        access_token = str(body["access_token"])
        refresh_token = str(body.get("refresh_token") or "")
        id_claims: dict[str, Any] = {}
        id_token = str(body.get("id_token") or "")
        if id_token:
            with __import__("contextlib").suppress(jwt.PyJWTError):
                id_claims = jwt.decode(id_token, options={"verify_signature": False})
        tenant_id = str(id_claims.get("tid") or "")
        user_name = str(id_claims.get("name") or id_claims.get("preferred_username") or "Teams user")

        definition_result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "teams")
        )
        definition = definition_result.scalar_one_or_none()
        if definition is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Teams connector definition missing")

        existing_result = await self.db.execute(
            select(ConnectorInstallation).where(
                ConnectorInstallation.owner_id == oauth_state.owner_id,
                ConnectorInstallation.connector_definition_id == definition.id,
            )
        )
        installation = existing_result.scalar_one_or_none()
        expires_in = int(body.get("expires_in") or 3600)
        public_config = {
            "tenant_id": tenant_id,
            "tenant_name": user_name,
            "teams_user_id": str(id_claims.get("oid") or id_claims.get("sub") or ""),
            "granted_scopes": str(body.get("scope") or "").split(),
            "token_expires_at": (_utcnow() + timedelta(seconds=expires_in)).isoformat(),
        }
        secrets_payload = {"access_token": access_token}
        if refresh_token:
            secrets_payload["refresh_token"] = refresh_token
        if installation is None:
            installation = ConnectorInstallation(
                owner_id=oauth_state.owner_id,
                company_id=oauth_state.company_id,
                connector_definition_id=definition.id,
                name=f"Teams · {tenant_id or user_name}",
                status="active",
                config_json=public_config,
                secrets_ref=encrypt_secret(json.dumps(secrets_payload)),
            )
            self.db.add(installation)
        else:
            installation.status = "active"
            installation.name = f"Teams · {tenant_id or user_name}"
            installation.config_json = public_config
            installation.secrets_ref = encrypt_secret(json.dumps(secrets_payload))
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.teams.oauth_connected",
            user_id=oauth_state.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
            metadata={"tenant_id": tenant_id},
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after


class TeamsAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls,
        db: AsyncSession,
        *,
        owner_id: str,
        installation_id: str,
    ) -> TeamsAdapter:
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
                ConnectorDefinition.slug == "teams",
            )
        )
        row = result.first()
        if row is None:
            raise TeamsAPIError("Authorized Teams installation not found")
        return cls(db, row[0])

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return token
        refresh_token = str(config.get("refresh_token") or "")
        if not refresh_token:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise TeamsAPIError("Teams refresh token unavailable")
        async with managed_http_client("teams-oauth") as client:
            response = await client.post(
                TEAMS_TOKEN_URL,
                data={
                    "client_id": settings.TEAMS_CLIENT_ID,
                    "client_secret": settings.TEAMS_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise TeamsAPIError("Teams token refresh rejected")
        body = response.json()
        access_token = str(body["access_token"])
        self.installation.secrets_ref = encrypt_secret(
            json.dumps({"access_token": access_token, "refresh_token": refresh_token})
        )
        public = dict(self.installation.config_json or {})
        public["token_expires_at"] = (
            _utcnow() + timedelta(seconds=int(body.get("expires_in") or 3600))
        ).isoformat()
        self.installation.config_json = public
        await self.db.flush()
        return access_token

    async def _graph(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        async with managed_http_client("microsoft-graph", base_url=GRAPH_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=external_headers(
                    {
                        "Authorization": f"Bearer {token}",
                        **({"ConsistencyLevel": "eventual"} if path.startswith("/search") else {}),
                    }
                ),
            )
        if response.status_code >= 400:
            retryable = response.status_code in {408, 429, 500, 502, 503, 504}
            raise TeamsAPIError(
                f"Graph request failed ({response.status_code})",
                retryable=retryable,
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "teams.search_messages":
            query = str(arguments.get("query") or "").strip()
            if query:
                return await self._graph(
                    "POST",
                    "/search/query",
                    json_payload={
                        "requests": [
                            {
                                "entityTypes": ["chatMessage"],
                                "query": {"queryString": query},
                                "from": 0,
                                "size": int(arguments.get("limit") or 20),
                            }
                        ]
                    },
                )
            conversation_id = str(arguments.get("conversation_id") or "")
            if not conversation_id:
                raise TeamsAPIError("search requires query or conversation_id")
            return await self._graph("GET", f"/chats/{conversation_id}/messages")
        if operation == "teams.get_thread":
            conversation_id = str(arguments["conversation_id"])
            message_id = str(arguments["message_id"])
            return await self._graph(
                "GET",
                f"/chats/{conversation_id}/messages/{message_id}/replies",
            )
        if operation == "teams.get_message":
            conversation_id = str(arguments["conversation_id"])
            message_id = str(arguments["message_id"])
            return await self._graph("GET", f"/chats/{conversation_id}/messages/{message_id}")
        if operation == "teams.post_message":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.post_message_exactly_once(arguments)
            conversation_id = str(arguments["conversation_id"])
            payload = {
                "body": {"contentType": "html", "content": str(arguments.get("text") or "")},
            }
            if arguments.get("attachments"):
                payload["attachments"] = arguments["attachments"]
            if arguments.get("reply_to_id"):
                return await self._graph(
                    "POST",
                    f"/chats/{conversation_id}/messages/{arguments['reply_to_id']}/replies",
                    json_payload={"body": payload["body"]},
                )
            return await self._graph("POST", f"/chats/{conversation_id}/messages", json_payload=payload)
        if operation == "teams.update_message":
            conversation_id = str(arguments["conversation_id"])
            message_id = str(arguments["message_id"])
            return await self._graph(
                "PATCH",
                f"/chats/{conversation_id}/messages/{message_id}",
                json_payload={
                    "body": {"contentType": "html", "content": str(arguments.get("text") or "")}
                },
            )
        raise TeamsAPIError(f"Unsupported Teams operation: {operation}")

    async def post_message_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        owner_id = self.installation.owner_id
        workflow_run_id = str(arguments.get("workflow_run_id") or "")
        approval_id = str(arguments.get("approval_request_id") or "")
        conversation_id = str(arguments.get("conversation_id") or "")
        if not all((workflow_run_id, approval_id, conversation_id)):
            raise TeamsAPIError(
                "teams.post_message requires workflow_run_id, approval_request_id, and conversation_id"
            )
        reply_to_id = str(arguments.get("reply_to_id") or "root")
        args_hash = teams_action_arguments_hash(arguments)
        try:
            claim = await authorize_and_claim_execution(
                self.db,
                owner_id=owner_id,
                action_key="teams.post_message",
                raw_arguments=arguments,
                approval_id=approval_id,
                idempotency_key=build_idempotency_key(
                    workflow_run_id, approval_id, conversation_id, reply_to_id, "teams.post_message"
                ),
                arguments_hash=args_hash,
                connector_installation_id=self.installation.id,
                workflow_run_id=workflow_run_id,
                require_consumed=True,
            )
        except CommitAuthorizationError as exc:
            raise TeamsAPIError(str(exc), retryable="Concurrent duplicate" in str(exc)) from exc
        existing = claim.execution
        if claim.replayed:
            return dict(existing.result_json or {})
        await mark_execution_sending(
            self.db,
            existing,
            owner_id=owner_id,
            audit_action="connector.teams.post_attempted",
            audit_metadata={
                "workflow_run_id": workflow_run_id,
                "approval_request_id": approval_id,
                "conversation_id": conversation_id,
                "arguments_hash": args_hash,
            },
        )
        try:
            conversation_id = str(arguments.get("conversation_id") or "")
            body = {"contentType": "html", "content": str(arguments.get("text") or "")}
            if arguments.get("reply_to_id"):
                result = await self._graph(
                    "POST",
                    f"/chats/{conversation_id}/messages/{arguments['reply_to_id']}/replies",
                    json_payload={"body": body},
                )
            else:
                payload: dict[str, Any] = {"body": body}
                if arguments.get("attachments"):
                    payload["attachments"] = arguments["attachments"]
                result = await self._graph(
                    "POST",
                    f"/chats/{conversation_id}/messages",
                    json_payload=payload,
                )
        except TeamsAPIError as exc:
            await mark_execution_failed(self.db, existing, owner_id=owner_id, error=str(exc))
            raise
        await mark_execution_succeeded(
            self.db,
            existing,
            owner_id=owner_id,
            result=result,
            audit_action="connector.teams.post_succeeded",
        )
        await self.db.commit()
        return result

    async def reply_activity(self, activity: dict[str, Any], text: str) -> dict[str, Any]:
        service_url = str(activity.get("serviceUrl") or "").rstrip("/")
        conversation = dict(activity.get("conversation") or {})
        conversation_id = str(conversation.get("id") or "")
        if not service_url or not conversation_id:
            raise TeamsAPIError("Teams activity missing serviceUrl or conversation")
        token = await self._bot_access_token()
        payload = {
            "type": "message",
            "from": dict(activity.get("recipient") or {}),
            "conversation": conversation,
            "recipient": dict(activity.get("from") or {}),
            "text": text,
            "replyToId": activity.get("id"),
        }
        async with managed_http_client("teams-bot") as client:
            response = await client.post(
                f"{service_url}/v3/conversations/{conversation_id}/activities",
                json=payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise TeamsAPIError(f"Bot reply failed ({response.status_code})")
        return response.json() if response.content else {}

    async def send_adaptive_card(
        self,
        *,
        service_url: str,
        conversation: dict[str, Any],
        recipient: dict[str, Any],
        card: dict[str, Any],
    ) -> dict[str, Any]:
        token = await self._bot_access_token()
        conversation_id = str(conversation.get("id") or "")
        payload = {
            "type": "message",
            "from": recipient,
            "conversation": conversation,
            "attachments": [
                {
                    "contentType": "application/vnd.microsoft.card.adaptive",
                    "content": card,
                }
            ],
        }
        async with managed_http_client("teams-bot") as client:
            response = await client.post(
                f"{service_url.rstrip('/')}/v3/conversations/{conversation_id}/activities",
                json=payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise TeamsAPIError(f"Adaptive card send failed ({response.status_code})")
        return response.json() if response.content else {}

    async def _bot_access_token(self) -> str:
        app_id = (settings.TEAMS_BOT_APP_ID or settings.TEAMS_CLIENT_ID or "").strip()
        secret = (settings.TEAMS_CLIENT_SECRET or "").strip()
        if not app_id or not secret:
            raise TeamsAPIError("Teams bot credentials are not configured")
        async with managed_http_client("teams-bot-auth") as client:
            response = await client.post(
                "https://login.microsoftonline.com/botframework.com/oauth2/v2.0/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": app_id,
                    "client_secret": secret,
                    "scope": "https://api.botframework.com/.default",
                },
                headers=external_headers(),
            )
        body = response.json()
        if response.status_code >= 400 or "access_token" not in body:
            raise TeamsAPIError("Teams bot token exchange failed")
        return str(body["access_token"])


class TeamsIdentityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_link(
        self, owner_id: str, installation_id: str, *, company_id: str | None = None
    ) -> tuple[TeamsIdentityBinding, str]:
        installation = await self.get_installation(owner_id, installation_id)
        token = secrets.token_urlsafe(24)
        row = TeamsIdentityBinding(
            owner_id=owner_id,
            company_id=company_id or installation.company_id,
            connector_installation_id=installation.id,
            teams_tenant_id=str((installation.config_json or {}).get("tenant_id") or ""),
            link_token_hash=hash_link_token(token),
            status="pending",
            token_expires_at=_utcnow() + timedelta(minutes=settings.TEAMS_LINK_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row, token

    async def consume_link(
        self,
        token: str,
        *,
        teams_user_id: str,
        teams_tenant_id: str,
        conversation_id: str,
        teams_username: str | None = None,
    ) -> TeamsIdentityBinding:
        result = await self.db.execute(
            select(TeamsIdentityBinding)
            .where(TeamsIdentityBinding.link_token_hash == hash_link_token(token))
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None or row.status != "pending" or row.token_expires_at <= _utcnow():
            raise ValueError("Invalid or expired Teams link token")
        if row.teams_tenant_id and teams_tenant_id and row.teams_tenant_id != teams_tenant_id:
            raise ValueError("Teams tenant does not match installation")
        existing = await self.db.execute(
            select(TeamsIdentityBinding).where(
                TeamsIdentityBinding.connector_installation_id == row.connector_installation_id,
                TeamsIdentityBinding.teams_user_id == teams_user_id,
                TeamsIdentityBinding.status == "active",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Teams identity is already linked")
        row.teams_user_id = teams_user_id
        row.conversation_id = conversation_id
        row.teams_username = teams_username
        if teams_tenant_id:
            row.teams_tenant_id = teams_tenant_id
        row.status = "active"
        row.linked_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.teams.identity_linked",
            user_id=row.owner_id,
            resource_type="teams_identity_binding",
            resource_id=row.id,
            metadata={"connector_installation_id": row.connector_installation_id},
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def revoke(self, owner_id: str, binding_id: str) -> None:
        result = await self.db.execute(
            select(TeamsIdentityBinding).where(
                TeamsIdentityBinding.id == binding_id,
                TeamsIdentityBinding.owner_id == owner_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Teams binding not found")
        row.status = "revoked"
        row.revoked_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.teams.identity_revoked",
            user_id=row.owner_id,
            resource_type="teams_identity_binding",
            resource_id=row.id,
        )
        await self.db.commit()

    async def get_installation(self, owner_id: str, installation_id: str) -> ConnectorInstallation:
        result = await self.db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.slug == "teams",
            )
        )
        row = result.first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Teams installation not found")
        return row[0]


class TeamsWebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def handle(self, activity: dict[str, Any]) -> dict[str, Any]:
        activity_type = str(activity.get("type") or "")
        if activity_type == "message":
            return await self._message(activity)
        if activity_type == "invoke":
            return await self._invoke(activity)
        return {"status": "ignored"}

    async def _message(self, activity: dict[str, Any]) -> dict[str, Any]:
        sender = dict(activity.get("from") or {})
        conversation = dict(activity.get("conversation") or {})
        channel_data = dict(activity.get("channelData") or {})
        tenant_id = str((channel_data.get("tenant") or {}).get("id") or "")
        teams_user_id = str(sender.get("aadObjectId") or sender.get("id") or "")
        conversation_id = str(conversation.get("id") or "")
        text = str(activity.get("text") or "").strip()
        if text.lower().startswith("link "):
            token = text.split(maxsplit=1)[1].strip()
            installation = await self._installation_for_tenant(tenant_id)
            if installation is None:
                raise ValueError("Teams tenant installation not found")
            binding = await TeamsIdentityService(self.db).consume_link(
                token,
                teams_user_id=teams_user_id,
                teams_tenant_id=tenant_id,
                conversation_id=conversation_id,
                teams_username=sender.get("name"),
            )
            adapter = TeamsAdapter(self.db, installation)
            await adapter.reply_activity(activity, "✅ Microsoft Teams account linked to Troop.")
            _ = binding
            return {"status": "linked"}
        return {"status": "ignored"}

    async def _invoke(self, activity: dict[str, Any]) -> dict[str, Any]:
        if str(activity.get("name") or "") != "adaptiveCard/action":
            return {"status": "ignored"}
        value = dict(activity.get("value") or {})
        action = dict(value.get("action") or value)
        data = dict(action.get("data") or value.get("data") or {})
        troop_action = str(data.get("troop_action") or "")
        approval_id = str(data.get("approval_id") or "")
        if troop_action not in {"approve", "reject"} or not approval_id:
            return {"status": "ignored"}
        sender = dict(activity.get("from") or {})
        channel_data = dict(activity.get("channelData") or {})
        tenant_id = str((channel_data.get("tenant") or {}).get("id") or "")
        teams_user_id = str(sender.get("aadObjectId") or sender.get("id") or "")
        conversation = dict(activity.get("conversation") or {})
        conversation_id = str(conversation.get("id") or "")
        approval, binding, delivery = await self._authorized_context(
            approval_id=approval_id,
            teams_user_id=teams_user_id,
            tenant_id=tenant_id,
            conversation_id=conversation_id,
        )
        installation = await self.db.get(ConnectorInstallation, binding.connector_installation_id)
        if installation is None:
            raise ValueError("Teams installation missing")
        adapter = TeamsAdapter(self.db, installation)
        troop_user = await self.db.get(User, binding.owner_id)
        if troop_user is None:
            raise ValueError("Linked Troop user missing")
        decision = "approved" if troop_action == "approve" else "rejected"
        reason = None if decision == "approved" else "Rejected from Microsoft Teams"
        await ApprovalsService(self.db).decide_approval(troop_user, approval.id, decision, reason)
        delivery.status = decision
        delivery.responded_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.teams.approval_decided",
            user_id=binding.owner_id,
            resource_type="approval_request",
            resource_id=approval.id,
            metadata={
                "decision": decision,
                "teams_identity_binding_id": binding.id,
                "approval_delivery_id": delivery.id,
                "teams_tenant_id": tenant_id,
            },
        )
        await self.db.commit()
        confirmation = "Rejected."
        if decision == "approved":
            workflow_run_id = str((approval.payload_json or {}).get("workflow_run_id") or "")
            workflow = await self.db.get(WorkflowRun, workflow_run_id) if workflow_run_id else None
            if workflow and workflow.status == "completed":
                confirmation = "Approved and completed."
                delivery.status = "completed"
            elif approval.status == "stale":
                confirmation = "Approval is stale. Open Troop to review."
                delivery.status = "stale"
            elif workflow and workflow.status == "failed":
                confirmation = "Approved, but execution failed. Open Troop for details."
                delivery.status = "failed"
            else:
                confirmation = "Approved; workflow resumed."
        await self.db.commit()
        await adapter.reply_activity(activity, confirmation)
        return {"status": decision}

    async def _authorized_context(
        self,
        *,
        approval_id: str,
        teams_user_id: str,
        tenant_id: str,
        conversation_id: str,
    ) -> tuple[ApprovalRequest, TeamsIdentityBinding, ApprovalDelivery]:
        result = await self.db.execute(
            select(ApprovalRequest, ApprovalDelivery, TeamsIdentityBinding)
            .join(
                ApprovalDelivery,
                ApprovalDelivery.approval_request_id == ApprovalRequest.id,
            )
            .join(
                TeamsIdentityBinding,
                TeamsIdentityBinding.connector_installation_id
                == ApprovalDelivery.connector_installation_id,
            )
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == "pending",
                ApprovalDelivery.channel == "teams",
                TeamsIdentityBinding.teams_user_id == teams_user_id,
                TeamsIdentityBinding.status == "active",
                TeamsIdentityBinding.owner_id == ApprovalDelivery.owner_id,
                TeamsIdentityBinding.conversation_id == ApprovalDelivery.destination_id,
            )
        )
        row = result.first()
        if row is None:
            raise ValueError("Unauthorized or unavailable approval")
        approval, delivery, binding = row
        if tenant_id and binding.teams_tenant_id and tenant_id != binding.teams_tenant_id:
            raise ValueError("Teams tenant mismatch")
        installation = await self.db.get(ConnectorInstallation, binding.connector_installation_id)
        if installation is not None:
            install_tenant = str((installation.config_json or {}).get("tenant_id") or "")
            if tenant_id and install_tenant and tenant_id != install_tenant:
                raise ValueError("Activity tenant does not match connector installation")
        if conversation_id and binding.conversation_id and conversation_id != binding.conversation_id:
            raise ValueError("Teams conversation does not match linked identity")
        expected_owner = str(
            (approval.payload_json or {}).get("owner_id") or approval.requested_by_user_id or ""
        )
        if expected_owner != binding.owner_id:
            raise ValueError("Teams identity is not authorized for this approval")
        return approval, binding, delivery

    async def _installation_for_tenant(self, tenant_id: str) -> ConnectorInstallation | None:
        if not tenant_id:
            return None
        result = await self.db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorDefinition.slug == "teams",
                ConnectorInstallation.status == "active",
            )
        )
        for installation, _definition in result.all():
            if str((installation.config_json or {}).get("tenant_id") or "") == tenant_id:
                return installation
        return None
