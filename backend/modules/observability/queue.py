"""Bounded queue-state refresh for Prometheus scrapes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.db.session import SessionLocal, engine
from backend.modules.observability.metrics import (
    record_db_pool_state,
    record_queue_state,
    record_run_status_snapshot,
)
from backend.modules.orchestration.models import TaskRun

logger = get_logger(__name__)


def _age_seconds(created_at: datetime | None) -> float | None:
    if created_at is None:
        return None
    timestamp = created_at if created_at.tzinfo else created_at.replace(tzinfo=UTC)
    return max(0.0, (datetime.now(UTC) - timestamp).total_seconds())


async def refresh_queue_metrics(redis_client: Any) -> None:
    """Refresh Redis queue depth and durable orchestration queue age.

    Queue names are configuration-derived and bounded. Database refresh failures
    fail open for the scrape; the readiness endpoint remains authoritative for
    dependency health.
    """
    queue_names = tuple(
        dict.fromkeys(
            (
                settings.CELERY_TASK_DEFAULT_QUEUE,
                settings.CELERY_QUEUE_GITHUB,
                settings.CELERY_QUEUE_MODEL_GATEWAY,
                settings.CELERY_QUEUE_OBSERVABILITY,
                settings.CELERY_QUEUE_CPU,
                settings.CELERY_QUEUE_INTEGRATIONS,
                settings.CELERY_EMAIL_QUEUE,
            )
        )
    )
    default_queue_depth_available = False

    async def refresh_depth(queue: str) -> None:
        nonlocal default_queue_depth_available
        try:
            depth = await asyncio.wait_for(
                redis_client.llen(queue), timeout=settings.METRICS_REFRESH_TIMEOUT_SECONDS
            )
            record_queue_state(queue, depth=int(depth))
            if queue == settings.CELERY_TASK_DEFAULT_QUEUE:
                default_queue_depth_available = True
        except Exception as exc:
            logger.debug(
                "queue_depth_refresh_failed queue=%s error_type=%s", queue, type(exc).__name__
            )

    await asyncio.gather(*(refresh_depth(queue) for queue in queue_names))

    if default_queue_depth_available:

        async def durable_queue_state() -> None:
            async with SessionLocal() as db:
                row = (
                    await db.execute(
                        select(func.count(TaskRun.id), func.min(TaskRun.created_at)).where(
                            TaskRun.status == "queued"
                        )
                    )
                ).one()
            record_queue_state(
                settings.CELERY_TASK_DEFAULT_QUEUE,
                depth=int(row[0] or 0),
                oldest_age_seconds=_age_seconds(row[1]),
            )

        try:
            await asyncio.wait_for(
                durable_queue_state(), timeout=settings.METRICS_REFRESH_TIMEOUT_SECONDS
            )
        except Exception as exc:
            logger.debug("durable_queue_age_refresh_failed error_type=%s", type(exc).__name__)

    await asyncio.gather(
        refresh_run_status_metrics(),
        asyncio.to_thread(refresh_db_pool_metrics),
    )


async def refresh_run_status_metrics() -> None:
    """Expose active run counts and stale in_progress pressure for alerting."""
    stale_cutoff = datetime.now(UTC) - timedelta(
        seconds=max(60, int(settings.ORCHESTRATION_STALE_IN_PROGRESS_SECONDS))
    )
    active_statuses = ("queued", "in_progress", "blocked", "awaiting_approval")

    async def query() -> None:
        async with SessionLocal() as db:
            counts_result = await db.execute(
                select(TaskRun.status, func.count(TaskRun.id))
                .where(TaskRun.status.in_(active_statuses))
                .group_by(TaskRun.status)
            )
            counts = {str(row[0]): int(row[1]) for row in counts_result.all()}

            stale_result = await db.execute(
                select(func.count(TaskRun.id)).where(
                    TaskRun.status == "in_progress",
                    TaskRun.started_at.is_not(None),
                    TaskRun.started_at < stale_cutoff,
                )
            )
            stale_count = int(stale_result.scalar_one() or 0)

            oldest_result = await db.execute(
                select(func.min(TaskRun.started_at)).where(TaskRun.status == "in_progress")
            )
            oldest_started = oldest_result.scalar_one()

        record_run_status_snapshot(
            counts,
            stale_in_progress=stale_count,
            oldest_in_progress_age_seconds=_age_seconds(oldest_started),
        )

    try:
        await asyncio.wait_for(query(), timeout=settings.METRICS_REFRESH_TIMEOUT_SECONDS)
    except Exception as exc:
        logger.debug("run_status_metrics_refresh_failed error_type=%s", type(exc).__name__)


def refresh_db_pool_metrics() -> None:
    """Publish SQLAlchemy pool saturation gauges for the current process."""
    try:
        pool = engine.sync_engine.pool
        checked_out = int(getattr(pool, "checkedout", lambda: 0)())
        overflow = max(0, int(getattr(pool, "overflow", lambda: 0)()))
        pool_size = int(getattr(pool, "size", lambda: settings.effective_database_pool_size)())
        record_db_pool_state(
            role=settings.database_process_role,
            checked_out=checked_out,
            overflow=overflow,
            pool_size=pool_size,
        )
    except Exception as exc:
        logger.debug("db_pool_metrics_refresh_failed error_type=%s", type(exc).__name__)


__all__ = ["refresh_db_pool_metrics", "refresh_queue_metrics", "refresh_run_status_metrics"]
