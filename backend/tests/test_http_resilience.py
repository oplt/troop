"""Unit tests for outbound HTTP retry and circuit breaker."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import httpx
import pytest
from backend.modules.workforce.services.http_resilience import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    circuit_breaker_for,
    request_with_retry,
    reset_circuit_breakers,
)


@pytest.fixture(autouse=True)
def _reset_breakers() -> None:
    reset_circuit_breakers()


@pytest.mark.asyncio
async def test_request_with_retry_recovers_on_transient_status() -> None:
    calls = {"count": 0}

    async def flaky() -> str:
        calls["count"] += 1
        if calls["count"] == 1:
            request = httpx.Request("GET", "https://example.com")
            response = httpx.Response(503, request=request)
            raise httpx.HTTPStatusError("503", request=request, response=response)
        return "ok"

    with patch("backend.modules.workforce.services.http_resilience.asyncio.sleep", new=AsyncMock()):
        result = await request_with_retry(flaky, base_url="https://example.com")

    assert result == "ok"
    assert calls["count"] == 2


@pytest.mark.asyncio
async def test_request_with_retry_stops_after_max_retries() -> None:
    async def always_fail() -> None:
        request = httpx.Request("GET", "https://example.com")
        response = httpx.Response(502, request=request)
        raise httpx.HTTPStatusError("502", request=request, response=response)

    with (
        patch("backend.modules.workforce.services.http_resilience.asyncio.sleep", new=AsyncMock()),
        pytest.raises(httpx.HTTPStatusError),
    ):
        await request_with_retry(always_fail, base_url="https://example.com", max_retries=2)

    breaker = circuit_breaker_for("https://example.com")
    assert breaker._failures["https://example.com"] >= 1


def test_circuit_breaker_opens_after_threshold() -> None:
    breaker = CircuitBreaker(failure_threshold=3, cooldown_seconds=30.0)
    key = "https://mcp.test"

    for _ in range(3):
        breaker.record_failure(key)

    assert breaker.allow(key) is False


@pytest.mark.asyncio
async def test_circuit_breaker_blocks_subsequent_requests() -> None:
    breaker = circuit_breaker_for("https://blocked.test")
    for _ in range(5):
        breaker.record_failure("https://blocked.test")

    async def should_not_run() -> str:
        return "nope"

    with pytest.raises(CircuitBreakerOpenError):
        await request_with_retry(should_not_run, base_url="https://blocked.test")
