from __future__ import annotations

import httpx
import pytest
from backend.core.distributed_lock import RedisLease
from backend.modules.observability.slo import SLO_DEFINITIONS, slo_catalog
from backend.modules.orchestration.execution.durable_execution import (
    is_run_execution_claimable,
)
from backend.tools.phase7_validation import percentile, run_http_load


class FakeRedis:
    def __init__(self, *, acquired: bool = True):
        self.acquired = acquired
        self.calls: list[tuple] = []

    async def set(self, *args, **kwargs):
        self.calls.append(("set", args, kwargs))
        return self.acquired

    async def eval(self, *args):
        self.calls.append(("eval", args, {}))
        return 1


@pytest.mark.asyncio
async def test_redis_lease_is_ownership_safe_and_reports_contention() -> None:
    redis = FakeRedis()
    lease = RedisLease(redis, "troop:singleton:test", ttl_seconds=30)

    async with lease as acquired:
        assert acquired is True
        assert lease.acquired is True

    assert redis.calls[0][0] == "set"
    assert redis.calls[0][2] == {"nx": True, "px": 30_000}
    assert redis.calls[1][0] == "eval"
    assert lease.acquired is False

    contended = RedisLease(FakeRedis(acquired=False), "troop:singleton:test", ttl_seconds=30)
    assert await contended.acquire() is False
    await contended.release()
    assert len(contended.client.calls) == 1


def test_slo_catalog_has_owned_budgets_and_runbooks() -> None:
    catalog = slo_catalog()
    assert len(catalog) == len(SLO_DEFINITIONS) >= 5
    assert all(item["owner"] and item["runbook"] for item in catalog)
    assert all(0 < item["error_budget"] < 1 for item in catalog)


def test_duplicate_delivery_claim_policy_is_terminal_and_explicit() -> None:
    assert is_run_execution_claimable("queued") is True
    assert is_run_execution_claimable("failed") is True
    assert is_run_execution_claimable("in_progress") is False
    assert is_run_execution_claimable("completed") is False
    assert is_run_execution_claimable("cancelled") is False
    assert is_run_execution_claimable("awaiting_approval") is False


@pytest.mark.asyncio
async def test_bounded_http_load_reports_percentiles_and_failures() -> None:
    calls = 0

    async def handler(request: httpx.Request) -> httpx.Response:
        nonlocal calls
        calls += 1
        return httpx.Response(503 if calls == 3 else 200, request=request)

    summary = await run_http_load(
        "https://example.test/health/live",
        requests=6,
        concurrency=2,
        transport=httpx.MockTransport(handler),
    )

    assert summary.completed == 6
    assert summary.failures == 1
    assert summary.p95_ms >= summary.p50_ms
    assert summary.p99_ms >= summary.p95_ms


def test_percentile_is_bounded_for_empty_and_small_samples() -> None:
    assert percentile([], 0.95) == 0.0
    assert percentile([10.0, 20.0, 30.0], 0.95) == 20.0
