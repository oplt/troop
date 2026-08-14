"""Provider-neutral calendar event normalization and approval fingerprints."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.tool_execution_context import arguments_hash


def _normalize_attendees(value: Any) -> list[str]:
    raw = value if isinstance(value, list) else ([value] if value else [])
    emails: list[str] = []
    for item in raw:
        if isinstance(item, dict):
            address = item.get("email") or (item.get("emailAddress") or {}).get("address")
        else:
            address = item
        if address:
            emails.append(str(address).strip().lower())
    return sorted(emails)


def canonical_calendar_event_arguments(arguments: dict[str, Any]) -> dict[str, Any]:
    return {
        "provider": str(arguments.get("provider") or ""),
        "connector_installation_id": str(arguments.get("connector_installation_id") or ""),
        "calendar_id": str(arguments.get("calendar_id") or "primary"),
        "event_id": str(arguments.get("event_id") or ""),
        "subject": str(arguments.get("subject") or arguments.get("summary") or ""),
        "body": str(arguments.get("body") or arguments.get("description") or ""),
        "location": str(arguments.get("location") or ""),
        "start_at": str(arguments.get("start_at") or arguments.get("start") or ""),
        "end_at": str(arguments.get("end_at") or arguments.get("end") or ""),
        "timezone": str(arguments.get("timezone") or arguments.get("time_zone") or "UTC"),
        "attendees": _normalize_attendees(arguments.get("attendees")),
        "is_online_meeting": bool(arguments.get("is_online_meeting", False)),
    }


def calendar_event_arguments_hash(arguments: dict[str, Any]) -> str:
    return arguments_hash(canonical_calendar_event_arguments(arguments))
