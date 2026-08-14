"""Reusable approval delivery service with channel adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.workforce.integrations.slack import SlackAdapter
from backend.modules.workforce.integrations.teams import TeamsAdapter
from backend.modules.workforce.integrations.telegram import TelegramAdapter
from backend.modules.workforce.models import (
    ApprovalDelivery,
    ConnectorInstallation,
    SlackIdentityBinding,
    TeamsIdentityBinding,
    TelegramIdentityBinding,
)


class ApprovalDeliveryAdapter(Protocol):
    async def deliver(self, *, destination_id: str, payload: dict[str, Any]) -> dict[str, Any]: ...


class TelegramApprovalDeliveryAdapter:
    def __init__(self, installation: ConnectorInstallation) -> None:
        self.adapter = TelegramAdapter(installation)

    async def deliver(self, *, destination_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(payload["approval_request_id"])
        draft = dict(payload.get("draft_arguments") or {})
        incoming = dict(payload.get("email") or {})
        sender = incoming.get("from") or {}
        sender_label = sender.get("email") if isinstance(sender, dict) else str(sender or "")
        recipients = ", ".join(
            str(item.get("email") if isinstance(item, dict) else item)
            for item in draft.get("to") or []
        )
        safe_text = (
            "📩 Email reply awaiting approval\n\n"
            f"From: {sender_label or 'Unknown sender'}\n"
            f"To: {recipients or 'Not specified'}\n"
            f"Subject: {draft.get('subject', '')}\n\n"
            f"Draft:\n{draft.get('body') or draft.get('body_text') or ''}\n\n"
            f"Risk: {payload.get('risk_level', 'high')}"
        )
        return await self.adapter.execute(
            "telegram.send_message",
            {
                "chat_id": destination_id,
                "text": safe_text[:3900],
                "reply_markup": {
                    "inline_keyboard": [
                        [
                            {
                                "text": "✅ Approve & Send",
                                "callback_data": f"approve:{approval_id}",
                            },
                            {"text": "✏️ Edit", "callback_data": f"edit:{approval_id}"},
                            {"text": "❌ Reject", "callback_data": f"reject:{approval_id}"},
                        ],
                        [
                            {
                                "text": "🔗 Open in Troop",
                                "url": (
                                    f"{settings.FRONTEND_URL.rstrip('/')}/activity"
                                    f"?approval_id={approval_id}"
                                ),
                            }
                        ],
                    ]
                },
            },
        )


class SlackApprovalDeliveryAdapter:
    def __init__(self, installation: ConnectorInstallation, db: AsyncSession) -> None:
        self.adapter = SlackAdapter(db, installation)

    async def deliver(self, *, destination_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(payload["approval_request_id"])
        draft = dict(payload.get("draft_arguments") or {})
        incoming = dict(payload.get("email") or payload.get("slack") or {})
        subject = draft.get("subject") or incoming.get("subject") or "Approval required"
        body = draft.get("body") or draft.get("body_text") or incoming.get("text") or ""
        summary = (
            f"*Approval required*\n"
            f"*Subject:* {subject}\n\n"
            f"{body}\n\n"
            f"*Risk:* {payload.get('risk_level', 'high')}"
        )
        return await self.adapter.execute(
            "slack.post_message",
            {
                "channel": destination_id,
                "text": summary[:3000],
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": summary[:3000]},
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Approve"},
                                "style": "primary",
                                "action_id": "troop_approve",
                                "value": approval_id,
                            },
                            {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "Reject"},
                                "style": "danger",
                                "action_id": "troop_reject",
                                "value": approval_id,
                            },
                        ],
                    },
                ],
            },
        )


class TeamsApprovalDeliveryAdapter:
    def __init__(self, installation: ConnectorInstallation, db: AsyncSession) -> None:
        self.adapter = TeamsAdapter(db, installation)

    async def deliver(self, *, destination_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        approval_id = str(payload["approval_request_id"])
        draft = dict(payload.get("draft_arguments") or {})
        incoming = dict(payload.get("email") or payload.get("teams") or {})
        subject = draft.get("subject") or incoming.get("subject") or "Approval required"
        body = draft.get("body") or draft.get("body_text") or incoming.get("text") or ""
        summary = (
            f"<strong>Approval required</strong><br/>"
            f"<strong>Subject:</strong> {subject}<br/><br/>"
            f"{body}<br/><br/>"
            f"<strong>Risk:</strong> {payload.get('risk_level', 'high')}"
        )
        card = {
            "$schema": "http://adaptivecards.io/schemas/adaptive-card.json",
            "type": "AdaptiveCard",
            "version": "1.4",
            "body": [{"type": "TextBlock", "text": summary, "wrap": True}],
            "actions": [
                {
                    "type": "Action.Submit",
                    "title": "Approve",
                    "data": {"troop_action": "approve", "approval_id": approval_id},
                },
                {
                    "type": "Action.Submit",
                    "title": "Reject",
                    "data": {"troop_action": "reject", "approval_id": approval_id},
                },
            ],
        }
        return await self.adapter.execute(
            "teams.post_message",
            {
                "conversation_id": destination_id,
                "text": "Approval required",
                "attachments": [
                    {
                        "contentType": "application/vnd.microsoft.card.adaptive",
                        "content": card,
                    }
                ],
            },
        )


class ApprovalDeliveryService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def deliver_telegram(
        self,
        *,
        approval_request_id: str,
        connector_installation_id: str,
    ) -> ApprovalDelivery:
        approval = await self.db.get(ApprovalRequest, approval_request_id)
        installation = await self.db.get(ConnectorInstallation, connector_installation_id)
        if approval is None or installation is None:
            raise ValueError("Approval or Telegram connector installation not found")
        owner_id = str(
            (approval.payload_json or {}).get("owner_id") or approval.requested_by_user_id or ""
        )
        if not owner_id or installation.owner_id != owner_id:
            raise ValueError("Approval and Telegram connector tenant do not match")
        binding_result = await self.db.execute(
            select(TelegramIdentityBinding).where(
                TelegramIdentityBinding.owner_id == owner_id,
                TelegramIdentityBinding.connector_installation_id == connector_installation_id,
                TelegramIdentityBinding.status == "active",
            )
        )
        binding = binding_result.scalar_one_or_none()
        if binding is None or not binding.telegram_chat_id:
            raise ValueError("Active Telegram identity binding not found")
        existing_result = await self.db.execute(
            select(ApprovalDelivery).where(
                ApprovalDelivery.approval_request_id == approval.id,
                ApprovalDelivery.channel == "telegram",
                ApprovalDelivery.connector_installation_id == connector_installation_id,
                ApprovalDelivery.destination_id == binding.telegram_chat_id,
            )
        )
        delivery = existing_result.scalar_one_or_none()
        if delivery and delivery.status in {"delivered", "approved", "rejected"}:
            return delivery
        if delivery is None:
            delivery = ApprovalDelivery(
                owner_id=owner_id,
                company_id=binding.company_id,
                approval_request_id=approval.id,
                channel="telegram",
                connector_installation_id=connector_installation_id,
                destination_id=binding.telegram_chat_id,
                status="pending",
            )
            self.db.add(delivery)
            await self.db.flush()
        try:
            result = await TelegramApprovalDeliveryAdapter(installation).deliver(
                destination_id=binding.telegram_chat_id,
                payload={
                    **dict(approval.payload_json or {}),
                    "approval_request_id": approval.id,
                },
            )
        except Exception as exc:
            delivery.status = "failed"
            delivery.metadata_json = {"error_type": type(exc).__name__}
            await self.db.commit()
            raise
        delivery.status = "delivered"
        delivery.external_message_id = str(result.get("message_id") or "")
        delivery.delivered_at = datetime.now(UTC)
        delivery.metadata_json = {"provider": "telegram"}
        await self.db.commit()
        await self.db.refresh(delivery)
        return delivery

    async def deliver_slack(
        self,
        *,
        approval_request_id: str,
        connector_installation_id: str,
    ) -> ApprovalDelivery:
        approval = await self.db.get(ApprovalRequest, approval_request_id)
        installation = await self.db.get(ConnectorInstallation, connector_installation_id)
        if approval is None or installation is None:
            raise ValueError("Approval or Slack connector installation not found")
        owner_id = str(
            (approval.payload_json or {}).get("owner_id") or approval.requested_by_user_id or ""
        )
        if not owner_id or installation.owner_id != owner_id:
            raise ValueError("Approval and Slack connector tenant do not match")
        binding_result = await self.db.execute(
            select(SlackIdentityBinding).where(
                SlackIdentityBinding.owner_id == owner_id,
                SlackIdentityBinding.connector_installation_id == connector_installation_id,
                SlackIdentityBinding.status == "active",
            )
        )
        binding = binding_result.scalar_one_or_none()
        if binding is None or not binding.slack_channel_id:
            raise ValueError("Active Slack identity binding not found")
        destination_id = binding.slack_channel_id
        existing_result = await self.db.execute(
            select(ApprovalDelivery).where(
                ApprovalDelivery.approval_request_id == approval.id,
                ApprovalDelivery.channel == "slack",
                ApprovalDelivery.connector_installation_id == connector_installation_id,
                ApprovalDelivery.destination_id == destination_id,
            )
        )
        delivery = existing_result.scalar_one_or_none()
        if delivery and delivery.status in {"delivered", "approved", "rejected"}:
            return delivery
        if delivery is None:
            delivery = ApprovalDelivery(
                owner_id=owner_id,
                company_id=binding.company_id,
                approval_request_id=approval.id,
                channel="slack",
                connector_installation_id=connector_installation_id,
                destination_id=destination_id,
                status="pending",
            )
            self.db.add(delivery)
            await self.db.flush()
        try:
            result = await SlackApprovalDeliveryAdapter(installation, self.db).deliver(
                destination_id=destination_id,
                payload={
                    **dict(approval.payload_json or {}),
                    "approval_request_id": approval.id,
                },
            )
        except Exception as exc:
            delivery.status = "failed"
            delivery.metadata_json = {"error_type": type(exc).__name__}
            await self.db.commit()
            raise
        delivery.status = "delivered"
        delivery.external_message_id = str(result.get("ts") or result.get("message_id") or "")
        delivery.delivered_at = datetime.now(UTC)
        delivery.metadata_json = {"provider": "slack"}
        await self.db.commit()
        await self.db.refresh(delivery)
        return delivery

    async def deliver_teams(
        self,
        *,
        approval_request_id: str,
        connector_installation_id: str,
    ) -> ApprovalDelivery:
        approval = await self.db.get(ApprovalRequest, approval_request_id)
        installation = await self.db.get(ConnectorInstallation, connector_installation_id)
        if approval is None or installation is None:
            raise ValueError("Approval or Teams connector installation not found")
        owner_id = str(
            (approval.payload_json or {}).get("owner_id") or approval.requested_by_user_id or ""
        )
        if not owner_id or installation.owner_id != owner_id:
            raise ValueError("Approval and Teams connector tenant do not match")
        binding_result = await self.db.execute(
            select(TeamsIdentityBinding).where(
                TeamsIdentityBinding.owner_id == owner_id,
                TeamsIdentityBinding.connector_installation_id == connector_installation_id,
                TeamsIdentityBinding.status == "active",
            )
        )
        binding = binding_result.scalar_one_or_none()
        if binding is None or not binding.conversation_id:
            raise ValueError("Active Teams identity binding not found")
        destination_id = binding.conversation_id
        existing_result = await self.db.execute(
            select(ApprovalDelivery).where(
                ApprovalDelivery.approval_request_id == approval.id,
                ApprovalDelivery.channel == "teams",
                ApprovalDelivery.connector_installation_id == connector_installation_id,
                ApprovalDelivery.destination_id == destination_id,
            )
        )
        delivery = existing_result.scalar_one_or_none()
        if delivery and delivery.status in {"delivered", "approved", "rejected"}:
            return delivery
        if delivery is None:
            delivery = ApprovalDelivery(
                owner_id=owner_id,
                company_id=binding.company_id,
                approval_request_id=approval.id,
                channel="teams",
                connector_installation_id=connector_installation_id,
                destination_id=destination_id,
                status="pending",
            )
            self.db.add(delivery)
            await self.db.flush()
        try:
            result = await TeamsApprovalDeliveryAdapter(installation, self.db).deliver(
                destination_id=destination_id,
                payload={
                    **dict(approval.payload_json or {}),
                    "approval_request_id": approval.id,
                },
            )
        except Exception as exc:
            delivery.status = "failed"
            delivery.metadata_json = {"error_type": type(exc).__name__}
            await self.db.commit()
            raise
        delivery.status = "delivered"
        delivery.external_message_id = str(result.get("id") or "")
        delivery.delivered_at = datetime.now(UTC)
        delivery.metadata_json = {"provider": "teams", "teams_tenant_id": binding.teams_tenant_id}
        await self.db.commit()
        await self.db.refresh(delivery)
        return delivery
