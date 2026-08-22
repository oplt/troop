from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest
from backend.modules.orchestration.models import TaskRun
from backend.modules.orchestration.services.planned_runs import PlannedRunService
from backend.modules.orchestration.workspace.storage import StoredWorkspaceFile
from backend.modules.projects.orchestration_models import OrchestratorTask


def _run(*, status: str) -> TaskRun:
    return TaskRun(
        id="run-1",
        project_id="project-1",
        task_id="task-1",
        triggered_by_user_id="user-1",
        run_mode="planned_placeholder",
        status=status,
        checkpoint_json={},
        input_payload_json={},
        output_payload_json={},
    )


def _service() -> tuple[PlannedRunService, AsyncMock, SimpleNamespace, SimpleNamespace]:
    db = AsyncMock()
    service = PlannedRunService(db)
    repo = SimpleNamespace(
        get_task_by_id=AsyncMock(),
        create_run=AsyncMock(),
        create_run_event=AsyncMock(),
        get_run=AsyncMock(),
        get_run_for_worker=AsyncMock(),
        create_task_artifact=AsyncMock(),
        list_run_events=AsyncMock(return_value=[]),
        list_run_artifacts=AsyncMock(return_value=[]),
    )
    orchestration = SimpleNamespace(get_project=AsyncMock())
    workspace = SimpleNamespace(
        write_artifact=AsyncMock(),
        list_files=AsyncMock(return_value=[]),
    )
    service.repo = repo
    service.orchestration = orchestration
    service.workspace = workspace
    return service, db, repo, workspace


@pytest.mark.asyncio
async def test_create_planned_run_persists_plan_and_event() -> None:
    service, db, repo, _workspace = _service()
    task = OrchestratorTask(
        id="task-1",
        project_id="project-1",
        title="Design the runtime",
        assigned_agent_id="agent-1",
    )
    run = _run(status="awaiting_approval")
    repo.get_task_by_id.return_value = task
    repo.create_run.return_value = run
    service.orchestration.get_project.return_value = SimpleNamespace(company_id="company-1")
    user = SimpleNamespace(id="user-1")

    created = await service.create_planned_run(user, task.id, {})

    assert created.status == "awaiting_approval"
    assert [step["id"] for step in created.output_payload_json["plan"]] == [
        "understand_task",
        "gather_context",
        "draft_output",
    ]
    repo.create_run_event.assert_awaited_once()
    db.commit.assert_awaited_once()


@pytest.mark.asyncio
async def test_approve_plan_creates_workspace_and_artifact_metadata() -> None:
    service, db, repo, workspace = _service()
    run = _run(status="awaiting_approval")
    run.output_payload_json = {
        "plan": [{"id": "draft", "title": "Draft output", "status": "pending"}]
    }
    repo.get_run.return_value = run
    repo.get_run_for_worker.return_value = run
    workspace.write_artifact.return_value = StoredWorkspaceFile(
        name="final-output.md",
        path="final-output.md",
        size_bytes=10,
        location="/tmp/workspace/final-output.md",
    )
    user = SimpleNamespace(id="user-1")

    approved = await service.approve_plan(user, run.id)

    assert approved.status == "completed"
    assert approved.completed_at is not None
    workspace.write_artifact.assert_awaited_once()
    repo.create_task_artifact.assert_awaited_once_with(
        task_id="task-1",
        run_id="run-1",
        kind="final_output",
        title="final-output.md",
        content=approved.output_payload_json["final_output"],
        metadata_json={
            "path_or_url": "/tmp/workspace/final-output.md",
            "workspace_file": "final-output.md",
        },
    )
    assert repo.create_run_event.await_count == 4
    db.commit.assert_awaited_once()
