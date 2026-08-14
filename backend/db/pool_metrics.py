"""SQLAlchemy pool instrumentation for checkout wait and saturation metrics."""

from __future__ import annotations

from time import perf_counter
from typing import Any

from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine
from sqlalchemy.pool import Pool

from backend.modules.observability.metrics import record_db_pool_checkout_wait

_REGISTERED_ATTR = "_troop_checkout_metrics_registered"


def _engine_pool(engine: Engine | AsyncEngine) -> Pool:
    sync_engine = getattr(engine, "sync_engine", engine)
    return sync_engine.pool  # type: ignore[union-attr]


def register_db_pool_checkout_metrics(engine: Engine | AsyncEngine, *, role: str) -> None:
    """Time pool checkouts via ``QueuePool._do_get`` for the configured process role."""
    pool = _engine_pool(engine)
    if getattr(pool, _REGISTERED_ATTR, False):
        return
    setattr(pool, _REGISTERED_ATTR, True)

    original_do_get = pool._do_get

    def timed_do_get() -> Any:
        started = perf_counter()
        try:
            return original_do_get()
        finally:
            record_db_pool_checkout_wait(perf_counter() - started, role=role)

    pool._do_get = timed_do_get  # type: ignore[method-assign]


__all__ = ["register_db_pool_checkout_metrics"]
