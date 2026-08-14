"""Process-local cache for GitHub App installation access tokens."""

from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from datetime import datetime

from backend.core.cache import AsyncSingleFlight
from backend.core.config import settings
from backend.modules.github.models import GithubConnection

_singleflight = AsyncSingleFlight(max_keys=256)
_cache: dict[str, _CachedInstallationToken] = {}


@dataclass(frozen=True, slots=True)
class _CachedInstallationToken:
    token: str
    expires_at: float


def installation_token_cache_key(connection: GithubConnection) -> str:
    installation_id = int((connection.metadata_json or {}).get("installation_id") or 0)
    return f"{connection.id}:{installation_id}:{connection.api_url}"


def installation_token_safety_margin_seconds() -> int:
    return max(60, int(getattr(settings, "GITHUB_INSTALLATION_TOKEN_SAFETY_MARGIN_SECONDS", 300)))


def invalidate_installation_token_cache(connection: GithubConnection) -> None:
    _cache.pop(installation_token_cache_key(connection), None)


def clear_installation_token_cache() -> None:
    _cache.clear()


def cache_installation_token(
    connection: GithubConnection,
    *,
    token: str,
    expires_at: float,
) -> None:
    _cache[installation_token_cache_key(connection)] = _CachedInstallationToken(
        token=token,
        expires_at=expires_at,
    )


def get_cached_installation_token(connection: GithubConnection) -> str | None:
    entry = _cache.get(installation_token_cache_key(connection))
    if entry is None:
        return None
    if time.time() >= entry.expires_at - installation_token_safety_margin_seconds():
        invalidate_installation_token_cache(connection)
        return None
    return entry.token


def parse_installation_token_expiry(payload: dict) -> float:
    raw = payload.get("expires_at")
    if isinstance(raw, str) and raw.strip():
        normalized = raw.strip().replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).timestamp()
    return time.time() + 3600


async def get_or_refresh_installation_token(
    connection: GithubConnection,
    mint: Callable[[], Awaitable[tuple[str, float]]],
) -> str:
    cached = get_cached_installation_token(connection)
    if cached is not None:
        return cached

    cache_key = installation_token_cache_key(connection)

    async def load() -> str:
        still_cached = get_cached_installation_token(connection)
        if still_cached is not None:
            return still_cached
        token, expires_at = await mint()
        cache_installation_token(connection, token=token, expires_at=expires_at)
        return token

    return await _singleflight.run(cache_key, load)
