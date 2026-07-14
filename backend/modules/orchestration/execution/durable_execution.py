"""Durable orchestration enqueueing (control plane).

Celery + Redis is the active durable backend. Runs remain recoverable because the worker
persists checkpoints, signals, query snapshots, and workflow steps in Postgres before and during
execution. The adapter boundary is intentionally small so a Temporal worker can replace the
transport later without changing API callers.
"""

from __future__ import annotations

from backend.core.config import settings
from backend.core.logging import get_logger

SUPPORTED_DURABLE_BACKENDS = frozenset({"celery"})
NON_CLAIMABLE_RUN_STATUSES = frozenset(
    {"in_progress", "completed", "cancelled", "awaiting_approval"}
)


def is_run_execution_claimable(status: str | None) -> bool:
    """Prevent duplicate deliveries from starting an already active/terminal run."""
    return str(status or "").strip().lower() not in NON_CLAIMABLE_RUN_STATUSES


def durable_backend_status() -> dict[str, object]:
    configured = str(settings.ORCHESTRATION_DURABLE_QUEUE_BACKEND or "celery").strip().lower()
    return {
        "configured": configured,
        "active": "celery" if configured == "celery" else None,
        "available": configured in SUPPORTED_DURABLE_BACKENDS,
        "delivery": "at_least_once" if configured == "celery" else None,
        "checkpointed": True,
        "temporal_adapter_ready": True,
        "temporal_worker_available": False,
    }


def submit_orchestration_run(run_id: str) -> None:
    """Submit a task run to the configured durable queue.

    Fail closed for unsupported backends instead of silently queueing to Celery when an operator
    explicitly configured another backend.
    """
    backend = str(settings.ORCHESTRATION_DURABLE_QUEUE_BACKEND or "celery").strip().lower()
    if backend not in SUPPORTED_DURABLE_BACKENDS:
        raise RuntimeError(
            f"Durable orchestration backend '{backend}' is configured but unavailable. "
            "Use celery or install/configure the Temporal worker adapter."
        )
    logger = get_logger(__name__)
    logger.info(f"[SUBMIT] Submitting orchestration run {run_id}")
    from backend.workers.orchestration import queue_orchestration_run

    queue_orchestration_run(run_id)
    logger.info(f"[SUBMIT] Queued run {run_id}")
