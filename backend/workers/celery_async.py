"""Non-blocking helpers for waiting on Celery AsyncResult from async code."""

from __future__ import annotations

import asyncio
import time
from typing import Any


async def await_celery_result(
    async_result: Any,
    *,
    timeout_seconds: float,
    poll_interval: float = 0.25,
) -> Any:
    """Poll ``AsyncResult.ready()`` instead of blocking a thread on ``get()`` for the full job."""
    deadline = time.monotonic() + max(0.0, timeout_seconds)
    while True:
        if async_result.ready():
            return async_result.get(propagate=False)
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(
                f"Celery task {getattr(async_result, 'id', '?')} did not finish within {timeout_seconds}s"
            )
        await asyncio.sleep(min(poll_interval, remaining))
