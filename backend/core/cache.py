from __future__ import annotations

import hashlib
import json
import logging
from dataclasses import asdict, is_dataclass
from typing import Any

import redis.asyncio as redis

from backend.core.config import settings

logger = logging.getLogger(__name__)

redis_client = redis.from_url(settings.REDIS_URL, decode_responses=True)


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


async def cache_get_json(key: str) -> Any | None:
    if not cache_enabled():
        return None
    try:
        raw = await redis_client.get(key)
    except Exception as exc:
        logger.warning("cache read failed key=%s: %s", key, exc)
        return None
    if not raw:
        return None
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        return None


async def cache_set_json(key: str, value: Any, *, ttl_seconds: int) -> None:
    if not cache_enabled():
        return
    try:
        await redis_client.setex(key, max(1, ttl_seconds), json.dumps(value))
    except Exception as exc:
        logger.warning("cache write failed key=%s: %s", key, exc)


async def cache_delete(key: str) -> None:
    if not cache_enabled():
        return
    try:
        await redis_client.delete(key)
    except Exception as exc:
        logger.warning("cache delete failed key=%s: %s", key, exc)


async def cache_delete_pattern(pattern: str) -> None:
    if not cache_enabled():
        return
    try:
        async for key in redis_client.scan_iter(match=pattern, count=200):
            await redis_client.delete(key)
    except Exception as exc:
        logger.warning("cache pattern delete failed pattern=%s: %s", pattern, exc)


async def get_cached_project_acl(user_id: str, project_id: str) -> bool | None:
    """Return True/False when cached; None on miss."""
    if not cache_enabled():
        return None
    try:
        value = await redis_client.get(project_acl_cache_key(user_id, project_id))
    except Exception as exc:
        logger.warning("project acl cache read failed: %s", exc)
        return None
    if value is None:
        return None
    return value == "1"


async def set_cached_project_acl(user_id: str, project_id: str, *, allowed: bool) -> None:
    if not cache_enabled():
        return
    ttl = settings.CACHE_ACL_TTL_SECONDS if allowed else settings.CACHE_ACL_DENIED_TTL_SECONDS
    try:
        await redis_client.setex(
            project_acl_cache_key(user_id, project_id),
            max(1, ttl),
            "1" if allowed else "0",
        )
    except Exception as exc:
        logger.warning("project acl cache write failed: %s", exc)


async def invalidate_project_acl_cache(user_id: str, project_id: str) -> None:
    await cache_delete(project_acl_cache_key(user_id, project_id))


async def invalidate_project_acl_cache_for_project(project_id: str) -> None:
    await cache_delete_pattern(f"cache:acl:project:*:{project_id}")


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
    await cache_delete_pattern(memory_context_cache_pattern(project_id))


async def invalidate_project_knowledge_caches(project_id: str) -> None:
    """Event-driven bust for retrieval + memory context after document/semantic writes."""
    await invalidate_project_rag_retrieval_cache(project_id)
    await invalidate_project_memory_context_cache(project_id)


async def get_cached_session_valid(user_id: str, session_id: str) -> bool | None:
    if not cache_enabled():
        return None
    try:
        value = await redis_client.get(session_cache_key(user_id, session_id))
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
        await redis_client.setex(
            session_cache_key(user_id, session_id),
            settings.CACHE_SESSION_TTL_SECONDS,
            "1",
        )
    except Exception as exc:
        logger.warning("session cache write failed: %s", exc)


async def invalidate_session_cache(user_id: str, session_id: str) -> None:
    if not cache_enabled():
        return
    try:
        await redis_client.delete(session_cache_key(user_id, session_id))
    except Exception as exc:
        logger.warning("session cache invalidate failed: %s", exc)


async def invalidate_user_session_caches(user_id: str) -> None:
    if not cache_enabled():
        return
    pattern = f"cache:session:{user_id}:*"
    try:
        async for key in redis_client.scan_iter(match=pattern, count=200):
            await redis_client.delete(key)
    except Exception as exc:
        logger.warning("session cache bulk invalidate failed user_id=%s: %s", user_id, exc)


async def get_cached_embeddings(keys: list[str]) -> list[list[float] | None]:
    if not cache_enabled() or not keys:
        return [None] * len(keys)
    try:
        raw = await redis_client.mget(keys)
    except Exception as exc:
        logger.warning("embedding cache mget failed: %s", exc)
        return [None] * len(keys)
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
    ttl = settings.CACHE_EMBEDDING_TTL_SECONDS
    try:
        pipe = redis_client.pipeline()
        for key, vector in entries:
            pipe.setex(key, ttl, json.dumps(vector))
        await pipe.execute()
    except Exception as exc:
        logger.warning("embedding cache write failed: %s", exc)


async def get_cached_rag_retrieval(key: str) -> list[dict[str, Any]] | None:
    if not cache_enabled():
        return None
    try:
        raw = await redis_client.get(key)
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
        payload = [
            asdict(item) if is_dataclass(item) else dict(item)
            for item in matches
        ]
        await redis_client.setex(
            key,
            settings.CACHE_RAG_RETRIEVAL_TTL_SECONDS,
            json.dumps(payload),
        )
    except Exception as exc:
        logger.warning("rag retrieval cache write failed: %s", exc)


async def invalidate_project_rag_retrieval_cache(project_id: str) -> None:
    if not cache_enabled():
        return
    pattern = rag_retrieval_cache_pattern(project_id)
    try:
        async for key in redis_client.scan_iter(match=pattern, count=200):
            await redis_client.delete(key)
    except Exception as exc:
        logger.warning(
            "rag retrieval cache invalidate failed project_id=%s: %s",
            project_id,
            exc,
        )
