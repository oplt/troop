"""P3 API / worker / AI architecture smoke tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException


def test_langgraph_shim_removed():
    assert not Path(
        "backend/modules/orchestration/execution/langgraph_runner.py"
    ).exists()
    from backend.core import config as app_config

    assert not hasattr(app_config.settings, "ORCHESTRATION_USE_LANGGRAPH")


def test_shared_gateway_pricing_module():
    from backend.modules.ai.gateway.pricing import estimate_cost_micros, estimate_tokens
    from backend.modules.orchestration.providers import estimate_tokens as orch_estimate_tokens

    assert estimate_tokens("abcd") == orch_estimate_tokens("abcd")
    assert estimate_cost_micros(None, 1000, 500) == 2_000_000


def test_apply_result_metrics_append_sums_per_call_cost():
    from backend.modules.orchestration.execution.execution_service import (
        OrchestrationExecutionServiceMixin,
    )
    from backend.modules.orchestration.providers import ProviderExecutionResult

    service = OrchestrationExecutionServiceMixin.__new__(OrchestrationExecutionServiceMixin)
    service._estimate_cost_micros = MagicMock(side_effect=[100, 200])
    run = SimpleNamespace(
        token_input=0,
        token_output=0,
        token_total=0,
        latency_ms=0,
        estimated_cost_micros=50,
        model_name="model-a",
    )
    results = [
        ProviderExecutionResult(
            model_name="cheap",
            output_text="a",
            output_json=None,
            input_tokens=10,
            output_tokens=5,
            latency_ms=1,
        ),
        ProviderExecutionResult(
            model_name="expensive",
            output_text="b",
            output_json=None,
            input_tokens=20,
            output_tokens=10,
            latency_ms=2,
        ),
    ]

    import asyncio

    asyncio.run(
        service._apply_result_metrics(run, None, results, append=True)
    )

    assert run.estimated_cost_micros == 350
    assert service._estimate_cost_micros.call_count == 2


def test_execute_run_rejects_owner_mismatch():
    from backend.modules.orchestration.execution.execution_service import (
        OrchestrationExecutionServiceMixin,
    )

    service = OrchestrationExecutionServiceMixin.__new__(OrchestrationExecutionServiceMixin)
    run = SimpleNamespace(
        id="run-1",
        status="queued",
        project_id="proj-1",
        run_mode="single_agent",
        task_id=None,
        checkpoint_json={},
        worker_agent_id=None,
        orchestrator_agent_id=None,
    )
    project = SimpleNamespace(owner_id="owner-a")
    service.repo = SimpleNamespace(get_run_for_worker=AsyncMock(return_value=run))
    service.db = MagicMock()
    service.db.get = AsyncMock(return_value=project)
    service._ensure_run_workflow = MagicMock(return_value={"backend": "celery"})
    service._emit_run_event = AsyncMock()

    import asyncio

    with pytest.raises(RuntimeError, match="owner mismatch"):
        asyncio.run(
            service.execute_run("run-1", expected_owner_id="owner-b")
        )


def test_delete_skill_pack_returns_410():
    from backend.modules.team.service import TeamService

    service = TeamService.__new__(TeamService)

    import asyncio

    with pytest.raises(HTTPException) as exc:
        asyncio.run(service.delete_skill_pack("legacy-pack"))

    assert exc.value.status_code == 410


def test_webhook_secret_encrypted_at_rest():
    from backend.modules.orchestration.security import decrypt_secret, encrypt_secret
    from backend.modules.platform.webhooks.signing import webhook_signing_secret

    raw = "whsec-test-signing-key"
    stored = encrypt_secret(raw)
    assert stored != raw
    assert webhook_signing_secret(stored) == raw
    assert webhook_signing_secret(raw) == raw


def test_compatibility_module_deleted():
    assert not Path("backend/modules/workforce/services/compatibility.py").exists()


def test_submit_orchestration_run_accepts_owner_kwarg():
    import inspect

    from backend.modules.orchestration.execution.durable_execution import submit_orchestration_run

    sig = inspect.signature(submit_orchestration_run)
    assert "expected_owner_id" in sig.parameters


def test_run_orchestration_task_accepts_owner_kwarg():
    import inspect

    from backend.workers.orchestration import run_orchestration_task

    sig = inspect.signature(run_orchestration_task)
    assert "expected_owner_id" in sig.parameters


def test_queue_orchestration_run_forwards_owner_to_celery():
    from backend.workers import orchestration as orch_workers

    with (
        patch.object(orch_workers.settings, "CELERY_TASK_ALWAYS_EAGER", False),
        patch.object(orch_workers.run_orchestration_task, "apply_async") as apply_async,
    ):
        orch_workers.queue_orchestration_run("run-1", expected_owner_id="owner-a")

    apply_async.assert_called_once()
    assert apply_async.call_args.kwargs["kwargs"]["expected_owner_id"] == "owner-a"
