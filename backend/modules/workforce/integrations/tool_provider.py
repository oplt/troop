"""ToolRegistry provider for native connector operations."""

from __future__ import annotations

from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.integrations.email import (
    email_action_arguments_hash,
    outlook_email_action_arguments_hash,
    outlook_thread_fingerprint,
    thread_fingerprint,
)
from backend.modules.workforce.integrations.gmail import GmailAdapter, GmailAPIError
from backend.modules.workforce.integrations.google_calendar import (
    GoogleCalendarAdapter,
    GoogleCalendarAPIError,
)
from backend.modules.workforce.integrations.google_drive import (
    GoogleDriveAdapter,
    GoogleDriveAPIError,
)
from backend.modules.workforce.integrations.hubspot import HubSpotAdapter, HubSpotAPIError
from backend.modules.workforce.integrations.jira import JiraAdapter, JiraAPIError
from backend.modules.workforce.integrations.linear import LinearAdapter, LinearAPIError
from backend.modules.workforce.integrations.microsoft_calendar import (
    MicrosoftCalendarAdapter,
    MicrosoftCalendarAPIError,
)
from backend.modules.workforce.integrations.microsoft_drive import (
    MicrosoftDriveAdapter,
    MicrosoftDriveAPIError,
)
from backend.modules.workforce.integrations.outlook import OutlookAdapter, OutlookAPIError
from backend.modules.workforce.integrations.salesforce import SalesforceAdapter, SalesforceAPIError
from backend.modules.workforce.integrations.slack import SlackAdapter, SlackAPIError
from backend.modules.workforce.integrations.teams import TeamsAdapter, TeamsAPIError
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
OUTLOOK_OPERATIONS = frozenset(
    {
        "outlook.search_messages",
        "outlook.get_message",
        "outlook.get_thread",
        "outlook.create_draft",
        "outlook.update_draft",
        "outlook.send_draft",
        "outlook.add_label",
    }
)
GOOGLE_CALENDAR_OPERATIONS = frozenset(
    {
        "google_calendar.list_events",
        "google_calendar.get_event",
        "google_calendar.get_availability",
        "google_calendar.create_event",
        "google_calendar.update_event",
        "google_calendar.cancel_event",
    }
)
MICROSOFT_CALENDAR_OPERATIONS = frozenset(
    {
        "microsoft_calendar.list_events",
        "microsoft_calendar.get_event",
        "microsoft_calendar.get_availability",
        "microsoft_calendar.create_event",
        "microsoft_calendar.update_event",
        "microsoft_calendar.cancel_event",
    }
)
GOOGLE_DRIVE_OPERATIONS = frozenset(
    {
        "google_drive.search_files",
        "google_drive.get_file_metadata",
        "google_drive.get_file_content",
    }
)
MICROSOFT_DRIVE_OPERATIONS = frozenset(
    {
        "microsoft_drive.search_files",
        "microsoft_drive.get_file_metadata",
        "microsoft_drive.get_file_content",
    }
)
JIRA_OPERATIONS = frozenset(
    {
        "jira.search_issues",
        "jira.get_issue",
        "jira.get_issue_comments",
        "jira.create_issue",
        "jira.update_issue",
        "jira.add_comment",
    }
)
LINEAR_OPERATIONS = frozenset(
    {
        "linear.search_issues",
        "linear.get_issue",
        "linear.get_issue_comments",
        "linear.create_issue",
        "linear.update_issue",
        "linear.add_comment",
    }
)
HUBSPOT_OPERATIONS = frozenset(
    {
        "hubspot.search_contacts",
        "hubspot.get_contact",
        "hubspot.search_companies",
        "hubspot.get_company",
        "hubspot.update_contact",
        "hubspot.create_note",
        "hubspot.send_email",
    }
)
SALESFORCE_OPERATIONS = frozenset(
    {
        "salesforce.search_contacts",
        "salesforce.get_contact",
        "salesforce.search_accounts",
        "salesforce.get_account",
        "salesforce.update_contact",
        "salesforce.create_task",
        "salesforce.send_email",
    }
)
TELEGRAM_OPERATIONS = frozenset(
    {
        "telegram.send_message",
        "telegram.edit_message",
        "telegram.answer_callback",
    }
)
SLACK_OPERATIONS = frozenset(
    {
        "slack.search_messages",
        "slack.get_thread",
        "slack.get_message",
        "slack.post_message",
        "slack.update_message",
    }
)
TEAMS_OPERATIONS = frozenset(
    {
        "teams.search_messages",
        "teams.get_thread",
        "teams.get_message",
        "teams.post_message",
        "teams.update_message",
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
            if item["slug"]
            in GMAIL_OPERATIONS
            | OUTLOOK_OPERATIONS
            | GOOGLE_CALENDAR_OPERATIONS
            | MICROSOFT_CALENDAR_OPERATIONS
            | GOOGLE_DRIVE_OPERATIONS
            | MICROSOFT_DRIVE_OPERATIONS
            | JIRA_OPERATIONS
            | LINEAR_OPERATIONS
            | HUBSPOT_OPERATIONS
            | SALESFORCE_OPERATIONS
            | TELEGRAM_OPERATIONS
            | SLACK_OPERATIONS
            | TEAMS_OPERATIONS
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
        if tool_slug in {
            "gmail.send_draft",
            "outlook.send_draft",
            "google_calendar.cancel_event",
            "microsoft_calendar.cancel_event",
            "jira.add_comment",
            "linear.add_comment",
            "hubspot.send_email",
            "salesforce.send_email",
            "slack.post_message",
            "teams.post_message",
        }:
            return "high"
        if tool_slug.endswith((".create_event", ".update_event", ".create_issue", ".update_issue")):
            return "medium"
        return "medium"

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
        if tool_slug in OUTLOOK_OPERATIONS:
            adapter = await OutlookAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except OutlookAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            if tool_slug == "outlook.create_draft":
                await self._record_outlook_draft(adapter, merged, output)
            elif tool_slug == "outlook.update_draft":
                await self._update_outlook_draft_fingerprint(adapter, merged)
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in GOOGLE_CALENDAR_OPERATIONS:
            adapter = await GoogleCalendarAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except GoogleCalendarAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in MICROSOFT_CALENDAR_OPERATIONS:
            adapter = await MicrosoftCalendarAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except MicrosoftCalendarAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in GOOGLE_DRIVE_OPERATIONS:
            adapter = await GoogleDriveAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except GoogleDriveAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in MICROSOFT_DRIVE_OPERATIONS:
            adapter = await MicrosoftDriveAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except MicrosoftDriveAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in JIRA_OPERATIONS:
            adapter = await JiraAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except JiraAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in LINEAR_OPERATIONS:
            adapter = await LinearAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except LinearAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in HUBSPOT_OPERATIONS:
            adapter = await HubSpotAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except HubSpotAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in SALESFORCE_OPERATIONS:
            adapter = await SalesforceAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except SalesforceAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                    "provider_status_code": exc.status_code,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in SLACK_OPERATIONS:
            adapter = await SlackAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except SlackAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug in TEAMS_OPERATIONS:
            adapter = await TeamsAdapter.for_owner(
                self.db,
                owner_id=str(context["owner_id"]),
                installation_id=installation_id,
            )
            try:
                output = await adapter.execute(tool_slug, merged)
            except TeamsAPIError as exc:
                return {
                    "status": "failed",
                    "error": str(exc),
                    "retryable": exc.retryable,
                }
            await self.db.commit()
            return {"status": "succeeded", "output": output}
        if tool_slug not in TELEGRAM_OPERATIONS:
            return {"status": "denied", "reason": "unsupported_connector_operation"}
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

    async def _record_outlook_draft(
        self,
        adapter: OutlookAdapter,
        arguments: dict[str, Any],
        result: dict[str, Any],
    ) -> None:
        draft_id = str(result.get("id") or "")
        thread_id = str(result.get("conversationId") or arguments.get("thread_id") or "")
        fingerprint = ""
        if thread_id:
            thread = await adapter.execute("outlook.get_thread", {"thread_id": thread_id})
            fingerprint = outlook_thread_fingerprint(thread)
        self.db.add(
            DraftExecutionMetadata(
                owner_id=adapter.installation.owner_id,
                company_id=adapter.installation.company_id,
                connector_installation_id=adapter.installation.id,
                workflow_run_id=arguments.get("workflow_run_id"),
                workflow_node_id=arguments.get("workflow_node_id"),
                provider_draft_id=draft_id,
                message_id=draft_id,
                thread_id=thread_id or None,
                thread_fingerprint=fingerprint,
                content_hash=outlook_email_action_arguments_hash(
                    {**arguments, "outlook_draft_id": draft_id}
                ),
                status="current",
                metadata_json={"provider": "outlook"},
            )
        )

    async def _update_outlook_draft_fingerprint(
        self, adapter: OutlookAdapter, arguments: dict[str, Any]
    ) -> None:
        result = await self.db.execute(
            select(DraftExecutionMetadata).where(
                DraftExecutionMetadata.owner_id == adapter.installation.owner_id,
                DraftExecutionMetadata.connector_installation_id == adapter.installation.id,
                DraftExecutionMetadata.provider_draft_id
                == str(arguments.get("outlook_draft_id") or ""),
            )
        )
        metadata = result.scalar_one_or_none()
        if metadata is None:
            return
        metadata.content_hash = outlook_email_action_arguments_hash(arguments)
        metadata.draft_version += 1
        metadata.status = "current"
