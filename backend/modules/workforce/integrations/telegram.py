"""Telegram Bot delivery, identity linking, and canonical approval interactions."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.audit.repository import AuditRepository
from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.services.approvals_domain import ApprovalsService
from backend.modules.workforce.models import (
    ApprovalDelivery,
    ApprovalInteraction,
    ConnectorDefinition,
    ConnectorInstallation,
    TelegramIdentityBinding,
    WorkflowRun,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config


def _utcnow() -> datetime:
    return datetime.now(UTC)


def hash_link_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def validate_telegram_webhook_secret(value: str | None) -> bool:
    configured = settings.TELEGRAM_WEBHOOK_SECRET
    return bool(configured and value and hmac.compare_digest(configured, value))


class TelegramAPIError(RuntimeError):
    pass


class TelegramAdapter:
    def __init__(self, installation: ConnectorInstallation) -> None:
        self.installation = installation
        config = resolve_installation_config(installation)
        self.bot_token = str(config.get("bot_token") or config.get("token") or "")
        if not self.bot_token:
            raise TelegramAPIError("Telegram bot token unavailable")

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        method_by_operation = {
            "telegram.send_message": "sendMessage",
            "telegram.edit_message": "editMessageText",
            "telegram.answer_callback": "answerCallbackQuery",
        }
        method = method_by_operation.get(operation)
        if not method:
            raise TelegramAPIError(f"Unsupported Telegram operation: {operation}")
        async with managed_http_client("telegram-api") as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/{method}",
                json=arguments,
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise TelegramAPIError(f"Telegram API request failed ({response.status_code})")
        body = response.json()
        if not body.get("ok"):
            raise TelegramAPIError(str(body.get("description") or "Telegram API request failed"))
        return dict(body.get("result") or {})

    async def configure_webhook(self) -> dict[str, Any]:
        base_url = settings.TELEGRAM_WEBHOOK_BASE_URL.rstrip("/")
        if not base_url or not settings.TELEGRAM_WEBHOOK_SECRET:
            raise TelegramAPIError("Telegram webhook URL/secret is not configured")
        if settings.is_production and not base_url.startswith("https://"):
            raise TelegramAPIError("Telegram webhook URL must use HTTPS in production")
        async with managed_http_client("telegram-api") as client:
            response = await client.post(
                f"https://api.telegram.org/bot{self.bot_token}/setWebhook",
                json={
                    "url": f"{base_url}/api/v1/workforce/webhooks/telegram",
                    "secret_token": settings.TELEGRAM_WEBHOOK_SECRET,
                    "allowed_updates": ["message", "callback_query"],
                    "drop_pending_updates": False,
                },
                headers=external_headers(),
            )
        body = response.json()
        if response.status_code >= 400 or not body.get("ok"):
            raise TelegramAPIError("Telegram webhook registration failed")
        return {"configured": True}


class TelegramIdentityService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def create_link(
        self, owner_id: str, installation_id: str, *, company_id: str | None = None
    ) -> tuple[TelegramIdentityBinding, str]:
        installation = await self.get_installation(owner_id, installation_id)
        token = secrets.token_urlsafe(24)
        row = TelegramIdentityBinding(
            owner_id=owner_id,
            company_id=company_id or installation.company_id,
            connector_installation_id=installation.id,
            link_token_hash=hash_link_token(token),
            status="pending",
            token_expires_at=_utcnow() + timedelta(minutes=settings.TELEGRAM_LINK_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        await self.db.refresh(row)
        return row, token

    async def consume_link(
        self,
        token: str,
        *,
        telegram_user_id: str,
        telegram_chat_id: str,
        telegram_username: str | None = None,
    ) -> TelegramIdentityBinding:
        result = await self.db.execute(
            select(TelegramIdentityBinding)
            .where(TelegramIdentityBinding.link_token_hash == hash_link_token(token))
            .with_for_update()
        )
        row = result.scalar_one_or_none()
        if row is None or row.status != "pending" or row.token_expires_at <= _utcnow():
            raise ValueError("Invalid or expired Telegram link token")
        existing = await self.db.execute(
            select(TelegramIdentityBinding).where(
                TelegramIdentityBinding.connector_installation_id == row.connector_installation_id,
                TelegramIdentityBinding.telegram_user_id == telegram_user_id,
                TelegramIdentityBinding.status == "active",
            )
        )
        if existing.scalar_one_or_none() is not None:
            raise ValueError("Telegram identity is already linked")
        row.telegram_user_id = telegram_user_id
        row.telegram_chat_id = telegram_chat_id
        row.telegram_username = telegram_username
        row.status = "active"
        row.linked_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.telegram.identity_linked",
            user_id=row.owner_id,
            resource_type="telegram_identity_binding",
            resource_id=row.id,
            metadata={"connector_installation_id": row.connector_installation_id},
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def revoke(self, owner_id: str, binding_id: str) -> None:
        result = await self.db.execute(
            select(TelegramIdentityBinding).where(
                TelegramIdentityBinding.id == binding_id,
                TelegramIdentityBinding.owner_id == owner_id,
            )
        )
        row = result.scalar_one_or_none()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram binding not found")
        row.status = "revoked"
        row.revoked_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.telegram.identity_revoked",
            user_id=row.owner_id,
            resource_type="telegram_identity_binding",
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
                ConnectorDefinition.slug == "telegram",
            )
        )
        row = result.first()
        if row is None:
            raise HTTPException(status.HTTP_404_NOT_FOUND, "Telegram installation not found")
        return row[0]


class TelegramWebhookService:
    """Processes verified updates. It never invokes Gmail send."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def handle(self, update: dict[str, Any]) -> dict[str, Any]:
        if update.get("callback_query"):
            return await self._callback(dict(update["callback_query"]))
        if update.get("message"):
            return await self._message(dict(update["message"]))
        return {"status": "ignored"}

    async def _message(self, message: dict[str, Any]) -> dict[str, Any]:
        sender = dict(message.get("from") or {})
        chat = dict(message.get("chat") or {})
        text = str(message.get("text") or "")
        if text.startswith("/start "):
            binding = await TelegramIdentityService(self.db).consume_link(
                text.split(maxsplit=1)[1].strip(),
                telegram_user_id=str(sender.get("id") or ""),
                telegram_chat_id=str(chat.get("id") or ""),
                telegram_username=sender.get("username"),
            )
            installation = await self.db.get(
                ConnectorInstallation, binding.connector_installation_id
            )
            if installation:
                await TelegramAdapter(installation).execute(
                    "telegram.send_message",
                    {"chat_id": binding.telegram_chat_id, "text": "✅ Telegram linked to Troop."},
                )
            return {"status": "linked"}
        return await self._handle_edit_message(
            telegram_user_id=str(sender.get("id") or ""),
            chat_id=str(chat.get("id") or ""),
            text=text,
        )

    async def _callback(self, callback: dict[str, Any]) -> dict[str, Any]:
        sender = dict(callback.get("from") or {})
        message = dict(callback.get("message") or {})
        telegram_user_id = str(sender.get("id") or "")
        callback_id = str(callback.get("id") or "")
        data = str(callback.get("data") or "")
        action, _, approval_id = data.partition(":")
        if action not in {"approve", "reject", "edit"} or not approval_id:
            return {"status": "ignored"}
        approval, binding, delivery = await self._authorized_context(
            approval_id=approval_id,
            telegram_user_id=telegram_user_id,
        )
        installation = await self.db.get(ConnectorInstallation, binding.connector_installation_id)
        if installation is None:
            raise ValueError("Telegram installation missing")
        adapter = TelegramAdapter(installation)
        if callback_id:
            await adapter.execute(
                "telegram.answer_callback",
                {"callback_query_id": callback_id, "text": "Processing…"},
            )
        if action == "edit":
            interaction_result = await self.db.execute(
                select(ApprovalInteraction).where(
                    ApprovalInteraction.approval_request_id == approval.id,
                    ApprovalInteraction.telegram_user_id == telegram_user_id,
                    ApprovalInteraction.mode == "replace_email_body",
                )
            )
            interaction = interaction_result.scalar_one_or_none()
            if interaction is None:
                interaction = ApprovalInteraction(
                    owner_id=binding.owner_id,
                    approval_request_id=approval.id,
                    approval_delivery_id=delivery.id,
                    telegram_user_id=telegram_user_id,
                    mode="replace_email_body",
                    expected_input="text",
                    expires_at=_utcnow() + timedelta(minutes=settings.TELEGRAM_EDIT_TTL_MINUTES),
                )
                self.db.add(interaction)
            else:
                interaction.status = "pending"
                interaction.consumed_at = None
                interaction.expires_at = _utcnow() + timedelta(
                    minutes=settings.TELEGRAM_EDIT_TTL_MINUTES
                )
            await self.db.commit()
            await adapter.execute(
                "telegram.send_message",
                {
                    "chat_id": binding.telegram_chat_id,
                    "text": "Send the complete revised reply text. It will require approval again.",
                },
            )
            return {"status": "waiting_edit"}
        user = await self.db.get(User, binding.owner_id)
        if user is None:
            raise ValueError("Linked Troop user missing")
        decision = "approved" if action == "approve" else "rejected"
        reason = None if decision == "approved" else "Rejected from Telegram"
        await ApprovalsService(self.db).decide_approval(user, approval.id, decision, reason)
        delivery.status = decision
        delivery.responded_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.telegram.approval_decided",
            user_id=binding.owner_id,
            resource_type="approval_request",
            resource_id=approval.id,
            metadata={
                "decision": decision,
                "telegram_identity_binding_id": binding.id,
                "approval_delivery_id": delivery.id,
            },
        )
        await self.db.commit()
        confirmation_text = "❌ Rejected."
        if decision == "approved":
            workflow_run_id = str((approval.payload_json or {}).get("workflow_run_id") or "")
            workflow = await self.db.get(WorkflowRun, workflow_run_id) if workflow_run_id else None
            if workflow and workflow.status == "completed":
                confirmation_text = "✅ Approved and sent."
                delivery.status = "completed"
            elif approval.status == "stale":
                confirmation_text = (
                    "⚠️ Not sent: the Gmail thread changed after drafting. Redraft required."
                )
                delivery.status = "stale"
            elif workflow and workflow.status == "failed":
                confirmation_text = "⚠️ Approved, but sending failed. Open Troop for details."
                delivery.status = "failed"
            else:
                confirmation_text = "✅ Approved; workflow resumed."
        await self.db.commit()
        chat_id = str((message.get("chat") or {}).get("id") or binding.telegram_chat_id)
        message_id = message.get("message_id") or delivery.external_message_id
        if message_id:
            await adapter.execute(
                "telegram.edit_message",
                {
                    "chat_id": chat_id,
                    "message_id": message_id,
                    "text": confirmation_text,
                },
            )
        return {"status": decision}

    async def _authorized_context(
        self, *, approval_id: str, telegram_user_id: str
    ) -> tuple[ApprovalRequest, TelegramIdentityBinding, ApprovalDelivery]:
        result = await self.db.execute(
            select(ApprovalRequest, ApprovalDelivery, TelegramIdentityBinding)
            .join(
                ApprovalDelivery,
                ApprovalDelivery.approval_request_id == ApprovalRequest.id,
            )
            .join(
                TelegramIdentityBinding,
                TelegramIdentityBinding.connector_installation_id
                == ApprovalDelivery.connector_installation_id,
            )
            .where(
                ApprovalRequest.id == approval_id,
                ApprovalRequest.status == "pending",
                ApprovalDelivery.channel == "telegram",
                TelegramIdentityBinding.telegram_user_id == telegram_user_id,
                TelegramIdentityBinding.status == "active",
                TelegramIdentityBinding.owner_id == ApprovalDelivery.owner_id,
                ApprovalDelivery.destination_id == TelegramIdentityBinding.telegram_chat_id,
            )
        )
        row = result.first()
        if row is None:
            raise ValueError("Unauthorized or unavailable approval")
        approval, delivery, binding = row
        expected_owner = str(
            (approval.payload_json or {}).get("owner_id") or approval.requested_by_user_id or ""
        )
        if expected_owner != binding.owner_id:
            raise ValueError("Telegram identity is not authorized for this approval")
        return approval, binding, delivery

    async def _handle_edit_message(
        self, *, telegram_user_id: str, chat_id: str, text: str
    ) -> dict[str, Any]:
        result = await self.db.execute(
            select(ApprovalInteraction)
            .where(
                ApprovalInteraction.telegram_user_id == telegram_user_id,
                ApprovalInteraction.status == "pending",
                ApprovalInteraction.expires_at > _utcnow(),
            )
            .order_by(ApprovalInteraction.created_at.desc())
            .limit(1)
        )
        interaction = result.scalar_one_or_none()
        if interaction is None:
            return {"status": "ignored"}
        _approval, binding, _delivery = await self._authorized_context(
            approval_id=interaction.approval_request_id,
            telegram_user_id=telegram_user_id,
        )
        from backend.modules.workforce.integrations.approval_edit import (
            replace_email_approval_draft,
        )

        replacement = await replace_email_approval_draft(
            self.db,
            owner_id=binding.owner_id,
            approval_id=interaction.approval_request_id,
            changes={"body_text": text},
        )
        interaction.status = "consumed"
        interaction.consumed_at = _utcnow()
        await self.db.commit()
        return {"status": "edited", "approval_request_id": replacement.id}
