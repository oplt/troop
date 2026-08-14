"""P5.7 tracing completeness smoke tests."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.core.request_context import bind_context, get_request_context
from backend.modules.observability.tracing import (
    bind_active_trace_context,
    celery_task_span,
    current_trace_context,
    enrich_with_trace_context,
    llm_invoke_span,
    record_llm_span_result,
)


def test_current_trace_context_without_otel_is_empty():
    assert current_trace_context() == {"trace_id": None, "span_id": None}


def test_enrich_with_trace_context_is_noop_without_span():
    payload = enrich_with_trace_context({"event": "test"})
    assert payload == {"event": "test"}


def test_enrich_with_trace_context_adds_ids_when_present():
    with patch(
        "backend.modules.observability.tracing.current_trace_context",
        return_value={"trace_id": "abc123", "span_id": "def456"},
    ):
        payload = enrich_with_trace_context({"event": "test"})
    assert payload["trace_id"] == "abc123"
    assert payload["span_id"] == "def456"


def test_bind_active_trace_context_sets_request_context():
    with patch(
        "backend.modules.observability.tracing.current_trace_context",
        return_value={"trace_id": "trace-1", "span_id": "span-1"},
    ):
        with bind_context():
            bind_active_trace_context()
            ctx = get_request_context()
    assert ctx.trace_id == "trace-1"
    assert ctx.span_id == "span-1"


def test_celery_and_llm_spans_do_not_raise_without_exporter():
    with celery_task_span("run_task", task_id="job-1"):
        pass
    with llm_invoke_span(purpose="plan", provider="ollama", model="llama3"):
        pass


def test_record_llm_span_result_tolerates_none_span():
    record_llm_span_result(None, input_tokens=1, output_tokens=2, result="success")


def test_record_llm_span_result_sets_attributes():
    span = MagicMock()
    record_llm_span_result(span, input_tokens=10, output_tokens=5, result="success")
    span.set_attribute.assert_any_call("llm.input_tokens", 10)
    span.set_attribute.assert_any_call("llm.output_tokens", 5)


@pytest.mark.asyncio
async def test_execute_prompt_wraps_llm_span(monkeypatch):
    from backend.modules.orchestration.providers import ProviderExecutionResult, execute_prompt

    stub = ProviderExecutionResult(
        model_name="gpt-test",
        output_text="ok",
        output_json=None,
        input_tokens=3,
        output_tokens=2,
        latency_ms=5,
    )

    monkeypatch.setattr(
        "backend.modules.orchestration.providers._execute_prompt_impl",
        AsyncMock(return_value=stub),
    )

    with patch("backend.modules.orchestration.providers.llm_invoke_span") as llm_span:
        cm = MagicMock()
        cm.__enter__ = MagicMock(return_value=MagicMock())
        cm.__exit__ = MagicMock(return_value=False)
        llm_span.return_value = cm
        await execute_prompt(
            None,
            model_name="local-heuristic",
            system_prompt="s",
            user_prompt="u",
            purpose="health_probe",
            record_metrics=False,
        )
        llm_span.assert_called_once()
        assert llm_span.call_args.kwargs["purpose"] == "health_probe"
