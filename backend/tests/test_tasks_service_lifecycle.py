"""Phase 0 — characterization tests for task acceptance and update_task gates."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin


class _TasksHost(OrchestrationTasksServiceMixin):
    def __init__(self) -> None:
        self.db = MagicMock()
        self.repo = MagicMock()
        self.repo.list_task_artifacts = AsyncMock(return_value=[])
        self.repo.list_sync_events_for_task = AsyncMock(return_value=[])


def _task(**overrides) -> SimpleNamespace:
    base = {
        "id": "task-1",
        "project_id": "proj-1",
        "created_by_user_id": "user-1",
        "status": "needs_review",
        "acceptance_criteria": "- Include unit tests\n- Document API changes",
        "result_summary": "Implemented API changes with unit tests and documentation.",
        "result_payload_json": {"summary": "done"},
        "metadata_json": {},
        "assigned_agent_id": None,
        "github_issue_link_id": None,
    }
    base.update(overrides)
    return SimpleNamespace(**base)


def test_acceptance_criteria_items_parses_bullets_and_numbered_lines():
    host = _TasksHost()
    items = host._acceptance_criteria_items("- first item\n2. second item\n\n")
    assert items == ["first item", "second item"]


def test_acceptance_item_check_requires_token_overlap():
    host = _TasksHost()
    passed = host._acceptance_item_check(
        "Include unit tests",
        "Implemented API changes with unit tests and documentation.",
    )
    failed = host._acceptance_item_check(
        "Deploy to production cluster",
        "Implemented API changes with unit tests and documentation.",
    )
    assert passed["passed"] is True
    assert failed["passed"] is False


def test_task_output_text_combines_summary_and_payload():
    host = _TasksHost()
    text = host._task_output_text(
        _task(result_summary="Summary line", result_payload_json={"detail": "payload"})
    )
    assert "Summary line" in text
    assert "payload" in text


@pytest.mark.asyncio
async def test_check_task_acceptance_payload_fails_without_output():
    host = _TasksHost()
    host.repo.list_task_dependencies_for_task = AsyncMock(return_value=[])

    result = await host._check_task_acceptance_payload(
        _task(status="in_progress", result_summary="", result_payload_json={})
    )

    assert result["passed"] is False
    check_names = {item["name"] for item in result["checks"]}
    assert "has_output" in check_names
    assert "valid_status" in check_names


@pytest.mark.asyncio
async def test_check_task_acceptance_payload_passes_with_output_and_criteria():
    host = _TasksHost()
    host.repo.list_task_dependencies_for_task = AsyncMock(return_value=[])

    result = await host._check_task_acceptance_payload(_task(status="completed"))

    criteria = next(item for item in result["checks"] if item["name"] == "acceptance_criteria")
    assert criteria["passed"] is True
    assert result["passed"] is True


@pytest.mark.asyncio
async def test_update_task_blocks_completion_when_acceptance_fails():
    host = _TasksHost()
    task = _task(status="in_progress", result_summary="", result_payload_json={})
    project = SimpleNamespace(id="proj-1", settings_json={})
    user = SimpleNamespace(id="user-1")

    host.get_task = AsyncMock(return_value=task)
    host.get_project = AsyncMock(return_value=project)
    host.db.get = AsyncMock(return_value=project)
    host.action_requires_approval = MagicMock(return_value=False)
    host._check_task_acceptance_payload = AsyncMock(
        return_value={"passed": False, "checks": [{"name": "has_output", "passed": False}]}
    )
    host._transition_task_status = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await host.update_task(user, "proj-1", "task-1", {"status": "completed"})

    assert exc.value.status_code == 409
    assert "Acceptance checks must pass" in str(exc.value.detail)
    host._transition_task_status.assert_not_awaited()


@pytest.mark.asyncio
async def test_update_task_creates_mark_complete_approval_when_gated():
    host = _TasksHost()
    task = _task(status="in_progress")
    project = SimpleNamespace(id="proj-1", settings_json={})
    user = SimpleNamespace(id="user-1")
    approval = SimpleNamespace(id="appr-complete")

    host.get_task = AsyncMock(return_value=task)
    host.get_project = AsyncMock(return_value=project)
    host.db.get = AsyncMock(return_value=project)
    host.action_requires_approval = MagicMock(
        side_effect=lambda _project, action: action == "mark_complete"
    )
    host.repo.create_approval = AsyncMock(return_value=approval)
    host.db.commit = AsyncMock()

    with pytest.raises(HTTPException) as exc:
        await host.update_task(user, "proj-1", "task-1", {"status": "completed"})

    assert exc.value.status_code == 409
    assert exc.value.detail["approval_id"] == "appr-complete"
    host.repo.create_approval.assert_awaited_once()


@pytest.mark.asyncio
async def test_update_task_clears_memory_checkpoint_on_reopen_from_terminal():
    host = _TasksHost()
    task = _task(
        status="completed",
        metadata_json={"memory_checkpoint_compacted": True, "memory_low_value_archived": True},
    )
    project = SimpleNamespace(id="proj-1", settings_json={})
    user = SimpleNamespace(id="user-1")

    host.get_task = AsyncMock(return_value=task)
    host.get_project = AsyncMock(return_value=project)
    host.db.get = AsyncMock(return_value=project)
    host.action_requires_approval = MagicMock(return_value=False)
    host._transition_task_status = AsyncMock()
    host._check_task_acceptance_payload = AsyncMock(return_value={"passed": True, "checks": []})
    host._queue_task_github_sync_from_internal_changes = AsyncMock()
    host._sync_knowledge_graph_for_task = AsyncMock()
    host.db.commit = AsyncMock()
    host.db.refresh = AsyncMock()

    with patch("backend.modules.projects.tasks.crud.orm_attributes.flag_modified"):
        await host.update_task(user, "proj-1", "task-1", {"status": "in_progress"})

    assert "memory_checkpoint_compacted" not in task.metadata_json
    assert "memory_low_value_archived" not in task.metadata_json
    host._transition_task_status.assert_awaited_once_with(
        task, "in_progress", reason="manual update"
    )
