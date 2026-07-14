"""Bounded liveness/readiness dependency checks."""

from __future__ import annotations

import asyncio
import time
from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy import text

from backend.core.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class DependencyCheck:
    status: str
    latency_ms: float
    required: bool = True
    error_type: str | None = None


async def _check(name: str, operation: Any, timeout_seconds: float) -> DependencyCheck:
    started = time.perf_counter()
    try:
        await asyncio.wait_for(operation(), timeout=timeout_seconds)
        return DependencyCheck(status="ok", latency_ms=(time.perf_counter() - started) * 1000)
    except TimeoutError:
        logger.warning("readiness_dependency_timeout dependency=%s", name)
        return DependencyCheck(
            status="error",
            latency_ms=(time.perf_counter() - started) * 1000,
            error_type="timeout",
        )
    except Exception as exc:
        logger.warning(
            "readiness_dependency_error dependency=%s error_type=%s",
            name,
            type(exc).__name__,
        )
        return DependencyCheck(
            status="error",
            latency_ms=(time.perf_counter() - started) * 1000,
            error_type=type(exc).__name__,
        )


async def readiness_report(
    engine: Any,
    redis_client: Any,
    broker_url: str,
    timeout_seconds: float,
) -> dict[str, Any]:
    async def check_db() -> None:
        async with engine.connect() as connection:
            await connection.execute(text("SELECT 1"))

    async def check_redis() -> None:
        await redis_client.ping()

    db_check, redis_check = await asyncio.gather(
        _check("db", check_db, timeout_seconds),
        _check("redis", check_redis, timeout_seconds),
    )
    queue_required = broker_url.startswith(("redis://", "rediss://"))
    queue_check = DependencyCheck(
        status=redis_check.status if queue_required else "unknown",
        latency_ms=redis_check.latency_ms if queue_required else 0.0,
        required=queue_required,
        error_type=redis_check.error_type if queue_required else None,
    )
    check_objects = {"db": db_check, "redis": redis_check, "queue": queue_check}
    checks = {name: asdict(value) for name, value in check_objects.items()}
    ready = all(item.status == "ok" or not item.required for item in check_objects.values())
    return {"status": "ok" if ready else "not_ready", "checks": checks}


__all__ = ["DependencyCheck", "readiness_report"]
