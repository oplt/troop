"""Phase 0 — manager-worker execution flow characterization."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.modules.orchestration.execution.execution_service import (
    OrchestrationExecutionServiceMixin,
)
from backend.modules.orchestration.execution.execution_workflow import (
    ensure_workflow_state,
    get_workflow_artifact,
    set_workflow_artifact,
)


class _StopAfterPlanCheckpoint(Exception):
    pass


class _StopAfterRoutingCheckpoint(Exception):
    pass


def _execution_service(**overrides) -> OrchestrationExecutionServiceMixin:
    service = OrchestrationExecutionServiceMixin()
    service.db = MagicMock()
    service.repo = MagicMock()
    for key, value in overrides.items():
        setattr(service, key, value)
    return service


def _run(*, checkpoint_json: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(
        id="run-1",
        status="in_progress",
        run_mode="manager_worker",
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
        attempt_number=1,
        retry_count=0,
        input_payload_json={},
        output_payload_json={},
        error_message=None,
        started_at=datetime.now(UTC),
        created_at=datetime.now(UTC),
        completed_at=None,
        cancelled_at=None,
        checkpoint_json=checkpoint_json or {},
    )


@pytest.mark.asyncio
async def test_manager_worker_run_persists_plan_checkpoint_before_routing():
    service = _execution_service()
    run = _run(
        checkpoint_json=ensure_workflow_state(
            {},
            run_mode="manager_worker",
            steps=[
                {"id": "planning", "title": "Planning", "actor": "supervisor"},
                {"id": "subtask_dispatch", "title": "Dispatch", "actor": "supervisor"},
                {"id": "worker_execution", "title": "Workers", "actor": "worker"},
            ],
            run_id="run-1",
        ),
    )
    manager = SimpleNamespace(id="agent-mgr", system_prompt="Manage work")
    worker = SimpleNamespace(id="agent-worker", system_prompt="Execute work")
    task = SimpleNamespace(
        id="task-1",
        title="Ship feature",
        description="Implement and test",
        acceptance_criteria="Tests pass",
        metadata_json={},
    )
    project = SimpleNamespace(id="proj-1", owner_id="user-1", settings_json={})

    service._load_agent_for_run = AsyncMock(side_effect=[manager, worker])
    service._resolve_provider_for_run = AsyncMock(return_value=SimpleNamespace(id="prov-1"))
    service.db.get = AsyncMock(side_effect=lambda _model, entity_id: task if entity_id == "task-1" else project)
    service._delegation_edge_allowed = MagicMock(return_value=True)
    service._emit_run_event = AsyncMock()
    service._mark_run_step = AsyncMock()
    service._build_task_prompt = AsyncMock(return_value="plan prompt")
    service._plan_agent_execution = AsyncMock(
        return_value={"sub_tasks": [{"title": "Implement", "parallelizable": False}]},
    )

    original_set = service._set_workflow_checkpoint_artifact

    def _stop_after_plan_checkpoint(run_obj, *, key: str, value):
        original_set(run_obj, key=key, value=value)
        if key == "manager_worker.plan":
            raise _StopAfterPlanCheckpoint()

    service._set_workflow_checkpoint_artifact = _stop_after_plan_checkpoint

    with pytest.raises(_StopAfterPlanCheckpoint):
        await service._execute_manager_worker_run(run)

    service._plan_agent_execution.assert_awaited_once()
    plan = get_workflow_artifact(run.checkpoint_json, "manager_worker.plan")
    assert plan is not None
    assert plan.get("sub_tasks")


@pytest.mark.asyncio
async def test_manager_worker_run_routes_subtasks_to_workers():
    service = _execution_service()
    checkpoint = ensure_workflow_state(
        {},
        run_mode="manager_worker",
        steps=[
            {"id": "planning", "title": "Planning", "actor": "supervisor"},
            {"id": "subtask_dispatch", "title": "Dispatch", "actor": "supervisor"},
            {"id": "worker_execution", "title": "Workers", "actor": "worker"},
        ],
        run_id="run-1",
    )
    checkpoint = set_workflow_artifact(
        checkpoint,
        key="manager_worker.plan",
        value={"sub_tasks": [{"title": "Implement API", "parallelizable": False}]},
    )
    run = _run(checkpoint_json=checkpoint)
    manager = SimpleNamespace(id="agent-mgr", system_prompt="Manage work")
    worker = SimpleNamespace(id="agent-worker", system_prompt="Execute work")
    task = SimpleNamespace(
        id="task-1",
        title="Ship feature",
        description="Implement and test",
        acceptance_criteria="Tests pass",
        metadata_json={},
    )
    project = SimpleNamespace(id="proj-1", owner_id="user-1", settings_json={})
    routed_sub_tasks = [
        {
            "branch_id": "branch-1",
            "title": "Implement API",
            "assigned_agent_id": "agent-worker",
            "dependency_ids": [],
            "parallelizable": False,
        }
    ]

    service._load_agent_for_run = AsyncMock(side_effect=[manager, worker])
    service._resolve_provider_for_run = AsyncMock(return_value=SimpleNamespace(id="prov-1"))
    service.db.get = AsyncMock(side_effect=lambda _model, entity_id: task if entity_id == "task-1" else project)
    service._delegation_edge_allowed = MagicMock(return_value=True)
    service._emit_run_event = AsyncMock()
    service._mark_run_step = AsyncMock()
    service._candidate_workers = AsyncMock(return_value=[worker])
    service._route_sub_tasks_to_agents = AsyncMock(return_value=routed_sub_tasks)

    original_set = service._set_workflow_checkpoint_artifact

    def _stop_after_routing_checkpoint(run_obj, *, key: str, value):
        original_set(run_obj, key=key, value=value)
        if key == "manager_worker.routed_sub_tasks":
            raise _StopAfterRoutingCheckpoint()

    service._set_workflow_checkpoint_artifact = _stop_after_routing_checkpoint

    with pytest.raises(_StopAfterRoutingCheckpoint):
        await service._execute_manager_worker_run(run)

    service._route_sub_tasks_to_agents.assert_awaited_once()
    route_kwargs = service._route_sub_tasks_to_agents.await_args.kwargs
    assert route_kwargs["manager"] is manager
    assert route_kwargs["parent_task"] is task
    routed = get_workflow_artifact(run.checkpoint_json, "manager_worker.routed_sub_tasks")
    assert routed == routed_sub_tasks
    assert routed[0]["assigned_agent_id"] == "agent-worker"
