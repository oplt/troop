"""Tests for Google + Microsoft Calendar connector integrations (CONN-005)."""

from __future__ import annotations

from backend.modules.workforce.integrations.calendar_events import (
    calendar_event_arguments_hash,
    canonical_calendar_event_arguments,
)


def test_calendar_event_hash_is_canonical() -> None:
    base = {
        "provider": "google_calendar",
        "connector_installation_id": "install-a",
        "calendar_id": "primary",
        "event_id": "evt-1",
        "subject": "Planning sync",
        "body": "Discuss roadmap",
        "location": "Zoom",
        "start_at": "2026-01-01T10:00:00Z",
        "end_at": "2026-01-01T11:00:00Z",
        "timezone": "UTC",
        "attendees": [{"email": "b@example.com"}, {"email": "a@example.com"}],
    }
    reordered = {**base, "attendees": list(reversed(base["attendees"]))}
    assert calendar_event_arguments_hash(base) == calendar_event_arguments_hash(reordered)
    assert calendar_event_arguments_hash(base) != calendar_event_arguments_hash(
        {**base, "subject": "Changed"}
    )
    canonical = canonical_calendar_event_arguments(base)
    assert canonical["provider"] == "google_calendar"
    assert canonical["attendees"] == ["a@example.com", "b@example.com"]


def test_calendar_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    google = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("google_calendar.")}
    microsoft = {
        item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("microsoft_calendar.")
    }
    assert google >= {
        "google_calendar.list_events",
        "google_calendar.get_event",
        "google_calendar.get_availability",
        "google_calendar.create_event",
        "google_calendar.update_event",
        "google_calendar.cancel_event",
    }
    assert microsoft >= {
        "microsoft_calendar.list_events",
        "microsoft_calendar.get_event",
        "microsoft_calendar.get_availability",
        "microsoft_calendar.create_event",
        "microsoft_calendar.update_event",
        "microsoft_calendar.cancel_event",
    }


def test_calendar_mutations_require_approval_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    by_slug = {item["slug"]: item for item in NATIVE_TOOL_CATALOG}
    for slug in (
        "google_calendar.create_event",
        "google_calendar.update_event",
        "google_calendar.cancel_event",
        "microsoft_calendar.create_event",
        "microsoft_calendar.update_event",
        "microsoft_calendar.cancel_event",
    ):
        assert by_slug[slug]["requires_approval"] is True
    for slug in (
        "google_calendar.list_events",
        "google_calendar.get_availability",
        "microsoft_calendar.list_events",
        "microsoft_calendar.get_availability",
    ):
        assert by_slug[slug]["requires_approval"] is False


def test_calendar_manifests_registered() -> None:
    from backend.modules.workforce.connectors import (
        ConnectorManifestRegistry,
        register_builtin_manifests,
    )

    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    for slug in ("google_calendar", "microsoft_calendar"):
        manifest = ConnectorManifestRegistry.get_manifest(slug)
        assert manifest is not None
        action_slugs = {item.slug for item in manifest.actions}
        assert f"{slug}.list_events" in action_slugs
        assert f"{slug}.cancel_event" in action_slugs
