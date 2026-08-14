"""Characterization tests for portfolio control-plane helpers."""

from __future__ import annotations

from types import SimpleNamespace

from backend.modules.projects.portfolio.control_plane_helpers import (
    build_project_control_plane_row,
    compute_project_health,
)


def test_compute_project_health_marks_critical_when_many_blockers():
    health = compute_project_health(
        blocked_count=5,
        repo_failures=2,
        ingest_failures=1,
        escalation_count=3,
    )
    assert health["status"] == "critical"
    assert health["open_blockers"] == 5


def test_build_project_control_plane_row_includes_manager_and_policy():
    project = SimpleNamespace(id="proj-1", name="Alpha", slug="alpha")
    manager = SimpleNamespace(id="mgr-1", name="Manager", slug="manager")
    row = build_project_control_plane_row(
        project=project,
        manager_agent=manager,
        task_counts={"blocked": 1, "queued": 2},
        run_counts={"queued": 1, "in_progress": 1},
        blocked_tasks=[],
        project_approvals=[],
        latest_run=None,
        repo_failures=0,
        ingest_failures=0,
        cost_usd_30d=12.5,
        token_total_30d=900,
        repository_links=2,
        execution_policy={"routing_mode": "capability_based"},
    )
    assert row["project_id"] == "proj-1"
    assert row["manager"]["agent_id"] == "mgr-1"
    assert row["execution_policy"]["routing_mode"] == "capability_based"
    assert row["cost_rollup"]["cost_usd_30d"] == 12.5
