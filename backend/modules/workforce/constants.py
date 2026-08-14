"""Workforce constants: generic task lifecycle + legacy status aliases."""

from __future__ import annotations

# Target generic statuses (prompt §4). Legacy GitHub statuses remain readable.
GENERIC_TASK_STATUSES = frozenset(
    {
        "backlog",
        "ready",
        "planned",
        "in_progress",
        "needs_input",
        "blocked",
        "needs_review",
        "needs_approval",
        "completed",
        "archived",
        "cancelled",
    }
)

# Map legacy persisted statuses → generic equivalents for display/API.
LEGACY_STATUS_ALIASES: dict[str, str] = {
    "queued": "ready",
    "approved": "needs_approval",  # historical: approved meant ready to complete
    "failed": "blocked",
    "synced_to_github": "completed",  # GitHub sync is now an event/artifact, not a status
    "todo": "ready",
    "done": "completed",
    "review": "needs_review",
}

# Extended transitions: keep old keys for backward compatibility + add generic ones.
TASK_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"ready", "queued", "planned", "archived", "cancelled"},
    "ready": {"planned", "in_progress", "blocked", "archived", "cancelled"},
    "queued": {"ready", "planned", "blocked", "failed", "archived", "cancelled"},
    "planned": {"in_progress", "blocked", "archived", "failed", "cancelled", "needs_input"},
    "in_progress": {
        "blocked",
        "needs_input",
        "needs_review",
        "needs_approval",
        "completed",
        "failed",
        "planned",
        "cancelled",
    },
    "needs_input": {"in_progress", "planned", "blocked", "cancelled", "archived"},
    "blocked": {"planned", "in_progress", "ready", "failed", "archived", "cancelled"},
    "needs_review": {
        "needs_approval",
        "approved",
        "planned",
        "blocked",
        "failed",
        "in_progress",
        "cancelled",
    },
    "needs_approval": {"completed", "approved", "planned", "blocked", "cancelled"},
    "approved": {"completed", "planned", "archived", "needs_approval"},
    "completed": {"synced_to_github", "planned", "archived", "cancelled"},
    "failed": {"planned", "queued", "ready", "archived", "cancelled"},
    "synced_to_github": {"archived", "planned", "completed"},
    "cancelled": {"backlog", "archived"},
    "archived": set(),
}

SKILL_SCOPES = frozenset({"task", "project", "organization", "template", "global"})
SKILL_STATUSES = frozenset({"draft", "testing", "active", "deprecated", "archived"})
SKILL_DRAFT_SOURCES = frozenset(
    {
        "manual",
        "markdown_import",
        "task_generation",
        "project_generation",
        "agent_recommendation",
        "skill_clone",
        "improvement",
    }
)

ANALYZER_VERSION = "1.0.0"

# Native tools registered into ToolDefinition on seed.
NATIVE_TOOL_CATALOG: list[dict] = [
    {
        "slug": "gmail.search_messages",
        "name": "Gmail Search Messages",
        "description": "Search an explicitly bound Gmail mailbox",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "query"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "slug": "gmail.get_message",
        "name": "Gmail Get Message",
        "description": "Read one Gmail message",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "message_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "message_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "gmail.get_thread",
        "name": "Gmail Get Thread",
        "description": "Read one Gmail thread",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "thread_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "thread_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "gmail.create_draft",
        "name": "Gmail Create Draft",
        "description": "Create a reply draft without sending",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "to", "subject", "body"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "array"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "slug": "gmail.update_draft",
        "name": "Gmail Update Draft",
        "description": "Replace exact Gmail draft content",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "gmail_draft_id", "to", "subject", "body"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "gmail_draft_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "array"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "slug": "gmail.send_draft",
        "name": "Gmail Send Draft",
        "description": "Send an exact approved Gmail draft",
        "risk_level": "high",
        "requires_approval": True,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": [
                "connector_installation_id",
                "gmail_draft_id",
                "thread_id",
                "to",
                "subject",
                "body",
            ],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "gmail_draft_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "array"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "slug": "gmail.add_label",
        "name": "Gmail Add Label",
        "description": "Modify labels on a Gmail message",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "message_id", "add_label_ids"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "message_id": {"type": "string"},
                "add_label_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "slug": "outlook.search_messages",
        "name": "Outlook Search Messages",
        "description": "Search an explicitly bound Outlook mailbox",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "query"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "query": {"type": "string"},
                "limit": {"type": "integer", "minimum": 1, "maximum": 100},
            },
        },
    },
    {
        "slug": "outlook.get_message",
        "name": "Outlook Get Message",
        "description": "Read one Outlook message",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "message_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "message_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "outlook.get_thread",
        "name": "Outlook Get Thread",
        "description": "Read one Outlook conversation thread",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "thread_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "thread_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "outlook.create_draft",
        "name": "Outlook Create Draft",
        "description": "Create a reply draft without sending",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "to", "subject", "body"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "array"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "slug": "outlook.update_draft",
        "name": "Outlook Update Draft",
        "description": "Replace exact Outlook draft content",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "outlook_draft_id", "to", "subject", "body"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "outlook_draft_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "array"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "slug": "outlook.send_draft",
        "name": "Outlook Send Draft",
        "description": "Send an exact approved Outlook draft",
        "risk_level": "high",
        "requires_approval": True,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": [
                "connector_installation_id",
                "outlook_draft_id",
                "thread_id",
                "to",
                "subject",
                "body",
            ],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "outlook_draft_id": {"type": "string"},
                "thread_id": {"type": "string"},
                "to": {"type": "array"},
                "cc": {"type": "array"},
                "bcc": {"type": "array"},
                "subject": {"type": "string"},
                "body": {"type": "string"},
            },
        },
    },
    {
        "slug": "outlook.add_label",
        "name": "Outlook Add Category",
        "description": "Modify categories on an Outlook message",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "message_id", "add_label_ids"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "message_id": {"type": "string"},
                "add_label_ids": {"type": "array", "items": {"type": "string"}},
            },
        },
    },
    {
        "slug": "telegram.send_message",
        "name": "Telegram Send Message",
        "description": "Send a Telegram bot message",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
    },
    {
        "slug": "telegram.edit_message",
        "name": "Telegram Edit Message",
        "description": "Edit a Telegram bot message",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
    },
    {
        "slug": "telegram.answer_callback",
        "name": "Telegram Answer Callback",
        "description": "Acknowledge a Telegram callback query",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
    },
    {
        "slug": "slack.search_messages",
        "name": "Slack Search Messages",
        "description": "Search Slack messages or scan a channel",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "query": {"type": "string"},
                "channel": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "slug": "slack.get_thread",
        "name": "Slack Get Thread",
        "description": "Read replies in a Slack thread",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "channel", "thread_ts"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "channel": {"type": "string"},
                "thread_ts": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "slug": "slack.get_message",
        "name": "Slack Get Message",
        "description": "Read a single Slack message",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "channel"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "channel": {"type": "string"},
                "message_ts": {"type": "string"},
                "latest": {"type": "string"},
            },
        },
    },
    {
        "slug": "slack.post_message",
        "name": "Slack Post Message",
        "description": "Post an approved Slack message",
        "risk_level": "high",
        "requires_approval": True,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "channel", "text"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "channel": {"type": "string"},
                "thread_ts": {"type": "string"},
                "text": {"type": "string"},
                "workflow_run_id": {"type": "string"},
                "approval_request_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "slack.update_message",
        "name": "Slack Update Message",
        "description": "Update a Slack message (approval channel feedback)",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "channel", "message_ts", "text"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "channel": {"type": "string"},
                "message_ts": {"type": "string"},
                "text": {"type": "string"},
            },
        },
    },
    {
        "slug": "teams.search_messages",
        "name": "Teams Search Messages",
        "description": "Search Microsoft Teams messages",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "query": {"type": "string"},
                "conversation_id": {"type": "string"},
                "limit": {"type": "integer"},
            },
        },
    },
    {
        "slug": "teams.get_thread",
        "name": "Teams Get Thread",
        "description": "Read replies in a Teams chat thread",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "conversation_id", "message_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "conversation_id": {"type": "string"},
                "message_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "teams.get_message",
        "name": "Teams Get Message",
        "description": "Read a single Teams message",
        "risk_level": "low",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "conversation_id", "message_id"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "conversation_id": {"type": "string"},
                "message_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "teams.post_message",
        "name": "Teams Post Message",
        "description": "Post an approved Teams message",
        "risk_level": "high",
        "requires_approval": True,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "conversation_id", "text"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "conversation_id": {"type": "string"},
                "reply_to_id": {"type": "string"},
                "text": {"type": "string"},
                "workflow_run_id": {"type": "string"},
                "approval_request_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "teams.update_message",
        "name": "Teams Update Message",
        "description": "Update a Teams message (approval channel feedback)",
        "risk_level": "medium",
        "requires_approval": False,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "conversation_id", "message_id", "text"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "conversation_id": {"type": "string"},
                "message_id": {"type": "string"},
                "text": {"type": "string"},
            },
        },
    },
    *[
        {
            "slug": f"{provider}.list_events",
            "name": f"{label} List Events",
            "description": f"List events from a bound {label} calendar",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "time_min", "time_max"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "time_min": {"type": "string"},
                    "time_max": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 250},
                },
            },
        }
        for provider, label in (
            ("google_calendar", "Google Calendar"),
            ("microsoft_calendar", "Microsoft Calendar"),
        )
    ],
    *[
        {
            "slug": f"{provider}.get_event",
            "name": f"{label} Get Event",
            "description": f"Read one {label} event",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "event_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "event_id": {"type": "string"},
                },
            },
        }
        for provider, label in (
            ("google_calendar", "Google Calendar"),
            ("microsoft_calendar", "Microsoft Calendar"),
        )
    ],
    *[
        {
            "slug": f"{provider}.get_availability",
            "name": f"{label} Get Availability",
            "description": f"Read free/busy availability from {label}",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "time_min", "time_max"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "time_min": {"type": "string"},
                    "time_max": {"type": "string"},
                    "timezone": {"type": "string"},
                    "schedules": {"type": "array"},
                    "calendars": {"type": "array"},
                    "interval_minutes": {"type": "integer"},
                },
            },
        }
        for provider, label in (
            ("google_calendar", "Google Calendar"),
            ("microsoft_calendar", "Microsoft Calendar"),
        )
    ],
    *[
        {
            "slug": f"{provider}.create_event",
            "name": f"{label} Create Event",
            "description": f"Create an approved {label} event",
            "risk_level": "medium",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": [
                    "connector_installation_id",
                    "subject",
                    "start_at",
                    "end_at",
                ],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "location": {"type": "string"},
                    "start_at": {"type": "string"},
                    "end_at": {"type": "string"},
                    "timezone": {"type": "string"},
                    "attendees": {"type": "array"},
                    "is_online_meeting": {"type": "boolean"},
                },
            },
        }
        for provider, label in (
            ("google_calendar", "Google Calendar"),
            ("microsoft_calendar", "Microsoft Calendar"),
        )
    ],
    *[
        {
            "slug": f"{provider}.update_event",
            "name": f"{label} Update Event",
            "description": f"Update an approved {label} event",
            "risk_level": "medium",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": [
                    "connector_installation_id",
                    "event_id",
                    "subject",
                    "start_at",
                    "end_at",
                ],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "event_id": {"type": "string"},
                    "subject": {"type": "string"},
                    "body": {"type": "string"},
                    "location": {"type": "string"},
                    "start_at": {"type": "string"},
                    "end_at": {"type": "string"},
                    "timezone": {"type": "string"},
                    "attendees": {"type": "array"},
                },
            },
        }
        for provider, label in (
            ("google_calendar", "Google Calendar"),
            ("microsoft_calendar", "Microsoft Calendar"),
        )
    ],
    *[
        {
            "slug": f"{provider}.cancel_event",
            "name": f"{label} Cancel Event",
            "description": f"Cancel an approved {label} event",
            "risk_level": "high",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "event_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "calendar_id": {"type": "string"},
                    "event_id": {"type": "string"},
                },
            },
        }
        for provider, label in (
            ("google_calendar", "Google Calendar"),
            ("microsoft_calendar", "Microsoft Calendar"),
        )
    ],
    *[
        {
            "slug": f"{provider}.search_files",
            "name": f"{label} Search Files",
            "description": f"Search files in bound {label}",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "query": {"type": "string"},
                    "folder_id": {"type": "string"},
                    "drive_id": {"type": "string"},
                    "site_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        }
        for provider, label in (
            ("google_drive", "Google Drive"),
            ("microsoft_drive", "Microsoft Drive"),
        )
    ],
    *[
        {
            "slug": f"{provider}.get_file_metadata",
            "name": f"{label} Get File Metadata",
            "description": f"Read metadata and ACL snapshot for one {label} file",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "file_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "file_id": {"type": "string"},
                    "drive_id": {"type": "string"},
                    "site_id": {"type": "string"},
                },
            },
        }
        for provider, label in (
            ("google_drive", "Google Drive"),
            ("microsoft_drive", "Microsoft Drive"),
        )
    ],
    *[
        {
            "slug": f"{provider}.get_file_content",
            "name": f"{label} Get File Content",
            "description": f"Read text content from one {label} file",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "file_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "file_id": {"type": "string"},
                    "drive_id": {"type": "string"},
                    "site_id": {"type": "string"},
                },
            },
        }
        for provider, label in (
            ("google_drive", "Google Drive"),
            ("microsoft_drive", "Microsoft Drive"),
        )
    ],
    *[
        {
            "slug": f"{provider}.search_issues",
            "name": f"{label} Search Issues",
            "description": f"Search issues in bound {label}",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "jql": {"type": "string"},
                    "query": {"type": "string"},
                    "team_id": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        }
        for provider, label in (("jira", "Jira"), ("linear", "Linear"))
    ],
    *[
        {
            "slug": f"{provider}.get_issue",
            "name": f"{label} Get Issue",
            "description": f"Read one {label} issue with context",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                    "issue_key": {"type": "string"},
                },
            },
        }
        for provider, label in (("jira", "Jira"), ("linear", "Linear"))
    ],
    *[
        {
            "slug": f"{provider}.get_issue_comments",
            "name": f"{label} Get Issue Comments",
            "description": f"Read comments on one {label} issue",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                    "issue_key": {"type": "string"},
                },
            },
        }
        for provider, label in (("jira", "Jira"), ("linear", "Linear"))
    ],
    *[
        {
            "slug": f"{provider}.create_issue",
            "name": f"{label} Create Issue",
            "description": f"Create an approved {label} issue",
            "risk_level": "medium",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "project_key": {"type": "string"},
                    "team_id": {"type": "string"},
                    "issue_type": {"type": "string"},
                    "summary": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "priority": {"type": "string"},
                    "workflow_run_id": {"type": "string"},
                    "approval_request_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("jira", "Jira"), ("linear", "Linear"))
    ],
    *[
        {
            "slug": f"{provider}.update_issue",
            "name": f"{label} Update Issue",
            "description": f"Update an approved {label} issue",
            "risk_level": "medium",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                    "issue_key": {"type": "string"},
                    "summary": {"type": "string"},
                    "title": {"type": "string"},
                    "description": {"type": "string"},
                    "state_id": {"type": "string"},
                    "priority": {"type": "string"},
                    "workflow_run_id": {"type": "string"},
                    "approval_request_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("jira", "Jira"), ("linear", "Linear"))
    ],
    *[
        {
            "slug": f"{provider}.add_comment",
            "name": f"{label} Add Comment",
            "description": f"Add an approved comment to a {label} issue",
            "risk_level": "medium",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "comment_body"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "issue_id": {"type": "string"},
                    "issue_key": {"type": "string"},
                    "comment_body": {"type": "string"},
                    "workflow_run_id": {"type": "string"},
                    "approval_request_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("jira", "Jira"), ("linear", "Linear"))
    ],
    *[
        {
            "slug": f"{provider}.search_contacts",
            "name": f"{label} Search Contacts",
            "description": f"Search contacts in {label}",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "query": {"type": "string"},
                    "soql": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        }
        for provider, label in (("hubspot", "HubSpot"), ("salesforce", "Salesforce"))
    ],
    *[
        {
            "slug": f"{provider}.get_contact",
            "name": f"{label} Get Contact",
            "description": f"Read one {label} contact",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "contact_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "contact_id": {"type": "string"},
                    "record_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("hubspot", "HubSpot"), ("salesforce", "Salesforce"))
    ],
    *[
        {
            "slug": f"{provider}.search_companies" if provider == "hubspot" else f"{provider}.search_accounts",
            "name": f"{label} Search {'Companies' if provider == 'hubspot' else 'Accounts'}",
            "description": f"Search {'companies' if provider == 'hubspot' else 'accounts'} in {label}",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "query": {"type": "string"},
                    "soql": {"type": "string"},
                    "limit": {"type": "integer", "minimum": 1, "maximum": 100},
                },
            },
        }
        for provider, label in (("hubspot", "HubSpot"), ("salesforce", "Salesforce"))
    ],
    *[
        {
            "slug": f"{provider}.get_company" if provider == "hubspot" else f"{provider}.get_account",
            "name": f"{label} Get {'Company' if provider == 'hubspot' else 'Account'}",
            "description": f"Read one {label} {'company' if provider == 'hubspot' else 'account'}",
            "risk_level": "low",
            "requires_approval": False,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "company_id": {"type": "string"},
                    "account_id": {"type": "string"},
                    "record_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("hubspot", "HubSpot"), ("salesforce", "Salesforce"))
    ],
    *[
        {
            "slug": f"{provider}.update_contact",
            "name": f"{label} Update Contact",
            "description": f"Update allowlisted fields on an approved {label} contact",
            "risk_level": "medium",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id", "contact_id", "fields"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "contact_id": {"type": "string"},
                    "record_id": {"type": "string"},
                    "fields": {"type": "object"},
                    "workflow_run_id": {"type": "string"},
                    "approval_request_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("hubspot", "HubSpot"), ("salesforce", "Salesforce"))
    ],
    {
        "slug": "hubspot.create_note",
        "name": "HubSpot Create Note",
        "description": "Create an approved note on a HubSpot contact",
        "risk_level": "medium",
        "requires_approval": True,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "contact_id", "note_body"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "contact_id": {"type": "string"},
                "note_body": {"type": "string"},
                "workflow_run_id": {"type": "string"},
                "approval_request_id": {"type": "string"},
            },
        },
    },
    {
        "slug": "salesforce.create_task",
        "name": "Salesforce Create Task",
        "description": "Create an approved task on a Salesforce contact",
        "risk_level": "medium",
        "requires_approval": True,
        "provider_type": "native_connector",
        "schema_json": {
            "type": "object",
            "required": ["connector_installation_id", "contact_id", "task_subject"],
            "properties": {
                "connector_installation_id": {"type": "string"},
                "contact_id": {"type": "string"},
                "task_subject": {"type": "string"},
                "task_description": {"type": "string"},
                "workflow_run_id": {"type": "string"},
                "approval_request_id": {"type": "string"},
            },
        },
    },
    *[
        {
            "slug": f"{provider}.send_email",
            "name": f"{label} Send Email",
            "description": f"Send an approved outreach email via {label}",
            "risk_level": "high",
            "requires_approval": True,
            "provider_type": "native_connector",
            "schema_json": {
                "type": "object",
                "required": ["connector_installation_id"],
                "properties": {
                    "connector_installation_id": {"type": "string"},
                    "contact_id": {"type": "string"},
                    "email_to": {"type": "string"},
                    "email_id": {"type": "string"},
                    "email_subject": {"type": "string"},
                    "email_body": {"type": "string"},
                    "workflow_run_id": {"type": "string"},
                    "approval_request_id": {"type": "string"},
                },
            },
        }
        for provider, label in (("hubspot", "HubSpot"), ("salesforce", "Salesforce"))
    ],
    {
        "slug": "web_search",
        "name": "Web Search",
        "description": "Search the public web",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "web_fetch",
        "name": "Web Fetch",
        "description": "Fetch a URL",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "knowledge_search",
        "name": "Knowledge Search",
        "description": "Search project/org knowledge",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "repo_search",
        "name": "Repository Search",
        "description": "Search linked repositories",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "fs_read",
        "name": "Filesystem Read",
        "description": "Read files in workspace",
        "risk_level": "low",
        "requires_approval": False,
    },
    {
        "slug": "fs_write",
        "name": "Filesystem Write",
        "description": "Write files in workspace",
        "risk_level": "high",
        "requires_approval": True,
    },
    {
        "slug": "code_execute",
        "name": "Code Execute",
        "description": "Execute code in sandbox",
        "risk_level": "high",
        "requires_approval": True,
    },
    {
        "slug": "db_query",
        "name": "Database Query",
        "description": "Run read/write DB queries",
        "risk_level": "critical",
        "requires_approval": True,
    },
    {
        "slug": "github_comment",
        "name": "GitHub Comment",
        "description": "Comment on GitHub issues/PRs",
        "risk_level": "medium",
        "requires_approval": True,
        "provider_type": "github",
    },
    {
        "slug": "github_label_issue",
        "name": "GitHub Label Issue",
        "description": "Add/remove GitHub issue labels",
        "risk_level": "medium",
        "requires_approval": True,
        "provider_type": "github",
    },
    {
        "slug": "github_create_pr",
        "name": "GitHub Create PR",
        "description": "Open a pull request",
        "risk_level": "high",
        "requires_approval": True,
        "provider_type": "github",
    },
    {
        "slug": "invoke_specialist",
        "name": "Invoke Specialist",
        "description": "Delegate a bounded sub-task to a specialist agent (max depth 1)",
        "risk_level": "medium",
        "requires_approval": False,
        "schema_json": {
            "type": "object",
            "required": ["specialist_agent_id", "prompt"],
            "properties": {
                "specialist_agent_id": {"type": "string"},
                "prompt": {"type": "string"},
            },
        },
    },
]

DEFAULT_ACTION_POLICIES: list[dict] = [
    {"action_key": "gmail.search_messages", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "gmail.get_message", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "gmail.get_thread", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "gmail.create_draft", "decision": "autonomous", "risk_level": "medium"},
    {"action_key": "gmail.update_draft", "decision": "autonomous", "risk_level": "medium"},
    {
        "action_key": "gmail.send_draft",
        "decision": "approval_required",
        "risk_level": "high",
    },
    {"action_key": "outlook.search_messages", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "outlook.get_message", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "outlook.get_thread", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "outlook.create_draft", "decision": "autonomous", "risk_level": "medium"},
    {"action_key": "outlook.update_draft", "decision": "autonomous", "risk_level": "medium"},
    {
        "action_key": "outlook.send_draft",
        "decision": "approval_required",
        "risk_level": "high",
    },
    *[
        {"action_key": f"{provider}.list_events", "decision": "autonomous", "risk_level": "low"}
        for provider in ("google_calendar", "microsoft_calendar")
    ],
    *[
        {"action_key": f"{provider}.get_event", "decision": "autonomous", "risk_level": "low"}
        for provider in ("google_calendar", "microsoft_calendar")
    ],
    *[
        {
            "action_key": f"{provider}.get_availability",
            "decision": "autonomous",
            "risk_level": "low",
        }
        for provider in ("google_calendar", "microsoft_calendar")
    ],
    *[
        {
            "action_key": f"{provider}.create_event",
            "decision": "approval_required",
            "risk_level": "medium",
        }
        for provider in ("google_calendar", "microsoft_calendar")
    ],
    *[
        {
            "action_key": f"{provider}.update_event",
            "decision": "approval_required",
            "risk_level": "medium",
        }
        for provider in ("google_calendar", "microsoft_calendar")
    ],
    *[
        {
            "action_key": f"{provider}.cancel_event",
            "decision": "approval_required",
            "risk_level": "high",
        }
        for provider in ("google_calendar", "microsoft_calendar")
    ],
    *[
        {"action_key": f"{provider}.search_files", "decision": "autonomous", "risk_level": "low"}
        for provider in ("google_drive", "microsoft_drive")
    ],
    *[
        {"action_key": f"{provider}.get_file_metadata", "decision": "autonomous", "risk_level": "low"}
        for provider in ("google_drive", "microsoft_drive")
    ],
    *[
        {"action_key": f"{provider}.get_file_content", "decision": "autonomous", "risk_level": "low"}
        for provider in ("google_drive", "microsoft_drive")
    ],
    *[
        {"action_key": f"{provider}.search_issues", "decision": "autonomous", "risk_level": "low"}
        for provider in ("jira", "linear")
    ],
    *[
        {"action_key": f"{provider}.get_issue", "decision": "autonomous", "risk_level": "low"}
        for provider in ("jira", "linear")
    ],
    *[
        {
            "action_key": f"{provider}.get_issue_comments",
            "decision": "autonomous",
            "risk_level": "low",
        }
        for provider in ("jira", "linear")
    ],
    *[
        {
            "action_key": f"{provider}.create_issue",
            "decision": "approval_required",
            "risk_level": "medium",
        }
        for provider in ("jira", "linear")
    ],
    *[
        {
            "action_key": f"{provider}.update_issue",
            "decision": "approval_required",
            "risk_level": "medium",
        }
        for provider in ("jira", "linear")
    ],
    *[
        {
            "action_key": f"{provider}.add_comment",
            "decision": "approval_required",
            "risk_level": "medium",
        }
        for provider in ("jira", "linear")
    ],
    *[
        {"action_key": f"{provider}.search_contacts", "decision": "autonomous", "risk_level": "low"}
        for provider in ("hubspot", "salesforce")
    ],
    *[
        {"action_key": f"{provider}.get_contact", "decision": "autonomous", "risk_level": "low"}
        for provider in ("hubspot", "salesforce")
    ],
    *[
        {
            "action_key": f"{provider}.search_companies",
            "decision": "autonomous",
            "risk_level": "low",
        }
        for provider in ("hubspot",)
    ],
    *[
        {
            "action_key": f"{provider}.get_company",
            "decision": "autonomous",
            "risk_level": "low",
        }
        for provider in ("hubspot",)
    ],
    *[
        {
            "action_key": f"{provider}.search_accounts",
            "decision": "autonomous",
            "risk_level": "low",
        }
        for provider in ("salesforce",)
    ],
    *[
        {
            "action_key": f"{provider}.get_account",
            "decision": "autonomous",
            "risk_level": "low",
        }
        for provider in ("salesforce",)
    ],
    *[
        {
            "action_key": f"{provider}.update_contact",
            "decision": "approval_required",
            "risk_level": "medium",
        }
        for provider in ("hubspot", "salesforce")
    ],
    {"action_key": "hubspot.create_note", "decision": "approval_required", "risk_level": "medium"},
    {"action_key": "salesforce.create_task", "decision": "approval_required", "risk_level": "medium"},
    *[
        {
            "action_key": f"{provider}.send_email",
            "decision": "approval_required",
            "risk_level": "high",
        }
        for provider in ("hubspot", "salesforce")
    ],
    {"action_key": "slack.search_messages", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "slack.get_thread", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "slack.get_message", "decision": "autonomous", "risk_level": "low"},
    {
        "action_key": "slack.post_message",
        "decision": "approval_required",
        "risk_level": "high",
    },
    {"action_key": "teams.search_messages", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "teams.get_thread", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "teams.get_message", "decision": "autonomous", "risk_level": "low"},
    {
        "action_key": "teams.post_message",
        "decision": "approval_required",
        "risk_level": "high",
    },
    {"action_key": "web_search", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "knowledge_read", "decision": "autonomous", "risk_level": "low"},
    {"action_key": "external_email_send", "decision": "approval_required", "risk_level": "high"},
    {"action_key": "social_publish", "decision": "approval_required", "risk_level": "high"},
    {"action_key": "ad_budget_change", "decision": "approval_required", "risk_level": "critical"},
    {"action_key": "delete_record", "decision": "approval_required", "risk_level": "critical"},
    {"action_key": "merge_pull_request", "decision": "approval_required", "risk_level": "high"},
    {
        "action_key": "shell_destructive_action",
        "decision": "prohibited",
        "risk_level": "critical",
    },
    {"action_key": "invoke_specialist", "decision": "autonomous", "risk_level": "medium"},
]
