"""Tests for evaluation cases created from production traces (EVAL-001A)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.ai.evaluations.assertions import (
    derive_assertions_from_expected,
    evaluate_assertions,
    normalize_assertions,
)
from backend.modules.ai.evaluations.scoring import score_evaluation_case
from backend.modules.ai.evaluations.trace_case import (
    apply_correction,
    build_input_snapshot,
    build_provenance,
    redact_pii,
)
from backend.modules.orchestration.models import RunEvent
from backend.modules.orchestration.schemas.run_trace import (
    RunTraceRestrictedRef,
    RunTraceSpanKind,
    RunTraceSpanSafe,
)


def test_redact_pii_masks_email_and_secrets() -> None:
    payload = {
        "contact": "reach me at user@example.com",
        "arguments": {"token": "secret"},
    }
    redacted = redact_pii(payload)
    assert "[email redacted]" in redacted["contact"]
    assert redacted["arguments"] == "[restricted]"


def test_build_provenance_captures_model_and_skill_versions() -> None:
    run = SimpleNamespace(
        id="run-1",
        project_id="proj-1",
        task_id="task-1",
        run_mode="single_agent",
        status="completed",
        model_name="gpt-test",
        provider_config_id="provider-1",
        checkpoint_json={
            "skill_version_snapshot": {
                "skill_version_ids": ["skill-v1", "skill-v2"],
                "captured_at": "2026-01-01T00:00:00+00:00",
                "agent_id": "agent-1",
                "skills": [{"id": "s1"}],
            },
            "workflow_version_id": "wf-v3",
            "query_snapshot": {"objective": "Ship feature"},
        },
    )
    events = [
        RunEvent(
            id="evt-1",
            run_id="run-1",
            event_type="llm_response",
            message="done",
            payload_json={"prompt_version_id": "prompt-v9"},
            created_at=datetime(2026, 1, 1, tzinfo=UTC),
        )
    ]
    provenance = build_provenance(run, events=events, source_trace_span_id="evt:evt-1")
    assert provenance["model_name"] == "gpt-test"
    assert provenance["skill_version_ids"] == ["skill-v1", "skill-v2"]
    assert provenance["workflow_version_id"] == "wf-v3"
    assert provenance["prompt_version_id"] == "prompt-v9"
    assert provenance["source_trace_span_id"] == "evt:evt-1"


def test_apply_correction_derives_deterministic_assertions() -> None:
    resolved = apply_correction(
        {
            "expected_output_json": {"status": "completed", "summary": "Shipped"},
            "notes": "Human corrected summary",
        }
    )
    assert resolved["expected_output_json"]["summary"] == "Shipped"
    assert resolved["expected_assertions_json"]["mode"] == "deterministic"
    assert resolved["expected_assertions_json"]["rules"][0]["type"] == "json_equals"


def test_evaluate_assertions_supports_json_path_rules() -> None:
    assertions = normalize_assertions(
        {
            "mode": "deterministic",
            "rules": [
                {"type": "json_path_equals", "path": "status", "value": "completed"},
                {"type": "text_contains", "value": "done"},
            ],
        }
    )
    score, passed, notes = evaluate_assertions(
        output_text="All done",
        output_json={"status": "completed"},
        assertions=assertions,
    )
    assert passed is True
    assert score == 1.0
    assert "passed" in notes


def test_score_evaluation_case_prefers_assertions_over_legacy_json() -> None:
    case = SimpleNamespace(
        expected_assertions_json=derive_assertions_from_expected({"answer": 42}),
        expected_output_json={"answer": 99},
        expected_output_text=None,
    )
    score, passed, _notes = score_evaluation_case("ignored", {"answer": 42}, case)
    assert passed is True
    assert score == 1.0


def test_build_input_snapshot_includes_selected_span() -> None:
    run = SimpleNamespace(
        status="completed",
        input_payload_json={"prompt": "hello"},
        output_payload_json={"summary": "ok"},
    )
    spans = [
        RunTraceSpanSafe(
            id="evt:evt-1",
            run_id="run-1",
            kind=RunTraceSpanKind.MODEL_ATTEMPT,
            title="Model attempt",
            status="completed",
            message=None,
            started_at=datetime(2026, 1, 1, tzinfo=UTC),
            finished_at=datetime(2026, 1, 1, tzinfo=UTC),
            safe_payload={"model": "gpt-test"},
            restricted=RunTraceRestrictedRef(),
            source_event_id="evt-1",
            source_event_type="llm_response",
        )
    ]
    snapshot = build_input_snapshot(run, spans=spans, source_trace_span_id="evt:evt-1")
    assert snapshot["selected_span"]["id"] == "evt:evt-1"
    assert snapshot["input_payload"]["prompt"] == "[restricted]"


@pytest.mark.asyncio
async def test_create_case_from_trace_persists_redacted_case() -> None:
    from backend.modules.ai.evaluations.service import AiEvaluationsMixin

    run = SimpleNamespace(
        id="run-1",
        project_id="proj-1",
        task_id="task-1",
        run_mode="single_agent",
        status="completed",
        model_name="gpt-test",
        provider_config_id=None,
        checkpoint_json={"skill_version_snapshot": {"skill_version_ids": ["skill-v1"]}},
        input_payload_json={"objective": "test"},
        output_payload_json={"summary": "before correction"},
    )
    span = RunTraceSpanSafe(
        id="evt:evt-1",
        run_id="run-1",
        kind=RunTraceSpanKind.TOOL_EFFECT,
        title="Tool effect",
        status="completed",
        message=None,
        started_at=datetime(2026, 1, 1, tzinfo=UTC),
        finished_at=datetime(2026, 1, 1, tzinfo=UTC),
        safe_payload={"tool": "fs_write"},
        restricted=RunTraceRestrictedRef(),
        source_event_id="evt-1",
        source_event_type="tool_call_completed",
    )

    service = AiEvaluationsMixin()
    service.db = AsyncMock()
    service.repo = AsyncMock()
    service.repo.get_dataset_for_user = AsyncMock(return_value=SimpleNamespace(id="dataset-1"))
    created_case = SimpleNamespace(id="case-1")
    service.repo.create_dataset_case = AsyncMock(return_value=created_case)

    orch_repo = AsyncMock()
    orch_repo.get_run = AsyncMock(return_value=run)
    orch_repo.list_run_events = AsyncMock(return_value=[])

    trace_service = AsyncMock()
    trace_service.list_run_trace_spans = AsyncMock(
        return_value=SimpleNamespace(items=[span], meta=SimpleNamespace())
    )

    user = SimpleNamespace(id="user-1")

    with (
        patch(
            "backend.modules.ai.evaluations.service.OrchestrationRepository",
            return_value=orch_repo,
        ),
        patch(
            "backend.modules.ai.evaluations.service.RunTraceService",
            return_value=trace_service,
        ),
    ):
        result = await service.create_case_from_trace(
            user,
            "dataset-1",
            {
                "run_id": "run-1",
                "source_trace_span_id": "evt:evt-1",
                "correction": {
                    "expected_output_json": {"summary": "after correction"},
                    "notes": "Reviewer fix",
                },
            },
        )

    assert result is created_case
    kwargs = service.repo.create_dataset_case.await_args.kwargs
    assert kwargs["source_run_id"] == "run-1"
    assert kwargs["provenance_json"]["model_name"] == "gpt-test"
    assert kwargs["expected_assertions_json"]["rules"][0]["type"] == "json_equals"
    service.db.commit.assert_awaited_once()
