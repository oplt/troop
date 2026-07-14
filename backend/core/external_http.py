"""Shared policy for outbound HTTP calls.

The application has several provider and integration adapters.  Keeping the
timeout shape and safe request metadata in one place prevents a scalar
``httpx`` timeout from accidentally leaving a connection phase unbounded and
keeps request correlation available without forwarding user data or secrets.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

import httpx

from backend.core.config import settings
from backend.core.request_context import get_request_context

DEFAULT_EXTERNAL_TIMEOUT_SECONDS = 30.0
MAX_CONNECT_OR_POOL_TIMEOUT_SECONDS = 10.0


def external_timeout(timeout_seconds: float | int | None = None) -> httpx.Timeout:
    """Build a bounded timeout with an explicit deadline for every phase."""
    total = float(
        timeout_seconds
        or settings.EXTERNAL_HTTP_TIMEOUT_SECONDS
        or DEFAULT_EXTERNAL_TIMEOUT_SECONDS
    )
    if total <= 0:
        raise ValueError("External HTTP timeout must be greater than zero")
    connect_and_pool = min(
        total,
        max(
            0.1,
            min(
                settings.EXTERNAL_HTTP_CONNECT_TIMEOUT_SECONDS,
                settings.EXTERNAL_HTTP_POOL_TIMEOUT_SECONDS,
                MAX_CONNECT_OR_POOL_TIMEOUT_SECONDS,
            ),
        ),
    )
    return httpx.Timeout(
        timeout=total,
        connect=connect_and_pool,
        read=total,
        write=total,
        pool=connect_and_pool,
    )


def external_headers(extra: Mapping[str, str] | None = None) -> dict[str, str]:
    """Merge caller headers with safe request correlation headers.

    Authentication headers and payload data stay owned by the caller.  Only
    identifiers explicitly designed for propagation are forwarded.
    """
    headers = dict(extra or {})
    context = get_request_context()
    if context.request_id:
        headers.setdefault("X-Request-ID", context.request_id)
    if context.correlation_id:
        headers.setdefault("X-Correlation-ID", context.correlation_id)
    if context.trace_id:
        headers.setdefault("X-Trace-ID", context.trace_id)
    return headers


# ``outbound_headers`` is retained as the descriptive public alias used by
# callers that do not need to distinguish HTTP from other integrations.
outbound_headers = external_headers


@dataclass(frozen=True, slots=True)
class ExternalRetryPolicy:
    """Retry classification without unsafe automatic retries.

    Callers may retry only idempotent operations or operations carrying an
    idempotency key.  Write operations intentionally default to no retry.
    """

    max_attempts: int
    retry_statuses: tuple[int, ...]
    retry_timeouts: bool
    reason: str


def external_retry_policy(
    method: str,
    *,
    idempotency_key: bool = False,
) -> ExternalRetryPolicy:
    """Return the safe retry contract for an outbound HTTP method."""
    normalized_method = method.upper()
    safe_method = normalized_method in {"GET", "HEAD", "OPTIONS"}
    can_retry = safe_method or idempotency_key
    if not can_retry:
        return ExternalRetryPolicy(
            max_attempts=1,
            retry_statuses=(),
            retry_timeouts=False,
            reason="non-idempotent write without an idempotency key",
        )
    return ExternalRetryPolicy(
        max_attempts=max(1, min(int(settings.EXTERNAL_HTTP_MAX_RETRIES), 5)),
        retry_statuses=(408, 425, 429, 500, 502, 503, 504),
        retry_timeouts=True,
        reason="transient failure on an idempotent or idempotency-keyed request",
    )


__all__ = [
    "ExternalRetryPolicy",
    "external_retry_policy",
    "external_headers",
    "external_timeout",
    "outbound_headers",
]
