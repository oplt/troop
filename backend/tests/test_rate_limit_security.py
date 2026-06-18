from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException

from backend.modules.orchestration.execution.execution_service import OrchestrationExecutionServiceMixin


class _ExecutionHarness(OrchestrationExecutionServiceMixin):
    def __init__(self) -> None:
        self.db = MagicMock()


@pytest.mark.asyncio
async def test_run_rate_limit_skipped_in_dev():
    harness = _ExecutionHarness()
    with patch("backend.modules.orchestration.execution.execution_service.settings.APP_ENV", "dev"):
        await harness._enforce_orchestration_run_rate_limit("user-1")


@pytest.mark.asyncio
async def test_run_rate_limit_enforced_outside_dev():
    harness = _ExecutionHarness()
    redis = MagicMock()
    redis.incr = AsyncMock(return_value=121)
    redis.expire = AsyncMock()
    redis.decr = AsyncMock()
    redis.ttl = AsyncMock(return_value=30)

    with (
        patch("backend.modules.orchestration.execution.execution_service.settings.APP_ENV", "staging"),
        patch("backend.modules.orchestration.execution.execution_service.settings.ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE", 120),
        patch("backend.modules.orchestration.execution.execution_service.redis_client", redis),
    ):
        with pytest.raises(HTTPException) as exc:
            await harness._enforce_orchestration_run_rate_limit("user-1")

    assert exc.value.status_code == 429
    assert exc.value.headers.get("Retry-After") == "30"
