"""Retry and per-host circuit breaker helpers for outbound HTTP clients."""

from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable

import httpx

TRANSIENT_HTTP_STATUS_CODES = frozenset({429, 502, 503})


class CircuitBreakerOpenError(RuntimeError):
    """Raised when requests to a host are temporarily blocked after repeated failures."""


class CircuitBreaker:
    """In-memory circuit breaker keyed by base URL."""

    def __init__(
        self,
        *,
        failure_threshold: int = 5,
        cooldown_seconds: float = 30.0,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._failures: dict[str, int] = {}
        self._opened_at: dict[str, float] = {}

    def allow(self, key: str) -> bool:
        opened = self._opened_at.get(key)
        if opened is None:
            return True
        if (time.monotonic() - opened) >= self.cooldown_seconds:
            self._opened_at.pop(key, None)
            self._failures[key] = 0
            return True
        return False

    def record_success(self, key: str) -> None:
        self._failures[key] = 0
        self._opened_at.pop(key, None)

    def record_failure(self, key: str) -> None:
        count = self._failures.get(key, 0) + 1
        self._failures[key] = count
        if count >= self.failure_threshold:
            self._opened_at[key] = time.monotonic()

    def reset(self, key: str | None = None) -> None:
        if key is None:
            self._failures.clear()
            self._opened_at.clear()
            return
        self._failures.pop(key, None)
        self._opened_at.pop(key, None)


_circuit_breakers: dict[str, CircuitBreaker] = {}


def circuit_breaker_for(base_url: str) -> CircuitBreaker:
    key = (base_url or "").rstrip("/") or "__default__"
    breaker = _circuit_breakers.get(key)
    if breaker is None:
        breaker = CircuitBreaker()
        _circuit_breakers[key] = breaker
    return breaker


def is_transient_http_error(exc: BaseException) -> bool:
    if isinstance(exc, httpx.HTTPStatusError):
        return exc.response.status_code in TRANSIENT_HTTP_STATUS_CODES
    return isinstance(exc, httpx.TransportError)


async def request_with_retry[T](
    request_fn: Callable[[], Awaitable[T]],
    *,
    base_url: str,
    max_retries: int = 2,
    base_delay_seconds: float = 0.25,
) -> T:
    """Retry transient HTTP failures with exponential backoff."""
    breaker = circuit_breaker_for(base_url)
    if not breaker.allow(base_url):
        raise CircuitBreakerOpenError(f"Circuit open for {base_url}")

    attempt = 0
    while True:
        try:
            result = await request_fn()
            breaker.record_success(base_url)
            return result
        except Exception as exc:
            if not is_transient_http_error(exc) or attempt >= max_retries:
                breaker.record_failure(base_url)
                raise
            delay = base_delay_seconds * (2**attempt)
            attempt += 1
            await asyncio.sleep(delay)


def reset_circuit_breakers() -> None:
    """Test helper to clear breaker state."""
    for breaker in _circuit_breakers.values():
        breaker.reset()


__all__ = [
    "CircuitBreaker",
    "CircuitBreakerOpenError",
    "TRANSIENT_HTTP_STATUS_CODES",
    "circuit_breaker_for",
    "is_transient_http_error",
    "request_with_retry",
    "reset_circuit_breakers",
]
