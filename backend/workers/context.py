"""Celery context propagation for request/job/run correlation."""

from __future__ import annotations

from contextlib import AbstractContextManager
from typing import Any

from celery.signals import task_postrun, task_prerun

from backend.core.request_context import (
    bind_context,
    context_from_headers,
    get_request_context,
)

_active_contexts: dict[str, AbstractContextManager[Any]] = {}
_registered = False


def task_context_headers() -> dict[str, str]:
    """Return the allowlisted current context for Celery message headers."""
    from backend.modules.observability.tracing import bind_active_trace_context

    bind_active_trace_context()
    return get_request_context().as_task_headers()


def _bind_task_context(task_id: str | None, task: Any, **_: Any) -> None:
    if not task_id:
        return
    headers = getattr(getattr(task, "request", None), "headers", None) or {}
    values = context_from_headers(headers)
    values.update(
        {
            "job_id": task_id,
            "task_name": getattr(task, "name", None),
        }
    )
    context = bind_context(**values)
    context.__enter__()
    _active_contexts[task_id] = context


def _restore_task_context(task_id: str | None, **_: Any) -> None:
    if not task_id:
        return
    context = _active_contexts.pop(task_id, None)
    if context is not None:
        context.__exit__(None, None, None)


def register_task_context_signals() -> None:
    """Register signals once per worker process/import context."""
    global _registered
    if _registered:
        return
    task_prerun.connect(
        _bind_task_context,
        weak=False,
        dispatch_uid="troop.bind_task_context",
    )
    task_postrun.connect(
        _restore_task_context,
        weak=False,
        dispatch_uid="troop.restore_task_context",
    )
    _registered = True


__all__ = ["register_task_context_signals", "task_context_headers"]
