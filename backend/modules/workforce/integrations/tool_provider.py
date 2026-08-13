"""ToolRegistry provider for native connector operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.integrations.email import (
    email_action_arguments_hash,
    thread_fingerprint,
)
from backend.modules.workforce.integrations.gmail import GmailAdapter, GmailAPIError
from backend.modules.workforce.integrations.telegram import TelegramAdapter, TelegramAPIError
from backend.modules.workforce.models import (
    ConnectorInstallation,
    DraftExecutionMetadata,
)

GMAIL_OPERATIONS = frozenset(
    {
        "gmail.search_messages",
        "gmail.get_message",
        "gmail.get_thread",
        "gmail.create_draft",
        "gmail.update_draft",
        "gmail.send_draft",
        "gmail.add_label",
    }
)
TELEGRAM_OPERATIONS = frozenset(
    {
        "telegram.send_message",
        "telegram.edit_message",
        "telegram.answer_callback",
    }
)


class NativeConnectorToolProvider:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def discover_tools(self) -> list[dict]:
        from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

        return [
            item
            for item in NATIVE_TOOL_CATALOG
            if item["slug"] in GMAIL_OPERATIONS | TELEGRAM_OPERATIONS
        ]

    async def get_schema(self, tool_slug: str) -> dict:
        for item in await self.discover_tools():
            if item["slug"] == tool_slug:
                return dict(item.get("schema_json") or {})
        return {}

    async def validate_permissions(self, tool_slug: str, context: dict) -> bool:
        owner_id = str(context.get("owner_id") or "")
        installation_id = str(context.get("connector_installation_id") or "")
        if not owner_id or not installation_id:
            return False
        result = await self.db.execute(
            select(ConnectorInstallation).where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
            )
        )
        installation = result.scalar_one_or_none()
        if installation is None:
            return False
        company_id = context.get("company_id")
        return not (
            company_id
            and installation.company_id
            and str(company_id) != str(installation.company_id)
        )

    async def estimate_risk(self, tool_slug: str) -> str:
        return "high" if tool_slug == "gmail.send_draft" else "medium"

    async def execute(self, tool_slug: str, params: dict, context: dict) -> dict:
        merged = {**params, **{k: v for k, v in context.items() if k not in params}}
        installation_id = str(merged.get("connector_installation_id") or "")
        if not await self.validate_permissions(tool_slug, merged):
            return {"status": "denied", "reason": "connector_installation_not_authorized"}
        if tool_slug in GMAIL_OPERATIONS:
            adapter = await GmailAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except GmailAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            if tool_slug == "gmail.create_draft":
                await self._record_draft(adapter, merged, output)
            elif tool_slug == "gmail.update_draft":
                await self._update_draft_fingerprint(adapter, merged)
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        installation = await self.db.get(ConnectorInstallation, installation_id)
        if installation is None:
            return {"status": "denied", "reason": "connector_installation_not_found"}
        try:
            output = await TelegramAdapter(installation).execute(tool_slug, params)
        except TelegramAPIError as exc:
            return {"status": "failed", "error": str(exc)}
        return {"status": "succeeded", "output": output}

    async def _record_draft(
        self,
        adapter: GmailAdapter,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        draft_id = str(result.get("id") or "")
        message = dict(result.get("message") or {})
        thread_id = str(message.get("threadId") or arguments.get("thread_id") or "")
        fingerprint = ""
        if thread_id:
            thread = await adapter.execute(
                "gmail.get_thread", {"thread_id": thread_id, "format": "minimal"}
            )
            fingerprint = thread_fingerprint(thread)
        self.db.add(
            DraftExecutionMetadata(
                owner_id=adapter.installation.owner_id,
                company_id=adapter.installation.company_id,
                connector_installation_id=adapter.installation.id,
                workflow_run_id=arguments.get("workflow_run_id"),
                workflow_node_id=arguments.get("workflow_node_id"),
                provider_draft_id=draft_id,
                message_id=str(message.get("id") or ""),
                thread_id=thread_id or None,
                thread_fingerprint=fingerprint,
                content_hash=email_action_arguments_hash({**arguments, "gmail_draft_id": draft_id}),
                status="current",
                metadata_json={"provider": "gmail"},
            )
        )

    async def _update_draft_fingerprint(
        self, adapter: GmailAdapter, arguments: dict[str, Any]
    ) -> None:
        result = await self.db.execute(
            select(DraftExecutionMetadata).where(
                DraftExecutionMetadata.owner_id == adapter.installation.owner_id,
                DraftExecutionMetadata.connector_installation_id == adapter.installation.id,
                DraftExecutionMetadata.provider_draft_id
                == str(arguments.get("gmail_draft_id") or ""),
            )
        )
        metadata = result.scalar_one_or_none()
        if metadata is None:
            return
        metadata.content_hash = email_action_arguments_hash(arguments)
        metadata.draft_version += 1
        metadata.status = "current"
