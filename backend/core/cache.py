from __future__ import annotations

import asyncio
import hashlib
import json
import random
import time
from collections.abc import Awaitable, Callable
from dataclasses import asdict, dataclass, is_dataclass
from typing import Any, Protocol, TypeVar

import redis.asyncio as redis

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.observability.metrics import record_cache_operation

logger = get_logger(__name__)

redis_client = redis.from_url(
    settings.REDIS_URL,
    decode_responses=True,
    socket_connect_timeout=settings.REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS,
    socket_timeout=settings.REDIS_SOCKET_TIMEOUT_SECONDS,
)

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class CacheKey:
    """Typed cache key description used by application cache policies."""

    namespace: str
    value: str
    versioned: bool = False


@dataclass(frozen=True, slots=True)
class CachePolicy:
    """Cache behavior without coupling callers to Redis commands."""

    name: str
    ttl_seconds: int
    negative_ttl_seconds: int | None = None
    jitter_ratio: float = 0.1
    fail_open: bool = True

    def ttl_for(self, *, negative: bool = False) -> int:
        base = self.negative_ttl_seconds if negative else self.ttl_seconds
        if base is None:
            base = self.ttl_seconds
        jitter = max(0.0, min(float(self.jitter_ratio), 0.5))
        return max(1, int(round(base * random.uniform(1.0 - jitter, 1.0 + jitter))))


class CacheStore(Protocol):
    """Small async cache port implemented by Redis and test doubles."""

    async def get(self, key: str) -> str | None: ...

    async def set(self, key: str, value: str, policy: CachePolicy) -> None: ...

    async def delete(self, key: str) -> None: ...

    async def delete_many(self, keys: list[str]) -> None: ...

    async def increment(self, key: str) -> int: ...


class RedisCacheStore:
    """Typed adapter retained behind the historical ``redis_client`` export."""

    def __init__(self, client: CacheStore):
        self.client = client

    async def get(self, key: str) -> str | None:
        return await self.client.get(key)

    async def set(self, key: str, value: str, policy: CachePolicy) -> None:
        await self.client.setex(key, policy.ttl_for(), value)

    async def delete(self, key: str) -> None:
        await self.client.delete(key)

    async def delete_many(self, keys: list[str]) -> None:
        if keys:
            await self.client.delete(*keys)

    async def increment(self, key: str) -> int:
        return int(await self.client.incr(key))


class AsyncSingleFlight:
    """Process-local coalescing for expensive, safe-to-share cache fills."""

    def __init__(self, *, max_keys: int = 1024):
        self._locks: dict[str, asyncio.Lock] = {}
        self._guard = asyncio.Lock()
        self._max_keys = max_keys

    async def run(self, key: str, loader: Callable[[], Awaitable[T]]) -> T:
        async with self._guard:
            lock = self._locks.get(key)
            if lock is None:
                lock = asyncio.Lock()
                self._locks[key] = lock
            elif len(self._locks) > self._max_keys:
                self._locks = {name: item for name, item in self._locks.items() if item.locked()}
        async with lock:
            return await loader()


singleflight = AsyncSingleFlight()
_NEGATIVE_CACHE_MARKER = {"__troop_cache_state__": "negative"}
_CACHE_POLICIES = {
    "session": CachePolicy("session", settings.CACHE_SESSION_TTL_SECONDS, jitter_ratio=0.05),
    "embedding": CachePolicy("embedding", settings.CACHE_EMBEDDING_TTL_SECONDS),
    "rag_retrieval": CachePolicy(
        "rag_retrieval", settings.CACHE_RAG_RETRIEVAL_TTL_SECONDS, negative_ttl_seconds=30
    ),
    "project_acl": CachePolicy(
        "project_acl",
        settings.CACHE_ACL_TTL_SECONDS,
        negative_ttl_seconds=settings.CACHE_ACL_DENIED_TTL_SECONDS,
        jitter_ratio=0.05,
    ),
    "platform_metadata": CachePolicy(
        "platform_metadata", settings.CACHE_PLATFORM_METADATA_TTL_SECONDS
    ),
    "memory_settings": CachePolicy("memory_settings", settings.CACHE_MEMORY_SETTINGS_TTL_SECONDS),
}


def cache_policy(name: str) -> CachePolicy:
    """Return a stable policy object for callers and tests."""
    return _CACHE_POLICIES[name]


def cache_enabled() -> bool:
    return bool(getattr(settings, "CACHE_ENABLED", True))


def session_cache_key(user_id: str, session_id: str) -> str:
    return f"cache:session:{user_id}:{session_id}"


def embedding_cache_key(text: str, model: str) -> str:
    digest = hashlib.sha256(text.encode("utf-8")).hexdigest()
    safe_model = (model or "default").replace(":", "_")
    return f"cache:emb:{safe_model}:{digest}"


def rag_retrieval_cache_key(
    project_id: str,
    query: str,
    *,
    task_id: str | None,
    source_kind: str | None,
    include_decisions: bool,
    limit: int,
) -> str:
    q_hash = hashlib.sha256(query.strip().encode("utf-8")).hexdigest()[:32]
    return ":".join(
        [
            "cache:rag:retrieve",
            project_id,
            q_hash,
            task_id or "-",
            source_kind or "-",
            "1" if include_decisions else "0",
            str(limit),
        ]
    )


def rag_retrieval_cache_pattern(project_id: str) -> str:
    return f"cache:rag:retrieve:{project_id}:*"


def project_acl_cache_key(user_id: str, project_id: str) -> str:
    return f"cache:acl:project:{user_id}:{project_id}"


def platform_metadata_cache_key() -> str:
    return "cache:platform:metadata"


def memory_settings_cache_key(project_id: str) -> str:
    return f"cache:memory-settings:{project_id}"


def memory_context_cache_pattern(project_id: str) -> str:
    return f"cache:memory-context:{project_id}:*"


def cache_namespace_generation_key(namespace: str) -> str:
    return f"cache:generation:{namespace}"


async def _namespace_generation(namespace: str) -> int:
    try:
        raw = await redis_client.get(cache_namespace_generation_key(namespace))
        return max(1, int(raw or 1))
    except (TypeError, ValueError):
        return 1
    except Exception as exc:
        logger.warning("cache generation read failed namespace=%s error=%s", namespace, exc)
        return 1


async def _bump_namespace_generation(namespace: str) -> None:
    if not cache_enabled():
        return
    try:
        await redis_client.incr(cache_namespace_generation_key(namespace))
    except Exception as exc:
        logger.warning("cache generation bump failed namespace=%s error=%s", namespace, exc)


async def _versioned_key(namespace: str, value: str) -> str:
    generation = await _namespace_generation(namespace)
    return f"cache:{namespace}:v{generation}:{value}"


def _cache_metric_name(key: str) -> str:
    if key.startswith("cache:session:"):
        return "session"
    if key.startswith("cache:emb:"):
        return "embedding"
    if key.startswith("cache:rag:"):
        return "rag_retrieval"
    if key.startswith("cache:acl:"):
        return "project_acl"
    if key.startswith("cache:platform:"):
        return "platform_metadata"
    if key.startswith("cache:memory-settings:"):
        return "memory_settings"
    if key.startswith("cache:generation:"):
        return "generation"
    return "other"


async def _raw_get(key: str, *, cache_name: str | None = None) -> tuple[bool, str | None]:
    started = time.perf_counter()
    name = cache_name or _cache_metric_name(key)
    try:
        raw = await redis_client.get(key)
    except Exception as exc:
        record_cache_operation(name, "get", "error", time.perf_counter() - started)
        raise exc
    record_cache_operation(
        name, "get", "hit" if raw is not None else "miss", time.perf_counter() - started
    )
    return raw is not None, raw


async def _raw_set(
    key: str, value: str, ttl_seconds: int, *, cache_name: str | None = None
) -> None:
    started = time.perf_counter()
    name = cache_name or _cache_metric_name(key)
    try:
        await redis_client.setex(key, max(1, ttl_seconds), value)
    except Exception as exc:
        record_cache_operation(name, "set", "error", time.perf_counter() - started)
        raise exc
    record_cache_operation(name, "set", "success", time.perf_counter() - started)


async def _raw_delete(key: str, *, cache_name: str | None = None) -> None:
    started = time.perf_counter()
    name = cache_name or _cache_metric_name(key)
    try:
        await redis_client.delete(key)
    except Exception as exc:
        record_cache_operation(name, "delete", "error", time.perf_counter() - started)
        raise exc
    record_cache_operation(name, "delete", "success", time.perf_counter() - started)


async def _cache_get_json_state(
    key: str, *, cache_name: str | None = None
) -> tuple[bool, Any | None]:
    found, raw = await _raw_get(key, cache_name=cache_name)
    if not found or not raw:
        return False, None
    try:
        payload = json.loads(raw)
    except json.JSONDecodeError:
        return False, None
    if payload == _NEGATIVE_CACHE_MARKER:
        return True, None
    return True, payload


async def cache_get_json(key: str) -> Any | None:
    if not cache_enabled():
        return None
    try:
        _found, payload = await _cache_get_json_state(key)
    except Exception as exc:
        logger.warning("cache read failed cache=%s error=%s", _cache_metric_name(key), exc)
        return None
    return payload


async def cache_set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    if not cache_enabled():
        return
    try:
        await _raw_set(key, json.dumps(value), ttl_seconds)
    except Exception as exc:
        logger.warning("cache write failed cache=%s error=%s", _cache_metric_name(key), exc)


async def cache_delete(key: str) -> None:
    if not cache_enabled():
        return
    try:
        await _raw_delete(key)
    except Exception as exc:
        logger.warning("cache delete failed cache=%s error=%s", _cache_metric_name(key), exc)


async def cache_delete_pattern(pattern: str) -> None:
    if not cache_enabled():
        return
    started = time.perf_counter()
    try:
        batch: list[str] = []
        async for key in redis_client.scan_iter(match=pattern, count=200):
            batch.append(key)
            if len(batch) >= 200:
                pipe = redis_client.pipeline(transaction=False)
                for item in batch:
                    pipe.delete(item)
                await pipe.execute()
                batch.clear()
        if batch:
            pipe = redis_client.pipeline(transaction=False)
            for item in batch:
                pipe.delete(item)
            await pipe.execute()
        record_cache_operation("bulk", "delete_pattern", "success", time.perf_counter() - started)
    except Exception as exc:
        record_cache_operation("bulk", "delete_pattern", "error", time.perf_counter() - started)
        logger.warning("cache pattern delete failed cache=bulk error=%s", exc)


async def cache_get_or_set_json(
    key: str,
    loader: Callable[[], Awaitable[Any]],
    *,
    policy: CachePolicy,
    namespace: str | None = None,
) -> Any | None:
    """Read-through cache fill with single-flight and optional negative caching."""
    effective_key = await _versioned_key(namespace, key) if namespace else key
    if not cache_enabled():
        return await loader()
    found, payload = await _cache_get_json_state(effective_key, cache_name=policy.name)
    if found:
        return payload

    async def fill() -> Any | None:
        found_again, payload_again = await _cache_get_json_state(
            effective_key, cache_name=policy.name
        )
        if found_again:
            return payload_again
        value = await loader()
        try:
            is_negative = value is None
            stored = _NEGATIVE_CACHE_MARKER if is_negative else value
            ttl = policy.ttl_for(negative=is_negative)
            await _raw_set(effective_key, json.dumps(stored), ttl, cache_name=policy.name)
        except Exception as exc:
            if not policy.fail_open:
                raise
            logger.warning("cache fill write failed cache=%s error=%s", policy.name, exc)
        return value

    return await singleflight.run(effective_key, fill)


async def cache_singleflight[T](key: str, loader: Callable[[], Awaitable[T]]) -> T:
    """Coalesce one expensive safe operation without changing its return type."""
    return await singleflight.run(key, loader)


async def get_cached_project_acl(user_id: str, project_id: str) -> bool | None:
    """Return True/False when cached; None on miss."""
    if not cache_enabled():
        return None
    try:
        key = await _versioned_key(f"acl-project:{project_id}", user_id)
        _found, value = await _raw_get(key, cache_name="project_acl")
    except Exception as exc:
        logger.warning("project acl cache read failed error=%s", exc)
        return None
    if value is None:
        return None
    return value == "1"


async def set_cached_project_acl(user_id: str, project_id: str, *, allowed: bool) -> None:
    if not cache_enabled():
        return
    try:
        key = await _versioned_key(f"acl-project:{project_id}", user_id)
        await _raw_set(
            key,
            "1" if allowed else "0",
            cache_policy("project_acl").ttl_for(negative=not allowed),
            cache_name="project_acl",
        )
    except Exception as exc:
        logger.warning("project acl cache write failed: %s", exc)


async def invalidate_project_acl_cache(user_id: str, project_id: str) -> None:
    try:
        await _raw_delete(
            await _versioned_key(f"acl-project:{project_id}", user_id),
            cache_name="project_acl",
        )
    except Exception as exc:
        logger.warning("project acl cache invalidate failed error=%s", exc)


async def invalidate_project_acl_cache_for_project(project_id: str) -> None:
    await _bump_namespace_generation(f"acl-project:{project_id}")


async def get_cached_platform_metadata() -> dict[str, Any] | None:
    payload = await cache_get_json(platform_metadata_cache_key())
    return payload if isinstance(payload, dict) else None


async def set_cached_platform_metadata(payload: dict[str, Any]) -> None:
    await cache_set_json(
        platform_metadata_cache_key(),
        payload,
        ttl_seconds=settings.CACHE_PLATFORM_METADATA_TTL_SECONDS,
    )


async def invalidate_platform_metadata_cache() -> None:
    await cache_delete(platform_metadata_cache_key())


async def get_cached_memory_settings(project_id: str) -> dict[str, Any] | None:
    payload = await cache_get_json(memory_settings_cache_key(project_id))
    return payload if isinstance(payload, dict) else None


async def set_cached_memory_settings(project_id: str, settings_payload: dict[str, Any]) -> None:
    await cache_set_json(
        memory_settings_cache_key(project_id),
        settings_payload,
        ttl_seconds=settings.CACHE_MEMORY_SETTINGS_TTL_SECONDS,
    )


async def invalidate_project_memory_settings_cache(project_id: str) -> None:
    await cache_delete(memory_settings_cache_key(project_id))


async def invalidate_project_memory_context_cache(project_id: str) -> None:
    await _bump_namespace_generation(f"memory-context:{project_id}")


async def invalidate_project_knowledge_caches(project_id: str) -> None:
    """Event-driven bust for retrieval + memory context after document/semantic writes."""
    await invalidate_project_rag_retrieval_cache(project_id)
    await invalidate_project_memory_context_cache(project_id)


async def get_cached_session_valid(user_id: str, session_id: str) -> bool | None:
    if not cache_enabled():
        return None
    try:
        _found, value = await _raw_get(session_cache_key(user_id, session_id), cache_name="session")
    except Exception as exc:
        logger.warning("session cache read failed: %s", exc)
        return None
    if value is None:
        return None
    return value == "1"


async def set_cached_session_valid(user_id: str, session_id: str) -> None:
    if not cache_enabled():
        return
    try:
        await _raw_set(
            session_cache_key(user_id, session_id),
            "1",
            cache_policy("session").ttl_for(),
            cache_name="session",
        )
    except Exception as exc:
        logger.warning("session cache write failed: %s", exc)


async def invalidate_session_cache(user_id: str, session_id: str) -> None:
    if not cache_enabled():
        return
    try:
        await _raw_delete(session_cache_key(user_id, session_id), cache_name="session")
    except Exception as exc:
        logger.warning("session cache invalidate failed: %s", exc)


async def invalidate_user_session_caches(user_id: str) -> None:
    if not cache_enabled():
        return
    pattern = f"cache:session:{user_id}:*"
    try:
        await cache_delete_pattern(pattern)
    except Exception as exc:
        logger.warning("session cache bulk invalidate failed user_id=%s: %s", user_id, exc)


async def get_cached_embeddings(keys: list[str]) -> list[list[float] | None]:
    if not cache_enabled() or not keys:
        return [None] * len(keys)
    started = time.perf_counter()
    try:
        raw = await redis_client.mget(keys)
    except Exception as exc:
        record_cache_operation("embedding", "mget", "error", time.perf_counter() - started)
        logger.warning("embedding cache mget failed: %s", exc)
        return [None] * len(keys)
    record_cache_operation("embedding", "mget", "success", time.perf_counter() - started)
    out: list[list[float] | None] = []
    for item in raw:
        if not item:
            out.append(None)
            continue
        try:
            parsed = json.loads(item)
            out.append([float(x) for x in parsed])
        except (TypeError, ValueError, json.JSONDecodeError):
            out.append(None)
    return out


async def set_cached_embeddings(entries: list[tuple[str, list[float]]]) -> None:
    if not cache_enabled() or not entries:
        return
    started = time.perf_counter()
    try:
        pipe = redis_client.pipeline(transaction=False)
        for key, vector in entries:
            pipe.setex(key, cache_policy("embedding").ttl_for(), json.dumps(vector))
        await pipe.execute()
        record_cache_operation("embedding", "mset", "success", time.perf_counter() - started)
    except Exception as exc:
        record_cache_operation("embedding", "mset", "error", time.perf_counter() - started)
        logger.warning("embedding cache write failed: %s", exc)


async def get_cached_rag_retrieval(key: str) -> list[dict[str, Any]] | None:
    if not cache_enabled():
        return None
    try:
        parts = key.split(":")
        project_id = parts[3] if len(parts) > 3 else "unknown"
        effective_key = await _versioned_key(f"rag-retrieval:{project_id}", ":".join(parts[4:]))
        _found, raw = await _raw_get(effective_key, cache_name="rag_retrieval")
    except Exception as exc:
        logger.warning("rag retrieval cache read failed: %s", exc)
        return None
    if not raw:
        return None
    try:
        payload = json.loads(raw)
        if isinstance(payload, list):
            return payload
    except json.JSONDecodeError:
        return None
    return None


async def set_cached_rag_retrieval(key: str, matches: list[Any]) -> None:
    if not cache_enabled():
        return
    try:
        payload = [asdict(item) if is_dataclass(item) else dict(item) for item in matches]
        parts = key.split(":")
        project_id = parts[3] if len(parts) > 3 else "unknown"
        effective_key = await _versioned_key(f"rag-retrieval:{project_id}", ":".join(parts[4:]))
        await _raw_set(
            effective_key,
            json.dumps(payload),
            cache_policy("rag_retrieval").ttl_for(negative=not payload),
            cache_name="rag_retrieval",
        )
    except Exception as exc:
        logger.warning("rag retrieval cache write failed: %s", exc)


async def invalidate_project_rag_retrieval_cache(project_id: str) -> None:
    if not cache_enabled():
        return
    await _bump_namespace_generation(f"rag-retrieval:{project_id}")
