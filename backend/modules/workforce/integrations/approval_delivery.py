"""Reusable approval delivery service with channel adapters."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.workforce.integrations.telegram import TelegramAdapter
from backend.modules.workforce.models import (
    ApprovalDelivery,
    ConnectorInstallation,
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
        sender_label = (
            sender.get("email") if isinstance(sender, dict) else str(sender or "")
        )
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
