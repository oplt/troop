"""Small Redis lease used for singleton work in horizontally scaled deployments."""

from __future__ import annotations

import secrets
from typing import Any

from backend.core.logging import get_logger
from backend.modules.observability.metrics import record_distributed_lock

logger = get_logger(__name__)

_RELEASE_SCRIPT = """
if redis.call('get', KEYS[1]) == ARGV[1] then
  return redis.call('del', KEYS[1])
end
return 0
"""


class RedisLease:
    """An ownership-safe, expiring Redis lease.

    A failed acquisition is a normal contention result. Redis errors are allowed to
    propagate so singleton jobs fail closed instead of running concurrently.
    """

    def __init__(self, client: Any, key: str, *, ttl_seconds: int, metric_name: str | None = None):
        self.client = client
        self.key = key
        self.ttl_ms = max(1, int(ttl_seconds)) * 1000
        self.metric_name = metric_name or key.rsplit(":", 1)[-1]
        self.token = secrets.token_urlsafe(24)
        self.acquired = False

    async def acquire(self) -> bool:
        self.acquired = bool(await self.client.set(self.key, self.token, nx=True, px=self.ttl_ms))
        record_distributed_lock(self.metric_name, "acquired" if self.acquired else "contended")
        return self.acquired

    async def release(self) -> None:
        if not self.acquired:
            return
        await self.client.eval(_RELEASE_SCRIPT, 1, self.key, self.token)
        self.acquired = False
        record_distributed_lock(self.metric_name, "released")

    async def __aenter__(self) -> bool:
        return await self.acquire()

    async def __aexit__(self, exc_type, exc, tb) -> None:
        try:
            await self.release()
        except Exception:
            logger.exception("distributed_lock_release_failed lock=%s", self.metric_name)


__all__ = ["RedisLease"]
