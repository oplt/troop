"""Tests for activation milestone helpers."""

from __future__ import annotations

from datetime import UTC, datetime

from backend.modules.platform.activation_milestones import (
    build_activation_response,
    merge_milestone,
    next_recommended_milestone,
)


def test_next_recommended_milestone_follows_order() -> None:
    milestones: dict = {}
    assert next_recommended_milestone(milestones) == "first_connected_integration"
    merge_milestone(
        milestones,
        "first_connected_integration",
        at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    assert next_recommended_milestone(milestones) == "first_test_run"


def test_build_activation_response_includes_durations_and_next_step() -> None:
    baseline = datetime(2026, 1, 1, 0, 0, tzinfo=UTC)
    milestones: dict = {}
    merge_milestone(
        milestones,
        "first_connected_integration",
        at=datetime(2026, 1, 1, 0, 5, tzinfo=UTC),
        resource_type="connector_installation",
        resource_id="conn-1",
    )
    payload = build_activation_response(
        workspace_id="ws-1",
        baseline_at=baseline,
        milestones=milestones,
    )
    assert payload["completed_count"] == 1
    assert payload["next_step"]["key"] == "first_test_run"
    assert payload["milestones"][0]["seconds_from_baseline"] == 300
    assert payload["activated"] is False
