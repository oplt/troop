"""Bounded query helpers and run-event tail utilities."""

from __future__ import annotations

from backend.core.config import settings
from backend.modules.orchestration._helpers import resolve_query_limit
from backend.modules.orchestration.execution.execution_service import OrchestrationExecutionServiceMixin


def test_run_event_query_settings_have_sensible_defaults():
    assert settings.RUN_EVENTS_DEFAULT_LIMIT >= 1
    assert settings.RUN_EVENTS_MAX_LIMIT >= settings.RUN_EVENTS_DEFAULT_LIMIT
    assert settings.RUN_EVENTS_REPLAY_MAX >= settings.RUN_EVENTS_DEFAULT_LIMIT
    assert settings.RUN_EVENTS_CLASSIFIER_MAX >= 1
    assert settings.RUN_EVENTS_EXPLAIN_MAX >= 1
    assert settings.RAG_CHUNK_FALLBACK_MAX == 200
    assert settings.AI_RETRIEVE_CHUNK_SCAN_MAX >= 1
    assert settings.ORCHESTRATION_LIST_TASKS_DEFAULT_LIMIT == 50
    assert settings.ORCHESTRATION_LIST_RUNS_DEFAULT_LIMIT >= 1
    assert settings.CURSOR_PAGE_DEFAULT_LIMIT == 50
    assert settings.CURSOR_PAGE_MAX_LIMIT == 100
    assert settings.ORCHESTRATION_LIST_DOCUMENTS_DEFAULT_LIMIT >= 1


def test_resolve_query_limit():
    assert resolve_query_limit(None, default=100, maximum=500) == 100
    assert resolve_query_limit(0, default=100, maximum=500) == 500
    assert resolve_query_limit(50, default=100, maximum=500) == 50
    assert resolve_query_limit(9999, default=100, maximum=500) == 500


def test_run_event_tail_payloads_respects_limit():
    class _Event:
        def __init__(self, idx: int):
            self.event_type = "log"
            self.level = "info"
            self.message = f"msg-{idx}"
            self.created_at = idx

    events = [_Event(i) for i in range(20)]
    mixin = OrchestrationExecutionServiceMixin()
    tail = mixin._run_event_tail_payloads(events, limit=8)
    assert len(tail) == 8
    assert tail[0]["message"] == "msg-12"
    assert tail[-1]["message"] == "msg-19"
