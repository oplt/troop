"""Bounded queue-state refresh for Prometheus scrapes."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import func, select

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.db.session import SessionLocal
from backend.modules.observability.metrics import record_queue_state
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

    if not default_queue_depth_available:
        return

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


__all__ = ["refresh_queue_metrics"]
