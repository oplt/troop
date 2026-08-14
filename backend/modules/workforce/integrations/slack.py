"""Slack OAuth, messaging, signed webhooks, and approval channel interactions."""

from __future__ import annotations

import hashlib
import hmac
import json
import secrets
import time
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode

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
    SlackIdentityBinding,
    WorkflowRun,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

SLACK_API_BASE = "https://slack.com/api"
SLACK_AUTHORIZE_URL = "https://slack.com/oauth/v2/authorize"
SLACK_BOT_SCOPES = (
    "channels:history",
    "channels:read",
    "groups:history",
    "im:history",
    "im:write",
    "mpim:history",
    "chat:write",
    "users:read",
)
SLACK_USER_SCOPES = ("search:read",)


class SlackAPIError(RuntimeError):
    def __init__(self, message: str, *, retryable: bool = False):
        super().__init__(message)
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def hash_link_token(token: str) -> str:
    return _hash_secret(token)


def slack_action_arguments_hash(arguments: dict[str, Any]) -> str:
    payload = {
        "channel": str(arguments.get("channel") or ""),
        "thread_ts": str(arguments.get("thread_ts") or ""),
        "text": str(arguments.get("text") or ""),
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True).encode()).hexdigest()


def validate_slack_request_signature(
    *,
    body: bytes,
    timestamp: str | None,
    signature: str | None,
    signing_secret: str | None = None,
) -> bool:
    secret = (signing_secret or settings.SLACK_SIGNING_SECRET or "").strip()
    if not secret or not timestamp or not signature:
        return False
    try:
        request_ts = int(timestamp)
    except ValueError:
        return False
    if abs(time.time() - request_ts) > 60 * 5:
        return False
    basestring = f"v0:{timestamp}:{body.decode()}"
    expected = (
        "v0="
        + hmac.new(secret.encode(), basestring.encode(), hashlib.sha256).hexdigest()
    )
    return hmac.compare_digest(expected, signature)


class SlackOAuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def begin(
        self,
        owner_id: str,
        *,
        company_id: str | None = None,
        redirect_after: str | None = None,
    ) -> dict[str, Any]:
        if not settings.SLACK_CLIENT_ID or not settings.SLACK_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "slack_not_configured", "detail": "Slack OAuth is not configured"},
            )
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="slack",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("slack"),
            requested_scopes_json=[*SLACK_BOT_SCOPES, *SLACK_USER_SCOPES],
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.SLACK_CLIENT_ID,
                "scope": ",".join(SLACK_BOT_SCOPES),
                "user_scope": ",".join(SLACK_USER_SCOPES),
                "redirect_uri": settings.SLACK_OAUTH_REDIRECT_URI,
                "state": state,
            }
        )
        return {
            "authorization_url": f"{SLACK_AUTHORIZE_URL}?{query}",
            "scopes": [*SLACK_BOT_SCOPES, *SLACK_USER_SCOPES],
        }

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "slack",
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
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired Slack OAuth state")
        async with managed_http_client("slack-oauth") as client:
            response = await client.post(
                f"{SLACK_API_BASE}/oauth.v2.access",
                data={
                    "client_id": settings.SLACK_CLIENT_ID,
                    "client_secret": settings.SLACK_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.SLACK_OAUTH_REDIRECT_URI,
                },
                headers=external_headers(),
            )
        body = response.json()
        if response.status_code >= 400 or not body.get("ok"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST,
                str(body.get("error") or "Slack OAuth exchange failed"),
            )
        team = dict(body.get("team") or {})
        authed_user = dict(body.get("authed_user") or {})
        bot_token = str(body.get("access_token") or "")
        user_token = str(authed_user.get("access_token") or "")
        if not bot_token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Slack OAuth response missing bot token")

        definition_result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "slack")
        )
        definition = definition_result.scalar_one_or_none()
        if definition is None:
            raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "Slack connector definition missing")

        existing_result = await self.db.execute(
            select(ConnectorInstallation).where(
                ConnectorInstallation.owner_id == oauth_state.owner_id,
                ConnectorInstallation.connector_definition_id == definition.id,
            )
        )
        installation = existing_result.scalar_one_or_none()
        team_id = str(team.get("id") or "")
        team_name = str(team.get("name") or "Slack workspace")
        public_config = {
            "team_id": team_id,
            "team_name": team_name,
            "bot_user_id": str(body.get("bot_user_id") or ""),
            "installer_user_id": str(authed_user.get("id") or ""),
            "granted_scopes": list(body.get("scope", "").split(",")),
            "granted_user_scopes": list(authed_user.get("scope", "").split(",")),
        }
        secrets_payload = {"bot_token": bot_token}
        if user_token:
            secrets_payload["user_token"] = user_token
        if installation is None:
            installation = ConnectorInstallation(
                owner_id=oauth_state.owner_id,
                company_id=oauth_state.company_id,
                connector_definition_id=definition.id,
                name=f"Slack · {team_name}",
                status="active",
                config_json=public_config,
                secrets_ref=encrypt_secret(json.dumps(secrets_payload)),
            )
            self.db.add(installation)
        else:
            installation.status = "active"
            installation.name = f"Slack · {team_name}"
            installation.config_json = public_config
            installation.secrets_ref = encrypt_secret(json.dumps(secrets_payload))
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.slack.oauth_connected",
            user_id=oauth_state.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
            metadata={"team_id": team_id},
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after


class SlackAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation
        config = resolve_installation_config(installation)
        self.bot_token = str(config.get("bot_token") or "")
        self.user_token = str(config.get("user_token") or "")
        if not self.bot_token:
            raise SlackAPIError("Slack bot token unavailable")

    @classmethod
    async def for_owner(
        cls,
        db: AsyncSession,
        *,
        owner_id: str,
        installation_id: str,
    ) -> SlackAdapter:
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
                ConnectorDefinition.slug == "slack",
            )
        )
        row = result.first()
        if row is None:
            raise SlackAPIError("Authorized Slack installation not found")
        return cls(db, row[0])

    async def _api(
        self,
        method: str,
        *,
        params: dict[str, Any] | None = None,
        json_payload: dict[str, Any] | None = None,
        token: str | None = None,
    ) -> dict[str, Any]:
        auth_token = token or self.bot_token
        async with managed_http_client("slack-api", base_url=SLACK_API_BASE) as client:
            if json_payload is not None:
                response = await client.post(
                    f"/{method}",
                    json=json_payload,
                    headers=external_headers({"Authorization": f"Bearer {auth_token}"}),
                )
            else:
                response = await client.get(
                    f"/{method}",
                    params=params or {},
                    headers=external_headers({"Authorization": f"Bearer {auth_token}"}),
                )
        body = response.json()
        if response.status_code >= 400 or not body.get("ok"):
            error = str(body.get("error") or "Slack API request failed")
            retryable = error in {"ratelimited", "service_unavailable", "internal_error"}
            raise SlackAPIError(error, retryable=retryable)
        return dict(body)

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "slack.search_messages":
            query = str(arguments.get("query") or "").strip()
            if self.user_token:
                return await self._api(
                    "search.messages",
                    params={"query": query, "count": int(arguments.get("limit") or 20)},
                    token=self.user_token,
                )
            channel = str(arguments.get("channel") or "")
            if not channel:
                raise SlackAPIError("search requires user OAuth scope or a channel to scan")
            history = await self._api(
                "conversations.history",
                params={"channel": channel, "limit": int(arguments.get("limit") or 50)},
            )
            messages = [
                item
                for item in history.get("messages") or []
                if not query or query.lower() in str(item.get("text") or "").lower()
            ]
            return {"messages": {"matches": messages}}
        if operation == "slack.get_thread":
            return await self._api(
                "conversations.replies",
                params={
                    "channel": str(arguments["channel"]),
                    "ts": str(arguments["thread_ts"]),
                    "limit": int(arguments.get("limit") or 50),
                },
            )
        if operation == "slack.get_message":
            channel = str(arguments["channel"])
            if arguments.get("message_ts"):
                replies = await self._api(
                    "conversations.replies",
                    params={
                        "channel": channel,
                        "ts": str(arguments["message_ts"]),
                        "limit": 1,
                        "inclusive": True,
                    },
                )
                messages = replies.get("messages") or []
                return {"message": messages[0] if messages else None}
            history = await self._api(
                "conversations.history",
                params={"channel": channel, "limit": 1, "latest": str(arguments.get("latest") or "")},
            )
            messages = history.get("messages") or []
            return {"message": messages[0] if messages else None}
        if operation == "slack.post_message":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.post_message_exactly_once(arguments)
            payload = {
                "channel": str(arguments["channel"]),
                "text": str(arguments.get("text") or ""),
            }
            if arguments.get("thread_ts"):
                payload["thread_ts"] = str(arguments["thread_ts"])
            if arguments.get("blocks"):
                payload["blocks"] = arguments["blocks"]
            return await self._api("chat.postMessage", json_payload=payload)
        if operation == "slack.update_message":
            return await self._api(
                "chat.update",
                json_payload={
                    "channel": str(arguments["channel"]),
                    "ts": str(arguments["message_ts"]),
                    "text": str(arguments.get("text") or ""),
                },
            )
        raise SlackAPIError(f"Unsupported Slack operation: {operation}")

    async def open_dm(self, slack_user_id: str) -> str:
        opened = await self._api(
            "conversations.open",
            json_payload={"users": slack_user_id},
        )
        channel = dict(opened.get("channel") or {})
        channel_id = str(channel.get("id") or "")
        if not channel_id:
            raise SlackAPIError("Failed to open Slack DM channel")
        return channel_id

    async def post_message_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        owner_id = self.installation.owner_id
        workflow_run_id = str(arguments.get("workflow_run_id") or "")
        approval_id = str(arguments.get("approval_request_id") or "")
        channel = str(arguments.get("channel") or "")
        if not all((workflow_run_id, approval_id, channel)):
            raise SlackAPIError(
                "slack.post_message requires workflow_run_id, approval_request_id, and channel"
            )
        thread_ts = str(arguments.get("thread_ts") or "root")
        args_hash = slack_action_arguments_hash(arguments)
        try:
            claim = await authorize_and_claim_execution(
                self.db,
                owner_id=owner_id,
                action_key="slack.post_message",
                raw_arguments=arguments,
                approval_id=approval_id,
                idempotency_key=build_idempotency_key(
                    workflow_run_id, approval_id, channel, thread_ts, "slack.post_message"
                ),
                arguments_hash=args_hash,
                connector_installation_id=self.installation.id,
                workflow_run_id=workflow_run_id,
                require_consumed=True,
            )
        except CommitAuthorizationError as exc:
            raise SlackAPIError(str(exc), retryable="Concurrent duplicate" in str(exc)) from exc
        existing = claim.execution
        if claim.replayed:
            return dict(existing.result_json or {})
        await mark_execution_sending(
            self.db,
            existing,
            owner_id=owner_id,
            audit_action="connector.slack.post_attempted",
            audit_metadata={
                "workflow_run_id": workflow_run_id,
                "approval_request_id": approval_id,
                "channel": channel,
                "arguments_hash": args_hash,
            },
        )
        payload = {
            "channel": channel,
            "text": str(arguments.get("text") or ""),
        }
        if arguments.get("thread_ts"):
            payload["thread_ts"] = str(arguments["thread_ts"])
        try:
            result = await self._api("chat.postMessage", json_payload=payload)
        except SlackAPIError as exc:
            await mark_execution_failed(self.db, existing, owner_id=owner_id, error=str(exc))
            raise
        await mark_execution_succeeded(
            self.db,
            existing,
            owner_id=owner_id,
            result=result,
            audit_action="connector.slack.post_succeeded",
        )
        await self.db.commit()
        return result


class SlackIdentityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_link(
        self, owner_id: str, installation_id: str, *, company_id: str | None = None
    ) -> tuple[SlackIdentityBinding, str]:
        installation = await self.get_installation(owner_id, installation_id)
        token = secrets.token_urlsafe(24)
        row = SlackIdentityBinding(
            owner_id=owner_id,
            company_id=company_id or installation.company_id,
            connector_installation_id=installation.id,
            slack_team_id=str((installation.config_json or {}).get("team_id") or ""),
            link_token_hash=hash_link_token(token),
            status="pending",
            token_expires_at=_utcnow() + timedelta(minutes=settings.SLACK_LINK_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row, token

    async def consume_link(
        self,
        token: str,
        *,
        slack_user_id: str,
        slack_channel_id: str,
        slack_username: str | None = None,
    ) -> SlackIdentityBinding:
        result = await self.db.execute(
            select(SlackIdentityBinding)
            .where(SlackIdentityBinding.link_token_hash == hash_link_token(token))
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None or row.status != "pending" or row.token_expires_at <= _utcnow():
            raise ValueError("Invalid or expired Slack link token")
        existing = await self.db.execute(
            select(SlackIdentityBinding).where(
                SlackIdentityBinding.connector_installation_id == row.connector_installation_id,
                SlackIdentityBinding.slack_user_id == slack_user_id,
                SlackIdentityBinding.status == "active",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Slack identity is already linked")
        row.slack_user_id = slack_user_id
        row.slack_channel_id = slack_channel_id
        row.slack_username = slack_username
        row.status = "active"
        row.linked_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.slack.identity_linked",
            user_id=row.owner_id,
            resource_type="slack_identity_binding",
            resource_id=row.id,
            metadata={"connector_installation_id": row.connector_installation_id},
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def revoke(self, owner_id: str, binding_id: str) -> None:
        result = await self.db.execute(
            select(SlackIdentityBinding).where(
                SlackIdentityBinding.id == binding_id,
                SlackIdentityBinding.owner_id == owner_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Slack binding not found")
        row.status = "revoked"
        row.revoked_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.slack.identity_revoked",
            user_id=row.owner_id,
            resource_type="slack_identity_binding",
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
                ConnectorDefinition.slug == "slack",
            )
        )
        row = result.first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Slack installation not found")
        return row[0]


class SlackWebhookService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def handle(self, payload: dict[str, Any]) -> dict[str, Any]:
        payload_type = str(payload.get("type") or "")
        if payload_type == "url_verification":
            return {"challenge": payload.get("challenge")}
        if payload_type == "block_actions":
            return await self._block_actions(payload)
        if payload_type == "event_callback":
            event = dict(payload.get("event") or {})
            return await self._event(event, team_id=str(payload.get("team_id") or ""))
        return {"status": "ignored"}

    async def _event(self, event: dict[str, Any], *, team_id: str) -> dict[str, Any]:
        if event.get("bot_id") or event.get("subtype") == "bot_message":
            return {"status": "ignored"}
        if event.get("type") != "message":
            return {"status": "ignored"}
        text = str(event.get("text") or "").strip()
        slack_user_id = str(event.get("user") or "")
        channel_id = str(event.get("channel") or "")
        if text.lower().startswith("link "):
            token = text.split(maxsplit=1)[1].strip()
            installation = await self._installation_for_team(team_id)
            if installation is None:
                raise ValueError("Slack workspace installation not found")
            binding = await SlackIdentityService(self.db).consume_link(
                token,
                slack_user_id=slack_user_id,
                slack_channel_id=channel_id,
            )
            adapter = SlackAdapter(self.db, installation)
            await adapter.execute(
                "slack.post_message",
                {"channel": channel_id, "text": "✅ Slack account linked to Troop."},
            )
            _ = binding
            return {"status": "linked"}
        return {"status": "ignored"}

    async def _block_actions(self, payload: dict[str, Any]) -> dict[str, Any]:
        user = dict(payload.get("user") or {})
        slack_user_id = str(user.get("id") or "")
        channel = dict(payload.get("channel") or {})
        channel_id = str(channel.get("id") or "")
        message = dict(payload.get("message") or {})
        actions = list(payload.get("actions") or [])
        if not actions:
            return {"status": "ignored"}
        action = dict(actions[0])
        action_id = str(action.get("action_id") or "")
        approval_id = str(action.get("value") or "")
        if action_id not in {"troop_approve", "troop_reject"} or not approval_id:
            return {"status": "ignored"}
        approval, binding, delivery = await self._authorized_context(
            approval_id=approval_id,
            slack_user_id=slack_user_id,
            channel_id=channel_id,
        )
        installation = await self.db.get(ConnectorInstallation, binding.connector_installation_id)
        if installation is None:
            raise ValueError("Slack installation missing")
        adapter = SlackAdapter(self.db, installation)
        troop_user = await self.db.get(User, binding.owner_id)
        if troop_user is None:
            raise ValueError("Linked Troop user missing")
        decision = "approved" if action_id == "troop_approve" else "rejected"
        reason = None if decision == "approved" else "Rejected from Slack"
        await ApprovalsService(self.db).decide_approval(troop_user, approval.id, decision, reason)
        delivery.status = decision
        delivery.responded_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.slack.approval_decided",
            user_id=binding.owner_id,
            resource_type="approval_request",
            resource_id=approval.id,
            metadata={
                "decision": decision,
                "slack_identity_binding_id": binding.id,
                "approval_delivery_id": delivery.id,
            },
        )
        await self.db.commit()
        confirmation_text = "❌ Rejected."
        if decision == "approved":
            workflow_run_id = str((approval.payload_json or {}).get("workflow_run_id") or "")
            workflow = await self.db.get(WorkflowRun, workflow_run_id) if workflow_run_id else None
            if workflow and workflow.status == "completed":
                confirmation_text = "✅ Approved and completed."
                delivery.status = "completed"
            elif approval.status == "stale":
                confirmation_text = "⚠️ Approval is stale. Open Troop to review."
                delivery.status = "stale"
            elif workflow and workflow.status == "failed":
                confirmation_text = "⚠️ Approved, but execution failed. Open Troop for details."
                delivery.status = "failed"
            else:
                confirmation_text = "✅ Approved; workflow resumed."
        await self.db.commit()
        message_ts = message.get("ts") or delivery.external_message_id
        if message_ts:
            await adapter.execute(
                "slack.update_message",
                {
                    "channel": channel_id,
                    "message_ts": str(message_ts),
                    "text": confirmation_text,
                },
            )
        return {"status": decision}

    async def _authorized_context(
        self,
        *,
        approval_id: str,
        slack_user_id: str,
        channel_id: str,
    ) -> tuple[ApprovalRequest, SlackIdentityBinding, ApprovalDelivery]:
        result = await self.db.execute(
            select(ApprovalRequest, ApprovalDelivery, SlackIdentityBinding)
            .join(
                ApprovalDelivery,
                ApprovalDelivery.approval_request_id == ApprovalRequest.id,
            )
            .join(
                SlackIdentityBinding,
                SlackIdentityBinding.connector_installation_id
                == ApprovalDelivery.connector_installation_id,
            )
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == "pending",
                ApprovalDelivery.channel == "slack",
                SlackIdentityBinding.slack_user_id == slack_user_id,
                SlackIdentityBinding.status == "active",
                SlackIdentityBinding.owner_id == ApprovalDelivery.owner_id,
                ApprovalDelivery.destination_id == SlackIdentityBinding.slack_channel_id,
            )
        )
        row = result.first()
        if row is None:
            raise ValueError("Unauthorized or unavailable approval")
        approval, delivery, binding = row
        if channel_id and binding.slack_channel_id and channel_id != binding.slack_channel_id:
            raise ValueError("Slack channel does not match linked identity")
        expected_owner = str(
            (approval.payload_json or {}).get("owner_id") or approval.requested_by_user_id or ""
        )
        if expected_owner != binding.owner_id:
            raise ValueError("Slack identity is not authorized for this approval")
        return approval, binding, delivery

    async def _installation_for_team(self, team_id: str) -> ConnectorInstallation | None:
        if not team_id:
            return None
        result = await self.db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorDefinition.slug == "slack",
                ConnectorInstallation.status == "active",
            )
        )
        for installation, _definition in result.all():
            if str((installation.config_json or {}).get("team_id") or "") == team_id:
                return installation
        return None
