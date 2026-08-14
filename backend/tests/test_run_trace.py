"""Tests for safe run-trace projection (OBS-002A)."""

from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from backend.core.pagination import simulate_desc_time_id_pages
from backend.modules.orchestration.execution.run_trace import (
    RunTraceService,
    _event_to_span,
)
from backend.modules.orchestration.execution.run_trace_redaction import build_safe_payload
from backend.modules.orchestration.models import RunEvent
from backend.modules.orchestration.schemas.run_trace import RunTraceSpanKind


def test_build_safe_payload_redacts_sensitive_keys() -> None:
    safe, restricted = build_safe_payload(
        {
            "tool": "gmail.send_draft",
            "arguments": {"access_token": "secret"},
            "result_preview": "ok",
        },
        event_type="tool_call_completed",
    )
    assert safe["arguments"] == "[restricted]"
    assert restricted.has_restricted is True
    assert "arguments" in restricted.restricted_fields


def test_event_to_span_maps_tool_lifecycle() -> None:
    started = RunEvent(
        id="evt-1",
        run_id="run-1",
        event_type="tool_call_started",
        message="Executing tool web_search.",
        payload_json={"tool": "web_search", "index": 0},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    span = _event_to_span("run-1", started)
    assert span is not None
    assert span.kind == RunTraceSpanKind.TOOL_AUTH
    assert span.id == "evt:evt-1"


def test_event_to_span_maps_model_attempt() -> None:
    event = RunEvent(
        id="evt-2",
        run_id="run-1",
        event_type="llm_response",
        message="Model responded.",
        payload_json={"model": "gpt-4.1", "result_preview": "{}"},
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
    )
    span = _event_to_span("run-1", event)
    assert span is not None
    assert span.kind == RunTraceSpanKind.MODEL_ATTEMPT
    assert span.status == "completed"


@pytest.mark.asyncio
async def test_list_run_trace_spans_returns_cursor_page() -> None:
    db = AsyncMock()
    repo = AsyncMock()
    repo.list_approvals_for_run = AsyncMock(return_value=[])
    repo.list_run_events = AsyncMock(
        side_effect=[
            [
                RunEvent(
                    id="e1",
                    run_id="run-1",
                    event_type="started",
                    message="Run started",
                    payload_json={},
                    created_at=datetime(2026, 1, 1, tzinfo=UTC),
                ),
                RunEvent(
                    id="e2",
                    run_id="run-1",
                    event_type="tool_call_started",
                    message="tool",
                    payload_json={"tool": "web_search"},
                    created_at=datetime(2026, 1, 1, 0, 1, tzinfo=UTC),
                ),
            ],
            [],
        ]
    )

    run = SimpleNamespace(
        id="run-1",
        created_at=datetime(2026, 1, 1, tzinfo=UTC),
        checkpoint_json={},
    )

    service = RunTraceService(db)
    service.repo = repo

    page = await service.list_run_trace_spans(run, limit=10)
    assert len(page.items) >= 2
    assert page.meta.run_id == "run-1"
    assert "trigger" in page.meta.span_kinds_present


def test_cursor_pagination_has_no_duplicates_on_simulated_rows() -> None:
    rows = [
        (datetime(2026, 1, 1, 0, 0, tzinfo=UTC), "a"),
        (datetime(2026, 1, 1, 0, 1, tzinfo=UTC), "b"),
        (datetime(2026, 1, 1, 0, 2, tzinfo=UTC), "c"),
    ]
    pages = simulate_desc_time_id_pages(rows, limit=2)
    flattened = [item for page in pages for item in page]
    assert len(flattened) == len(set(flattened))
