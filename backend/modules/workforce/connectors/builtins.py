"""Reference connector manifests for built-in native providers."""

from __future__ import annotations

from typing import Any

from backend.modules.workforce.action_metadata import governance_for_action_key
from backend.modules.workforce.catalog import CONNECTOR_CATALOG
from backend.modules.workforce.connectors.manifest import (
    AuthStrategyType,
    ConnectorAuthManifest,
    ConnectorManifest,
    ConnectorOperationManifest,
    ConnectorScopeManifest,
    HealthProbeManifest,
    OperationKind,
    RateLimitManifest,
    ReauthorizationBehavior,
    WebhookManifest,
    WebhookVerificationStrategy,
)
from backend.modules.workforce.connectors.registry import ConnectorManifestRegistry
from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

_GMAIL_SCOPES: tuple[tuple[str, str, str], ...] = (
    (
        "https://www.googleapis.com/auth/gmail.readonly",
        "Read mail",
        "Search, read messages and threads",
    ),
    (
        "https://www.googleapis.com/auth/gmail.modify",
        "Modify mail",
        "Add or remove labels on messages",
    ),
    (
        "https://www.googleapis.com/auth/gmail.compose",
        "Compose mail",
        "Create and update drafts",
    ),
    (
        "https://www.googleapis.com/auth/gmail.send",
        "Send mail",
        "Send approved drafts",
    ),
)

_GMAIL_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_messages": ["https://www.googleapis.com/auth/gmail.readonly"],
    "get_message": ["https://www.googleapis.com/auth/gmail.readonly"],
    "get_thread": ["https://www.googleapis.com/auth/gmail.readonly"],
    "new_message": ["https://www.googleapis.com/auth/gmail.readonly"],
    "add_label": ["https://www.googleapis.com/auth/gmail.modify"],
    "create_draft": ["https://www.googleapis.com/auth/gmail.compose"],
    "update_draft": ["https://www.googleapis.com/auth/gmail.compose"],
    "send_draft": ["https://www.googleapis.com/auth/gmail.send"],
}

_SLACK_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("channels:history", "Channel history", "Read public channel messages"),
    ("channels:read", "Channel metadata", "List and inspect channels"),
    ("groups:history", "Private channel history", "Read private channel messages"),
    ("im:history", "Direct messages", "Read direct message history"),
    ("chat:write", "Post messages", "Send and update messages"),
    ("search:read", "Search", "Search workspace messages (user scope)"),
)

_SLACK_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_messages": ["search:read", "channels:history"],
    "get_thread": ["channels:history", "groups:history", "im:history"],
    "get_message": ["channels:history", "groups:history", "im:history"],
    "post_message": ["chat:write"],
    "update_message": ["chat:write"],
}

_TEAMS_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("Chat.Read", "Read chats", "Read chat messages and threads"),
    ("Chat.ReadWrite", "Read/write chats", "Read and write chat messages"),
    ("ChannelMessage.Read.All", "Read channel messages", "Read team channel messages"),
    ("ChannelMessage.Send", "Send channel messages", "Post to team channels"),
)

_TEAMS_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_messages": ["Chat.Read", "ChannelMessage.Read.All"],
    "get_thread": ["Chat.Read"],
    "get_message": ["Chat.Read"],
    "post_message": ["Chat.ReadWrite", "ChannelMessage.Send"],
    "update_message": ["Chat.ReadWrite"],
}


def _catalog_tool(slug: str) -> dict[str, Any] | None:
    for item in NATIVE_TOOL_CATALOG:
        if item["slug"] == slug:
            return item
    return None


def _operation_kind(slug: str, *, trigger: bool = False) -> OperationKind:
    if trigger:
        return OperationKind.TRIGGER
    operation_name = slug.split(".", 1)[-1]
    if operation_name.startswith("search"):
        return OperationKind.SEARCH
    if operation_name.startswith(("get", "answer")):
        return OperationKind.READ
    return OperationKind.ACTION


def _operation_from_catalog(
    slug: str,
    *,
    trigger: bool = False,
    scope_map: dict[str, list[str]] | None = None,
) -> ConnectorOperationManifest:
    tool = _catalog_tool(slug) or {}
    operation_name = slug.split(".", 1)[-1]
    governance = governance_for_action_key(slug)
    scopes = scope_map or _GMAIL_SCOPE_BY_OPERATION
    return ConnectorOperationManifest(
        slug=slug,
        name=str(tool.get("name") or slug),
        description=str(tool.get("description") or ""),
        operation_kind=_operation_kind(slug, trigger=trigger),
        input_schema=dict(tool.get("schema_json") or {}),
        output_schema={},
        risk_level=str(tool.get("risk_level") or "medium"),
        requires_approval=bool(tool.get("requires_approval")),
        required_scopes=list(scopes.get(operation_name, [])),
        governance=governance,
        parallel_safe=governance.parallel_safe,
    )


def _connector_catalog_entry(slug: str) -> dict[str, Any]:
    for item in CONNECTOR_CATALOG:
        if item["slug"] == slug:
            return item
    return {}


def build_gmail_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("gmail")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _GMAIL_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _GMAIL_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug)
        for slug in (
            "gmail.search_messages",
            "gmail.get_message",
            "gmail.get_thread",
            "gmail.create_draft",
            "gmail.update_draft",
            "gmail.send_draft",
            "gmail.add_label",
        )
    ]
    triggers = [
        ConnectorOperationManifest(
            slug="gmail.new_message",
            name="Gmail New Message",
            description="Trigger a workflow from Gmail push/history events",
            operation_kind=OperationKind.TRIGGER,
            input_schema={
                "type": "object",
                "properties": {
                    "label_ids": {"type": "array", "items": {"type": "string"}},
                    "history_types": {"type": "array", "items": {"type": "string"}},
                },
            },
            output_schema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "message_id": {"type": "string"},
                    "history_id": {"type": "string"},
                },
            },
            risk_level="low",
            requires_approval=False,
            required_scopes=["https://www.googleapis.com/auth/gmail.readonly"],
            governance=governance_for_action_key("gmail.get_message"),
            parallel_safe=False,
        )
    ]
    return ConnectorManifest(
        provider_slug="gmail",
        version=version,
        name=str(catalog.get("name") or "Gmail"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
            pkce_required=True,
        ),
        triggers=triggers,
        actions=actions,
        webhook=WebhookManifest(
            strategy=WebhookVerificationStrategy.OIDC_JWT,
            verification_header="Authorization",
            dedupe_key_fields=["history_id", "message_id"],
            supports_registration=True,
        ),
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=250, burst=50, scope="installation"),
        metadata={"health_probe": "GET /users/me/profile"},
    )


_OUTLOOK_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("Mail.Read", "Read mail", "Read mailbox messages and threads"),
    ("Mail.ReadWrite", "Read and write mail", "Modify categories and draft content"),
    ("Mail.Send", "Send mail", "Send approved drafts"),
)

_OUTLOOK_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_messages": ["Mail.Read"],
    "get_message": ["Mail.Read"],
    "get_thread": ["Mail.Read"],
    "new_message": ["Mail.Read"],
    "add_label": ["Mail.ReadWrite"],
    "create_draft": ["Mail.ReadWrite"],
    "update_draft": ["Mail.ReadWrite"],
    "send_draft": ["Mail.Send"],
}


def build_outlook_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("outlook")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _OUTLOOK_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _OUTLOOK_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_OUTLOOK_SCOPE_BY_OPERATION)
        for slug in (
            "outlook.search_messages",
            "outlook.get_message",
            "outlook.get_thread",
            "outlook.create_draft",
            "outlook.update_draft",
            "outlook.send_draft",
            "outlook.add_label",
        )
    ]
    triggers = [
        ConnectorOperationManifest(
            slug="outlook.new_message",
            name="Outlook New Message",
            description="Trigger a workflow from Outlook inbox change notifications",
            operation_kind=OperationKind.TRIGGER,
            input_schema={"type": "object", "properties": {}},
            output_schema={
                "type": "object",
                "properties": {
                    "thread_id": {"type": "string"},
                    "message_id": {"type": "string"},
                },
            },
            risk_level="low",
            requires_approval=False,
            required_scopes=["Mail.Read"],
            governance=governance_for_action_key("outlook.get_message"),
            parallel_safe=False,
        )
    ]
    return ConnectorManifest(
        provider_slug="outlook",
        version=version,
        name=str(catalog.get("name") or "Outlook Mail"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=triggers,
        actions=actions,
        webhook=WebhookManifest(
            strategy=WebhookVerificationStrategy.CLIENT_STATE,
            verification_header="clientState",
            dedupe_key_fields=["resource", "changeType"],
            supports_registration=True,
        ),
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=250, burst=50, scope="installation"),
        metadata={"health_probe": "GET /me"},
    )


def build_telegram_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("telegram")
    actions = [
        _operation_from_catalog(slug)
        for slug in (
            "telegram.send_message",
            "telegram.edit_message",
            "telegram.answer_callback",
        )
    ]
    return ConnectorManifest(
        provider_slug="telegram",
        version=version,
        name=str(catalog.get("name") or "Telegram Bot"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.BOT_TOKEN,
            scopes=[],
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.REVOKE_AND_RECONNECT,
        ),
        triggers=[],
        actions=actions,
        webhook=WebhookManifest(
            strategy=WebhookVerificationStrategy.HMAC_SECRET,
            verification_header="X-Telegram-Bot-Api-Secret-Token",
            dedupe_key_fields=["update_id"],
            supports_registration=True,
        ),
        health=HealthProbeManifest(operation_slug="telegram.send_message", timeout_seconds=10),
        rate_limits=RateLimitManifest(requests_per_minute=30, burst=10, scope="provider"),
        metadata={"health_probe": "GET /bot<token>/getMe"},
    )


def build_slack_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("slack")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _SLACK_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _SLACK_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_SLACK_SCOPE_BY_OPERATION)
        for slug in (
            "slack.search_messages",
            "slack.get_thread",
            "slack.get_message",
            "slack.post_message",
            "slack.update_message",
        )
    ]
    return ConnectorManifest(
        provider_slug="slack",
        version=version,
        name=str(catalog.get("name") or "Slack"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.REVOKE_AND_RECONNECT,
        ),
        triggers=[],
        actions=actions,
        webhook=WebhookManifest(
            strategy=WebhookVerificationStrategy.PROVIDER_SIGNATURE,
            verification_header="X-Slack-Signature",
            dedupe_key_fields=["event_id"],
            supports_registration=False,
        ),
        health=HealthProbeManifest(operation_slug=None, timeout_seconds=10),
        rate_limits=RateLimitManifest(requests_per_minute=60, burst=20, scope="installation"),
        metadata={"health_probe": "POST /auth.test"},
    )


def build_teams_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("teams")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _TEAMS_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _TEAMS_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_TEAMS_SCOPE_BY_OPERATION)
        for slug in (
            "teams.search_messages",
            "teams.get_thread",
            "teams.get_message",
            "teams.post_message",
            "teams.update_message",
        )
    ]
    return ConnectorManifest(
        provider_slug="teams",
        version=version,
        name=str(catalog.get("name") or "Microsoft Teams"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        webhook=WebhookManifest(
            strategy=WebhookVerificationStrategy.OIDC_JWT,
            verification_header="Authorization",
            dedupe_key_fields=["id"],
            supports_registration=False,
        ),
        health=HealthProbeManifest(operation_slug=None, timeout_seconds=10),
        rate_limits=RateLimitManifest(requests_per_minute=60, burst=20, scope="installation"),
        metadata={"health_probe": "GET /me", "messaging_endpoint": "/webhooks/teams"},
    )


_GOOGLE_CALENDAR_SCOPES: tuple[tuple[str, str, str], ...] = (
    (
        "https://www.googleapis.com/auth/calendar.readonly",
        "Read calendar",
        "Read events and availability",
    ),
    (
        "https://www.googleapis.com/auth/calendar.events",
        "Manage events",
        "Create, update, and cancel events",
    ),
)

_GOOGLE_CALENDAR_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "list_events": ["https://www.googleapis.com/auth/calendar.readonly"],
    "get_event": ["https://www.googleapis.com/auth/calendar.readonly"],
    "get_availability": ["https://www.googleapis.com/auth/calendar.readonly"],
    "create_event": ["https://www.googleapis.com/auth/calendar.events"],
    "update_event": ["https://www.googleapis.com/auth/calendar.events"],
    "cancel_event": ["https://www.googleapis.com/auth/calendar.events"],
}

_MICROSOFT_CALENDAR_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("Calendars.Read", "Read calendar", "Read events and availability"),
    ("Calendars.ReadWrite", "Manage events", "Create, update, and cancel events"),
)

_MICROSOFT_CALENDAR_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "list_events": ["Calendars.Read"],
    "get_event": ["Calendars.Read"],
    "get_availability": ["Calendars.Read"],
    "create_event": ["Calendars.ReadWrite"],
    "update_event": ["Calendars.ReadWrite"],
    "cancel_event": ["Calendars.ReadWrite"],
}


def build_google_calendar_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("google_calendar")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op
                for op, required in _GOOGLE_CALENDAR_SCOPE_BY_OPERATION.items()
                if scope in required
            ],
        )
        for scope, label, description in _GOOGLE_CALENDAR_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_GOOGLE_CALENDAR_SCOPE_BY_OPERATION)
        for slug in (
            "google_calendar.list_events",
            "google_calendar.get_event",
            "google_calendar.get_availability",
            "google_calendar.create_event",
            "google_calendar.update_event",
            "google_calendar.cancel_event",
        )
    ]
    return ConnectorManifest(
        provider_slug="google_calendar",
        version=version,
        name=str(catalog.get("name") or "Google Calendar"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
            pkce_required=True,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /users/me/calendarList"},
    )


def build_microsoft_calendar_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("microsoft_calendar")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op
                for op, required in _MICROSOFT_CALENDAR_SCOPE_BY_OPERATION.items()
                if scope in required
            ],
        )
        for scope, label, description in _MICROSOFT_CALENDAR_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_MICROSOFT_CALENDAR_SCOPE_BY_OPERATION)
        for slug in (
            "microsoft_calendar.list_events",
            "microsoft_calendar.get_event",
            "microsoft_calendar.get_availability",
            "microsoft_calendar.create_event",
            "microsoft_calendar.update_event",
            "microsoft_calendar.cancel_event",
        )
    ]
    return ConnectorManifest(
        provider_slug="microsoft_calendar",
        version=version,
        name=str(catalog.get("name") or "Microsoft Calendar"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /me/calendar"},
    )


_GOOGLE_DRIVE_SCOPES: tuple[tuple[str, str, str], ...] = (
    (
        "https://www.googleapis.com/auth/drive.readonly",
        "Read Drive",
        "Search and read files for RAG sync",
    ),
)

_GOOGLE_DRIVE_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_files": ["https://www.googleapis.com/auth/drive.readonly"],
    "get_file_metadata": ["https://www.googleapis.com/auth/drive.readonly"],
    "get_file_content": ["https://www.googleapis.com/auth/drive.readonly"],
}

_MICROSOFT_DRIVE_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("Files.Read.All", "Read files", "Search and read OneDrive/SharePoint files"),
    ("Sites.Read.All", "Read sites", "Read SharePoint site libraries"),
)

_MICROSOFT_DRIVE_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_files": ["Files.Read.All", "Sites.Read.All"],
    "get_file_metadata": ["Files.Read.All", "Sites.Read.All"],
    "get_file_content": ["Files.Read.All", "Sites.Read.All"],
}


def build_google_drive_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("google_drive")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _GOOGLE_DRIVE_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _GOOGLE_DRIVE_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_GOOGLE_DRIVE_SCOPE_BY_OPERATION)
        for slug in (
            "google_drive.search_files",
            "google_drive.get_file_metadata",
            "google_drive.get_file_content",
        )
    ]
    return ConnectorManifest(
        provider_slug="google_drive",
        version=version,
        name=str(catalog.get("name") or "Google Drive"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
            pkce_required=True,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /about"},
    )


def build_microsoft_drive_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("microsoft_drive")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op
                for op, required in _MICROSOFT_DRIVE_SCOPE_BY_OPERATION.items()
                if scope in required
            ],
        )
        for scope, label, description in _MICROSOFT_DRIVE_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_MICROSOFT_DRIVE_SCOPE_BY_OPERATION)
        for slug in (
            "microsoft_drive.search_files",
            "microsoft_drive.get_file_metadata",
            "microsoft_drive.get_file_content",
        )
    ]
    return ConnectorManifest(
        provider_slug="microsoft_drive",
        version=version,
        name=str(catalog.get("name") or "Microsoft Drive"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /me/drive"},
    )


_JIRA_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("read:jira-work", "Read issues", "Search and read Jira issues"),
    ("write:jira-work", "Write issues", "Create, update, and comment on issues"),
)

_JIRA_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_issues": ["read:jira-work"],
    "get_issue": ["read:jira-work"],
    "get_issue_comments": ["read:jira-work"],
    "create_issue": ["write:jira-work"],
    "update_issue": ["write:jira-work"],
    "add_comment": ["write:jira-work"],
}

_LINEAR_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("read", "Read issues", "Search and read Linear issues"),
    ("write", "Write issues", "Update Linear issues"),
    ("issues:create", "Create issues", "Create Linear issues"),
    ("comments:create", "Create comments", "Comment on Linear issues"),
)

_LINEAR_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_issues": ["read"],
    "get_issue": ["read"],
    "get_issue_comments": ["read"],
    "create_issue": ["issues:create", "write"],
    "update_issue": ["write"],
    "add_comment": ["comments:create", "write"],
}


def build_jira_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("jira")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _JIRA_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _JIRA_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_JIRA_SCOPE_BY_OPERATION)
        for slug in (
            "jira.search_issues",
            "jira.get_issue",
            "jira.get_issue_comments",
            "jira.create_issue",
            "jira.update_issue",
            "jira.add_comment",
        )
    ]
    return ConnectorManifest(
        provider_slug="jira",
        version=version,
        name=str(catalog.get("name") or "Jira"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /myself"},
    )


def build_linear_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("linear")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _LINEAR_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _LINEAR_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_LINEAR_SCOPE_BY_OPERATION)
        for slug in (
            "linear.search_issues",
            "linear.get_issue",
            "linear.get_issue_comments",
            "linear.create_issue",
            "linear.update_issue",
            "linear.add_comment",
        )
    ]
    return ConnectorManifest(
        provider_slug="linear",
        version=version,
        name=str(catalog.get("name") or "Linear"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GraphQL viewer"},
    )


_HUBSPOT_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("crm.objects.contacts.read", "Read contacts", "Search and read contacts"),
    ("crm.objects.contacts.write", "Write contacts", "Update contacts and notes"),
    ("crm.objects.companies.read", "Read companies", "Search and read companies"),
)

_HUBSPOT_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_contacts": ["crm.objects.contacts.read"],
    "get_contact": ["crm.objects.contacts.read"],
    "search_companies": ["crm.objects.companies.read"],
    "get_company": ["crm.objects.companies.read"],
    "update_contact": ["crm.objects.contacts.write"],
    "create_note": ["crm.objects.contacts.write"],
    "send_email": ["crm.objects.contacts.write"],
}

_SALESFORCE_SCOPES: tuple[tuple[str, str, str], ...] = (
    ("api", "API access", "Read and write Salesforce records"),
)

_SALESFORCE_SCOPE_BY_OPERATION: dict[str, list[str]] = {
    "search_contacts": ["api"],
    "get_contact": ["api"],
    "search_accounts": ["api"],
    "get_account": ["api"],
    "update_contact": ["api"],
    "create_task": ["api"],
    "send_email": ["api"],
}


def build_hubspot_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("hubspot")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _HUBSPOT_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _HUBSPOT_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_HUBSPOT_SCOPE_BY_OPERATION)
        for slug in (
            "hubspot.search_contacts",
            "hubspot.get_contact",
            "hubspot.search_companies",
            "hubspot.get_company",
            "hubspot.update_contact",
            "hubspot.create_note",
            "hubspot.send_email",
        )
    ]
    return ConnectorManifest(
        provider_slug="hubspot",
        version=version,
        name=str(catalog.get("name") or "HubSpot"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /crm/v3/objects/contacts"},
    )


def build_salesforce_manifest(*, version: str = "1.0.0") -> ConnectorManifest:
    catalog = _connector_catalog_entry("salesforce")
    scopes = [
        ConnectorScopeManifest(
            scope=scope,
            label=label,
            description=description,
            required_for=[
                op for op, required in _SALESFORCE_SCOPE_BY_OPERATION.items() if scope in required
            ],
        )
        for scope, label, description in _SALESFORCE_SCOPES
    ]
    actions = [
        _operation_from_catalog(slug, scope_map=_SALESFORCE_SCOPE_BY_OPERATION)
        for slug in (
            "salesforce.search_contacts",
            "salesforce.get_contact",
            "salesforce.search_accounts",
            "salesforce.get_account",
            "salesforce.update_contact",
            "salesforce.create_task",
            "salesforce.send_email",
        )
    ]
    return ConnectorManifest(
        provider_slug="salesforce",
        version=version,
        name=str(catalog.get("name") or "Salesforce"),
        description=str(catalog.get("description") or ""),
        provider_type="native",
        auth=ConnectorAuthManifest(
            type=AuthStrategyType.OAUTH2,
            scopes=scopes,
            config_schema=dict(catalog.get("config_schema_json") or {}),
            reauthorization=ReauthorizationBehavior.AUTO_REFRESH,
        ),
        triggers=[],
        actions=actions,
        health=HealthProbeManifest(operation_slug=None, interval_seconds=3600, timeout_seconds=15),
        rate_limits=RateLimitManifest(requests_per_minute=120, burst=30, scope="installation"),
        metadata={"health_probe": "GET /services/data/v59.0/limits"},
    )


def register_builtin_manifests() -> None:
    """Register reference manifests for built-in native connectors."""
    ConnectorManifestRegistry.register_manifest(build_gmail_manifest())
    ConnectorManifestRegistry.register_manifest(build_outlook_manifest())
    ConnectorManifestRegistry.register_manifest(build_google_calendar_manifest())
    ConnectorManifestRegistry.register_manifest(build_microsoft_calendar_manifest())
    ConnectorManifestRegistry.register_manifest(build_google_drive_manifest())
    ConnectorManifestRegistry.register_manifest(build_microsoft_drive_manifest())
    ConnectorManifestRegistry.register_manifest(build_jira_manifest())
    ConnectorManifestRegistry.register_manifest(build_linear_manifest())
    ConnectorManifestRegistry.register_manifest(build_hubspot_manifest())
    ConnectorManifestRegistry.register_manifest(build_salesforce_manifest())
    ConnectorManifestRegistry.register_manifest(build_telegram_manifest())
    ConnectorManifestRegistry.register_manifest(build_slack_manifest())
    ConnectorManifestRegistry.register_manifest(build_teams_manifest())


def register_builtin_providers() -> None:
    """Register native connector providers that implement the runtime contract."""
    from backend.modules.workforce.connectors.gmail_provider import GmailConnectorProvider
    from backend.modules.workforce.connectors.google_calendar_provider import (
        GoogleCalendarConnectorProvider,
    )
    from backend.modules.workforce.connectors.google_drive_provider import (
        GoogleDriveConnectorProvider,
    )
    from backend.modules.workforce.connectors.hubspot_provider import HubSpotConnectorProvider
    from backend.modules.workforce.connectors.jira_provider import JiraConnectorProvider
    from backend.modules.workforce.connectors.linear_provider import LinearConnectorProvider
    from backend.modules.workforce.connectors.microsoft_calendar_provider import (
        MicrosoftCalendarConnectorProvider,
    )
    from backend.modules.workforce.connectors.microsoft_drive_provider import (
        MicrosoftDriveConnectorProvider,
    )
    from backend.modules.workforce.connectors.outlook_provider import OutlookConnectorProvider
    from backend.modules.workforce.connectors.salesforce_provider import SalesforceConnectorProvider
    from backend.modules.workforce.connectors.slack_provider import SlackConnectorProvider
    from backend.modules.workforce.connectors.teams_provider import TeamsConnectorProvider
    from backend.modules.workforce.connectors.telegram_provider import TelegramConnectorProvider

    ConnectorManifestRegistry.register_provider(GmailConnectorProvider())
    ConnectorManifestRegistry.register_provider(GoogleCalendarConnectorProvider())
    ConnectorManifestRegistry.register_provider(GoogleDriveConnectorProvider())
    ConnectorManifestRegistry.register_provider(MicrosoftCalendarConnectorProvider())
    ConnectorManifestRegistry.register_provider(MicrosoftDriveConnectorProvider())
    ConnectorManifestRegistry.register_provider(JiraConnectorProvider())
    ConnectorManifestRegistry.register_provider(LinearConnectorProvider())
    ConnectorManifestRegistry.register_provider(HubSpotConnectorProvider())
    ConnectorManifestRegistry.register_provider(SalesforceConnectorProvider())
    ConnectorManifestRegistry.register_provider(OutlookConnectorProvider())
    ConnectorManifestRegistry.register_provider(TelegramConnectorProvider())
    ConnectorManifestRegistry.register_provider(SlackConnectorProvider())
    ConnectorManifestRegistry.register_provider(TeamsConnectorProvider())
