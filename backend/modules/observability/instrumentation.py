"""Lifecycle registration for database and Celery golden signals."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from backend.core.config import settings
from backend.modules.observability.config import ObservabilityConfig
from backend.modules.observability.metrics import (
    WORKER_ACTIVE,
    metrics_registry,
    record_db_query,
    record_worker_task,
)
from backend.modules.observability.tracing import setup_sentry, setup_tracing

_database_instrumented = False
_worker_signals_registered = False
_task_started: dict[str, float] = {}


def instrument_database(engine: Any) -> None:
    global _database_instrumented
    if _database_instrumented:
        return
    from sqlalchemy import event

    def operation(statement: str) -> str:
        return str(statement).lstrip().split(maxsplit=1)[0].lower()[:16] or "unknown"

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def before_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        context._troop_started_at = perf_counter()
        context._troop_operation = operation(statement)

    @event.listens_for(engine.sync_engine, "after_cursor_execute")
    def after_cursor_execute(
        conn: Any,
        cursor: Any,
        statement: str,
        parameters: Any,
        context: Any,
        executemany: bool,
    ) -> None:
        started = getattr(context, "_troop_started_at", None)
        if started is not None:
            record_db_query(
                getattr(context, "_troop_operation", "unknown"),
                "success",
                perf_counter() - started,
            )

    @event.listens_for(engine.sync_engine, "handle_error")
    def handle_error(exception_context: Any) -> None:
        context = exception_context.execution_context
        started = getattr(context, "_troop_started_at", None)
        if started is not None:
            record_db_query(
                getattr(context, "_troop_operation", "unknown"),
                "error",
                perf_counter() - started,
            )

    _database_instrumented = True


def register_worker_observability_signals() -> None:
    global _worker_signals_registered
    if _worker_signals_registered:
        return
    from celery.signals import task_postrun, task_prerun

    def task_name(task: Any) -> str:
        return str(getattr(task, "name", "unknown")).rsplit(".", 1)[-1][:64]

    def on_prerun(task_id: str | None = None, task: Any = None, **_: Any) -> None:
        if task_id:
            _task_started[task_id] = perf_counter()
        metrics_registry.increment_gauge(
            WORKER_ACTIVE,
            help_text="Currently active Celery tasks.",
            labels={},
        )

    def on_postrun(
        task_id: str | None = None,
        task: Any = None,
        state: str | None = None,
        **_: Any,
    ) -> None:
        started = _task_started.pop(task_id or "", perf_counter())
        record_worker_task(task_name(task), (state or "unknown").lower(), perf_counter() - started)
        metrics_registry.increment_gauge(
            WORKER_ACTIVE,
            help_text="Currently active Celery tasks.",
            labels={},
            delta=-1,
        )

    task_prerun.connect(on_prerun, weak=False, dispatch_uid="troop.observability.task_prerun")
    task_postrun.connect(on_postrun, weak=False, dispatch_uid="troop.observability.task_postrun")
    _worker_signals_registered = True


def setup_observability(app: Any = None) -> None:
    config = ObservabilityConfig.from_settings()
    if not config.enabled:
        return
    from backend.db.session import engine

    instrument_database(engine)
    register_worker_observability_signals()
    setup_sentry(settings.SENTRY_DSN, settings.APP_ENV, settings.SENTRY_TRACES_SAMPLE_RATE)
    setup_tracing(settings.OTLP_ENDPOINT, settings.APP_NAME, settings.OTLP_INSECURE, app)


__all__ = [
    "instrument_database",
    "register_worker_observability_signals",
    "setup_observability",
]
