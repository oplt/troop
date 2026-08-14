"""Tests for thin list DTO payload reduction (DATA-001B)."""

from __future__ import annotations

import json
from datetime import UTC, datetime
from types import SimpleNamespace

from backend.modules.notifications.schemas import NotificationResponse
from backend.modules.orchestration.presenters import (
    to_approval_list_item,
    to_event_list_item,
    to_notification_list_item,
    to_run_list_item,
    to_task_list_item,
)
from backend.modules.orchestration.schemas import (
    ApprovalResponse,
    RunEventResponse,
    TaskRunListItem,
    TaskRunResponse,
)


def _json_bytes(model) -> int:
    return len(json.dumps(model.model_dump(mode="json")).encode("utf-8"))


def test_task_run_list_item_omits_large_payload_fields() -> None:
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id="run-1",
        parent_run_id=None,
        project_id="proj-1",
        task_id="task-1",
        run_mode="single_agent",
        status="completed",
        model_name="gpt-4",
        attempt_number=1,
        token_input=100,
        token_output=200,
        token_total=300,
        estimated_cost_micros=5000,
        latency_ms=1200,
        error_message=None,
        retry_count=0,
        created_at=now,
        started_at=now,
        completed_at=now,
        cancelled_at=None,
    )
    full = to_run_list_item(row)
    assert "checkpoint_json" not in full.model_fields
    assert "input_payload" not in full.model_fields
    assert "output_payload" not in full.model_fields

    full_response = TaskRunResponse(
        id=row.id,
        parent_run_id=None,
        project_id=row.project_id,
        task_id=row.task_id,
        triggered_by_user_id=None,
        orchestrator_agent_id=None,
        worker_agent_id=None,
        reviewer_agent_id=None,
        provider_config_id=None,
        brainstorm_id=None,
        run_mode=row.run_mode,
        status=row.status,
        model_name=row.model_name,
        attempt_number=row.attempt_number,
        token_input=row.token_input,
        token_output=row.token_output,
        token_total=row.token_total,
        estimated_cost_micros=row.estimated_cost_micros,
        latency_ms=row.latency_ms,
        error_message=row.error_message,
        retry_count=row.retry_count,
        checkpoint_json={"steps": ["x" * 5000]},
        input_payload={"prompt": "y" * 8000},
        output_payload={"result": "z" * 12000},
        created_at=now,
        started_at=now,
        completed_at=now,
        cancelled_at=None,
    )
    list_item = TaskRunListItem.model_validate(
        {k: v for k, v in full_response.model_dump().items() if k in TaskRunListItem.model_fields}
    )
    assert _json_bytes(list_item) < _json_bytes(full_response) * 0.2


def test_run_event_list_item_drops_payload() -> None:
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id="evt-1",
        run_id="run-1",
        task_id=None,
        level="info",
        event_type="tool_output",
        message="ok",
        payload_json={"tool_output": "x" * 10000},
        input_tokens=1,
        output_tokens=2,
        cost_usd_micros=3,
        created_at=now,
    )
    item = to_event_list_item(row)
    assert "payload" not in item.model_fields
    full = RunEventResponse(
        id=row.id,
        run_id=row.run_id,
        task_id=row.task_id,
        level=row.level,
        event_type=row.event_type,
        message=row.message,
        payload=row.payload_json,
        input_tokens=1,
        output_tokens=2,
        cost_usd_micros=3,
        created_at=now,
    )
    assert _json_bytes(item) < _json_bytes(full) * 0.05


def test_task_list_item_omits_metadata_and_result_payload() -> None:
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id="task-1",
        project_id="proj-1",
        title="Ship feature",
        status="in_progress",
        priority="high",
        task_type="general",
        position=1,
        assigned_agent_id=None,
        human_assignee_id=None,
        parent_task_id=None,
        due_date=None,
        labels_json=["backend"],
        result_summary="done",
        created_at=now,
        updated_at=now,
    )
    item = to_task_list_item(row, dependency_ids=["dep-1"])
    assert item.has_result is True
    assert "metadata" not in item.model_fields
    assert "result_payload" not in item.model_fields


def test_approval_list_item_omits_effect_payload() -> None:
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id="appr-1",
        project_id="proj-1",
        task_id="task-1",
        run_id="run-1",
        issue_link_id=None,
        approval_type="gmail_send",
        status="pending",
        reason="Please review",
        effect_hash="abc",
        effect_version=2,
        expires_at=now,
        created_at=now,
        resolved_at=None,
    )
    item = to_approval_list_item(row)
    assert "payload" not in item.model_fields
    assert "proposed_effect" not in item.model_fields
    full = ApprovalResponse(
        id=row.id,
        project_id=row.project_id,
        task_id=row.task_id,
        run_id=row.run_id,
        issue_link_id=row.issue_link_id,
        requested_by_user_id="user-1",
        approved_by_user_id=None,
        approval_type=row.approval_type,
        status=row.status,
        reason=row.reason,
        payload={"draft": "x" * 5000},
        effect_hash=row.effect_hash,
        effect_version=row.effect_version,
        proposed_effect={"body": "y" * 8000},
        created_at=now,
        resolved_at=None,
    )
    assert _json_bytes(item) < _json_bytes(full) * 0.05


def test_notification_list_item_truncates_body() -> None:
    now = datetime.now(UTC)
    row = SimpleNamespace(
        id="n-1",
        type="system",
        title="Hello",
        body="word " * 200,
        is_read=False,
        created_at=now,
    )
    item = to_notification_list_item(row)
    full = NotificationResponse(
        id=row.id,
        type=row.type,
        title=row.title,
        body=row.body,
        is_read=row.is_read,
        created_at=now,
    )
    assert item.body_preview is not None
    assert len(item.body_preview) < len(full.body or "")
    assert _json_bytes(item) < _json_bytes(full)
