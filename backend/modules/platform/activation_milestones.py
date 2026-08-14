"""Workspace activation milestone helpers (PROD-001B)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Final, Literal

ActivationMilestoneKey = Literal[
    "first_connected_integration",
    "first_test_run",
    "first_published_workflow",
    "first_external_effect",
]

MILESTONE_ORDER: tuple[ActivationMilestoneKey, ...] = (
    "first_connected_integration",
    "first_test_run",
    "first_published_workflow",
    "first_external_effect",
)

MILESTONE_LABELS: dict[ActivationMilestoneKey, str] = {
    "first_connected_integration": "Connect an integration",
    "first_test_run": "Run a workflow test",
    "first_published_workflow": "Publish a workflow",
    "first_external_effect": "Complete first external effect",
}

MILESTONE_CTA: dict[ActivationMilestoneKey, str] = {
    "first_connected_integration": "Connect integration",
    "first_test_run": "Test workflow",
    "first_published_workflow": "Publish workflow",
    "first_external_effect": "Review approvals",
}

MILESTONE_PATHS: dict[ActivationMilestoneKey, str] = {
    "first_connected_integration": "/integrations",
    "first_test_run": "/workforce-workflows",
    "first_published_workflow": "/workforce-workflows",
    "first_external_effect": "/approvals",
}

SETTINGS_KEY: Final[str] = "activation"


def _parse_dt(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=UTC)
        return parsed
    except ValueError:
        return None


def _iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=UTC)
    return dt.astimezone(UTC).isoformat()


def duration_seconds(start: datetime | None, end: datetime | None) -> int | None:
    if start is None or end is None:
        return None
    if start.tzinfo is None:
        start = start.replace(tzinfo=UTC)
    if end.tzinfo is None:
        end = end.replace(tzinfo=UTC)
    delta = end - start
    return max(0, int(delta.total_seconds()))


def read_activation_state(settings_json: dict[str, Any] | None) -> dict[str, Any]:
    raw = dict(settings_json or {}).get(SETTINGS_KEY) or {}
    milestones = dict(raw.get("milestones") or {})
    return {
        "baseline_at": raw.get("baseline_at"),
        "milestones": milestones,
    }


def write_activation_state(
    settings_json: dict[str, Any] | None,
    activation: dict[str, Any],
) -> dict[str, Any]:
    base = dict(settings_json or {})
    base[SETTINGS_KEY] = activation
    return base


def merge_milestone(
    milestones: dict[str, Any],
    key: ActivationMilestoneKey,
    *,
    at: datetime,
    resource_type: str | None = None,
    resource_id: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> bool:
    """Return True when a new milestone was recorded."""
    if key in milestones:
        return False
    entry: dict[str, Any] = {"at": _iso(at)}
    if resource_type:
        entry["resource_type"] = resource_type
    if resource_id:
        entry["resource_id"] = resource_id
    if metadata:
        entry["metadata"] = metadata
    milestones[key] = entry
    return True


def next_recommended_milestone(milestones: dict[str, Any]) -> ActivationMilestoneKey | None:
    for key in MILESTONE_ORDER:
        if key not in milestones:
            return key
    return None


def build_activation_response(
    *,
    workspace_id: str,
    baseline_at: datetime,
    milestones: dict[str, Any],
) -> dict[str, Any]:
    baseline_iso = _iso(baseline_at)
    items: list[dict[str, Any]] = []
    for key in MILESTONE_ORDER:
        raw = milestones.get(key)
        if not isinstance(raw, dict):
            items.append(
                {
                    "key": key,
                    "label": MILESTONE_LABELS[key],
                    "completed": False,
                    "completed_at": None,
                    "seconds_from_baseline": None,
                }
            )
            continue
        completed_at = _parse_dt(str(raw.get("at") or ""))
        items.append(
            {
                "key": key,
                "label": MILESTONE_LABELS[key],
                "completed": completed_at is not None,
                "completed_at": _iso(completed_at),
                "seconds_from_baseline": duration_seconds(baseline_at, completed_at),
                "resource_type": raw.get("resource_type"),
                "resource_id": raw.get("resource_id"),
                "metadata": raw.get("metadata") or {},
            }
        )

    next_key = next_recommended_milestone(milestones)
    completed_count = sum(1 for item in items if item["completed"])
    last_completed_at = None
    for key in reversed(MILESTONE_ORDER):
        raw = milestones.get(key)
        if isinstance(raw, dict) and raw.get("at"):
            last_completed_at = _parse_dt(str(raw["at"]))
            break

    return {
        "workspace_id": workspace_id,
        "baseline_at": baseline_iso,
        "milestones": items,
        "completed_count": completed_count,
        "total_count": len(MILESTONE_ORDER),
        "activated": completed_count == len(MILESTONE_ORDER),
        "seconds_to_activate": duration_seconds(baseline_at, last_completed_at)
        if completed_count == len(MILESTONE_ORDER)
        else None,
        "next_step": (
            {
                "key": next_key,
                "label": MILESTONE_LABELS[next_key],
                "cta": MILESTONE_CTA[next_key],
                "path": MILESTONE_PATHS[next_key],
            }
            if next_key
            else None
        ),
    }
