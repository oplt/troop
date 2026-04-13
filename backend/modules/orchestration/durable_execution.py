"""Durable orchestration enqueueing (control plane).

**Today:** Celery + Redis broker deliver at-least-once execution of ``run_orchestration_task``
(see ``backend/workers/orchestration.py`` and ADR 0002).

**Future:** A Temporal (or similar) backend can implement the same contract for cross-process
replay, signals, and long-lived workflow state without changing API callers (ADR 0004).

Callers should use :func:`submit_orchestration_run` instead of importing Celery tasks directly
so the enqueue path stays centralized.
"""

from __future__ import annotations


def submit_orchestration_run(run_id: str) -> None:
    """Submit a task run to the configured durable queue (Celery)."""
    from backend.workers.orchestration import queue_orchestration_run

    queue_orchestration_run(run_id)
