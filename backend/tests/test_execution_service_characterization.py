"""Phase 0 — characterization tests for orchestration execution_service."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.execution.execution_state import (
    EXECUTION_SNAPSHOT_SCHEMA_VERSION,
)
from backend.modules.orchestration.execution.execution_workflow import (
    ensure_workflow_state,
    mark_step,
    set_workflow_artifact,
)
from backend.modules.orchestration.execution.policies import next_retry_numbers


def _execution_service(**overrides) -> OrchestrationExecutionServiceMixin:
    service = OrchestrationExecutionServiceMixin()
    service.db = MagicMock()
    service.repo = MagicMock()
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def _run(
    *,
    run_id: str = "run-1",
    status: str = "failed",
    run_mode: str = "manager_worker",
    checkpoint_json: dict | None = None,
    retry_count: int = 0,
    attempt_number: int = 1,
) -> SimpleNamespace:
    return SimpleNamespace(
        id=run_id,
        status=status,
        run_mode=run_mode,
        project_id="proj-1",
        task_id="task-1",
        parent_run_id=None,
        triggered_by_user_id="user-1",
        orchestrator_agent_id="agent-mgr",
        worker_agent_id="agent-worker",
        reviewer_agent_id=None,
        provider_config_id=None,
        brainstorm_id=None,
        model_name="local-heuristic",
        attempt_number=attempt_number,
        retry_count=retry_count,
        input_payload_json={},
        output_payload_json={},
        error_message="timeout",
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        completed_at=None,
        cancelled_at=None,
        checkpoint_json=checkpoint_json or {},
    )


def _failed_resumable_checkpoint(run_id: str = "run-1") -> dict:
    checkpoint = ensure_workflow_state(
        {},
        run_mode="manager_worker",
        steps=[
            {"id": "planning", "title": "Planning", "actor": "supervisor"},
            {"id": "review", "title": "Review", "actor": "reviewer"},
        ],
        run_id=run_id,
    )
    return mark_step(checkpoint, step_id="planning", status="failed", error="model timeout")


def test_normalize_subtask_graph_assigns_branch_ids_and_dependencies():
    service = _execution_service()
    parent = SimpleNamespace(acceptance_criteria="Ship with tests")
    graph = service._normalize_subtask_graph(
        [
            {"title": "Plan", "dependency_indexes": []},
            {"title": "Implement", "dependency_indexes": [0], "required_tools": [" fs_read "]},
        ],
        parent_task=parent,
    )
    assert graph[0]["branch_id"] == "branch-1"
    assert graph[1]["branch_id"] == "branch-2"
    assert graph[0]["branch_id"] in graph[1]["dependency_ids"]
    assert graph[1]["required_tools"] == [" fs_read "]
    assert graph[0]["acceptance_criteria"] == "Ship with tests"


def test_worker_result_contract_normalizes_blocked_status_and_lists():
    service = _execution_service()
    contract = service._worker_result_contract(
        {"branch_id": "branch-1", "rework_scope": ["file.py"]},
        "Worker finished",
        {"status": "blocked", "summary": "Needs review", "risks": ["regression", ""]},
    )
    assert contract["status"] == "blocked"
    assert contract["summary"] == "Needs review"
    assert contract["risks"] == ["regression"]
    assert contract["rework_scope"] == ["file.py"]


def test_review_state_from_payload_defaults_decision_and_round():
    service = _execution_service()
    state = service._review_state_from_payload(
        {"summary": "Rework requested", "reasons": [" missing tests ", ""]},
        round_number=2,
    )
    assert state["round"] == 2
    assert state["decision"] == "rework"
    assert state["reasons"] == [" missing tests "]
    assert state["last_reviewed_at"]


def test_run_is_resumable_requires_failed_or_blocked_with_current_step():
    service = _execution_service()
    resumable = _run(status="failed", checkpoint_json=_failed_resumable_checkpoint())
    assert service._run_is_resumable(resumable) is True

    in_progress = _run(status="in_progress", checkpoint_json=_failed_resumable_checkpoint())
    assert service._run_is_resumable(in_progress) is False

    completed = _run(status="completed", checkpoint_json=_failed_resumable_checkpoint())
    assert service._run_is_resumable(completed) is False


def test_stage_state_payload_reads_manager_worker_artifacts():
    service = _execution_service()
    checkpoint = _failed_resumable_checkpoint()
    checkpoint = set_workflow_artifact(
        checkpoint, key="manager_worker.plan", value={"branches": 2}
    )
    checkpoint = set_workflow_artifact(
        checkpoint, key="manager_worker.branch_results", value=[{"branch_id": "b1"}]
    )
    run = _run(checkpoint_json=checkpoint)
    payload = service._stage_state_payload(run)
    assert payload["manager_plan"] == {"branches": 2}
    assert payload["branch_results"] == [{"branch_id": "b1"}]


def test_durable_workflow_payload_includes_resumable_flag():
    service = _execution_service()
    run = _run(status="failed", checkpoint_json=_failed_resumable_checkpoint())
    payload = service._durable_workflow_payload(run)
    assert payload["backend"] == "celery_checkpointed"
    assert payload["resumable"] is True
    assert payload["migration"]["strategy"] == "checkpoint-first coexistence"


def test_run_event_tail_payloads_truncates_long_messages():
    service = _execution_service()

    class _Event:
        event_type = "log"
        level = "info"
        created_at = datetime.now(UTC)

        def __init__(self, message: str):
            self.message = message

    tail = service._run_event_tail_payloads([_Event("x" * 500)], limit=5)
    assert len(tail[0]["message"]) == 401
    assert tail[0]["message"].endswith("…")


@pytest.mark.asyncio
async def test_consume_hitl_grant_marks_approval_consumed():
    service = _execution_service()
    run = _run(status="blocked")
    approval = SimpleNamespace(
        id="appr-1",
        approval_type="github_write",
        payload_json={"action": "comment"},
    )
    service.repo.list_approvals_for_run = AsyncMock(return_value=[approval])
    service._emit_run_event = AsyncMock()

    consumed = await service._consume_hitl_grant(
        run, "github_write", expected_payload={"action": "comment"}
    )

    assert consumed is True
    assert approval.payload_json["_consumed_at"]
    service._emit_run_event.assert_awaited_once()


@pytest.mark.asyncio
async def test_consume_hitl_grant_skips_already_consumed():
    service = _execution_service()
    run = _run(status="blocked")
    approval = SimpleNamespace(
        id="appr-1",
        approval_type="github_write",
        payload_json={"action": "comment", "_consumed_at": "2026-01-01T00:00:00Z"},
    )
    service.repo.list_approvals_for_run = AsyncMock(return_value=[approval])
    service._emit_run_event = AsyncMock()

    consumed = await service._consume_hitl_grant(
        run, "github_write", expected_payload={"action": "comment"}
    )

    assert consumed is False
    service._emit_run_event.assert_not_awaited()


@pytest.mark.asyncio
async def test_resume_run_rejects_non_resumable_status():
    service = _execution_service()
    run = _run(status="completed", checkpoint_json={})
    user = SimpleNamespace(id="user-1")
    service.get_run = AsyncMock(return_value=run)

    with pytest.raises(HTTPException) as exc:
        await service.resume_run(user, run.id)

    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_resume_run_requeues_blocked_child_runs():
    service = _execution_service()
    parent = _run(status="failed", checkpoint_json=_failed_resumable_checkpoint())
    child = _run(run_id="child-1", status="blocked", checkpoint_json={})
    user = SimpleNamespace(id="user-1")
    project = SimpleNamespace(owner_id="owner-1")

    service.get_run = AsyncMock(return_value=parent)
    service._child_runs_for_parent = AsyncMock(return_value=[child])
    service._emit_run_event = AsyncMock()
    service.db.commit = AsyncMock()
    service.db.refresh = AsyncMock()
    service.db.get = AsyncMock(return_value=project)

    with patch(
        "backend.modules.orchestration.execution.durable_execution.submit_orchestration_run"
    ) as submit:
        result = await service.resume_run(user, parent.id)

    assert result.status == "queued"
    assert child.status == "queued"
    submit.assert_called_once_with(parent.id, expected_owner_id="owner-1")


@pytest.mark.asyncio
async def test_retry_run_increments_counters_and_submits_new_run():
    service = _execution_service()
    old_run = _run(status="failed", retry_count=1, attempt_number=2)
    user = SimpleNamespace(id="user-1")
    project = SimpleNamespace(owner_id="owner-1")
    new_run = _run(run_id="run-2", status="queued", retry_count=2, attempt_number=3)
    task = SimpleNamespace(id="task-1", status="blocked")

    service.get_run = AsyncMock(return_value=old_run)
    service.db.get = AsyncMock(side_effect=lambda _model, _id: project if _id == "proj-1" else task)
    service._enforce_agent_token_budget = AsyncMock()
    service._enforce_agent_cost_budget = AsyncMock()
    service.repo.create_run = AsyncMock(return_value=new_run)
    service._transition_task_status = AsyncMock()
    service._emit_run_event = AsyncMock()
    service.db.commit = AsyncMock()
    service.db.refresh = AsyncMock()

    expected_retry, expected_attempt = next_retry_numbers(
        old_run.retry_count, old_run.attempt_number
    )

    with patch(
        "backend.modules.orchestration.execution.durable_execution.submit_orchestration_run"
    ) as submit:
        result = await service.retry_run(user, old_run.id)

    service.repo.create_run.assert_awaited_once()
    create_kwargs = service.repo.create_run.await_args.kwargs
    assert create_kwargs["retry_count"] == expected_retry
    assert create_kwargs["attempt_number"] == expected_attempt
    service._transition_task_status.assert_awaited_once_with(
        task, "queued", run=new_run, reason="retry queued"
    )
    submit.assert_called_once_with(new_run.id, expected_owner_id="owner-1")
    assert result.id == "run-2"


@pytest.mark.asyncio
async def test_get_task_execution_snapshot_schema_keys():
    service = _execution_service()
    user = SimpleNamespace(id="user-1")
    task = SimpleNamespace(
        id="task-1",
        project_id="proj-1",
        created_by_user_id="user-1",
        title="Snapshot task",
        status="in_progress",
        metadata_json={},
    )
    focal_run = _run(status="in_progress", run_id="run-focal")

    service.get_task = AsyncMock(return_value=task)
    service.repo.list_active_runs_for_task = AsyncMock(return_value=[focal_run])
    service.repo.list_pending_approvals_for_task = AsyncMock(return_value=[])
    service.repo.list_sync_events_for_task = AsyncMock(return_value=[])
    service.repo.list_run_events = AsyncMock(return_value=[])
    service.repo.get_latest_run_for_task = AsyncMock(return_value=focal_run)
    service._child_runs_for_parent = AsyncMock(return_value=[])
    service._check_task_acceptance_payload = AsyncMock(
        return_value={"passed": False, "checks": [], "config": {}}
    )
    service._changed_artifacts_payload = AsyncMock(return_value=[])
    service._routing_explainability_from_task_metadata = MagicMock(return_value={})

    snapshot = await service.get_task_execution_snapshot(user, "proj-1", "task-1")

    assert snapshot["meta"]["schema_version"] == EXECUTION_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["task_id"] == "task-1"
    assert snapshot["has_active_run"] is True
    assert "durable_workflow" in snapshot
    assert "acceptance_summary" in snapshot
    assert "recent_events_tail" in snapshot


TASK_EXECUTION_SNAPSHOT_GOLDEN_KEYS = {
    "meta",
    "project_id",
    "task_id",
    "task_status",
    "task_title",
    "has_active_run",
    "active_runs",
    "pending_approvals",
    "pending_github_sync",
    "metadata_views",
    "routing_explainability",
    "acceptance_summary",
    "execution_memory",
    "changed_artifacts",
    "last_run_id",
    "focal_run_id",
    "checkpoint_excerpt",
    "recent_events_tail",
    "trace",
    "durable_workflow",
    "child_runs",
    "blocker_queue",
    "review_state",
    "external_action_state",
    "github_action_state",
}


def test_task_execution_snapshot_golden_top_level_keys():
    """Lock snapshot contract — update intentionally when snapshot schema evolves."""
    assert len(TASK_EXECUTION_SNAPSHOT_GOLDEN_KEYS) == 25


@pytest.mark.asyncio
async def test_get_task_execution_snapshot_matches_golden_keys():
    service = _execution_service()
    user = SimpleNamespace(id="user-1")
    task = SimpleNamespace(
        id="task-1",
        project_id="proj-1",
        created_by_user_id="user-1",
        title="Snapshot task",
        status="in_progress",
        metadata_json={},
    )
    focal_run = _run(status="in_progress", run_id="run-focal")

    service.get_task = AsyncMock(return_value=task)
    service.repo.list_active_runs_for_task = AsyncMock(return_value=[focal_run])
    service.repo.list_pending_approvals_for_task = AsyncMock(return_value=[])
    service.repo.list_sync_events_for_task = AsyncMock(return_value=[])
    service.repo.list_run_events = AsyncMock(return_value=[])
    service.repo.get_latest_run_for_task = AsyncMock(return_value=focal_run)
    service._child_runs_for_parent = AsyncMock(return_value=[])
    service._check_task_acceptance_payload = AsyncMock(
        return_value={"passed": False, "checks": [], "config": {}}
    )
    service._changed_artifacts_payload = AsyncMock(return_value=[])
    service._routing_explainability_from_task_metadata = MagicMock(return_value={})

    snapshot = await service.get_task_execution_snapshot(user, "proj-1", "task-1")
    assert set(snapshot.keys()) == TASK_EXECUTION_SNAPSHOT_GOLDEN_KEYS


RUN_EXECUTION_SNAPSHOT_GOLDEN_KEYS = {
    "meta",
    "project_id",
    "run",
    "task_id",
    "pending_approvals",
    "pending_github_sync",
    "routing_explainability",
    "execution_memory",
    "changed_artifacts",
    "checkpoint_excerpt",
    "recent_events_tail",
    "trace",
    "durable_workflow",
    "child_runs",
    "blocker_queue",
    "review_state",
    "external_action_state",
    "github_action_state",
    "resumable",
}


def test_run_execution_snapshot_golden_top_level_keys():
    """Lock run-scoped snapshot contract — update intentionally when schema evolves."""
    assert len(RUN_EXECUTION_SNAPSHOT_GOLDEN_KEYS) == 19


@pytest.mark.asyncio
async def test_get_run_execution_snapshot_matches_golden_keys():
    service = _execution_service()
    user = SimpleNamespace(id="user-1")
    run = _run(status="in_progress", checkpoint_json=_failed_resumable_checkpoint())
    task = SimpleNamespace(id="task-1", metadata_json={})

    service.get_run = AsyncMock(return_value=run)
    service._child_runs_for_parent = AsyncMock(return_value=[])
    service.repo.list_pending_approvals_for_run = AsyncMock(return_value=[])
    service.repo.list_run_events = AsyncMock(return_value=[])
    service.repo.list_sync_events_for_task = AsyncMock(return_value=[])
    service.db.get = AsyncMock(return_value=task)
    service._changed_artifacts_payload = AsyncMock(return_value=[])
    service._routing_explainability_from_payload = MagicMock(return_value={})

    snapshot = await service.get_run_execution_snapshot(user, run.id)
    assert set(snapshot.keys()) == RUN_EXECUTION_SNAPSHOT_GOLDEN_KEYS
    assert snapshot["meta"]["schema_version"] == EXECUTION_SNAPSHOT_SCHEMA_VERSION
    assert snapshot["resumable"] is False
