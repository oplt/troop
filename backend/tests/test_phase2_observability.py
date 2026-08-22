from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from backend.api.main import app
from backend.api.v1 import health as health_module
from backend.modules.observability.health import readiness_report
from backend.modules.observability.metrics import (
    CONTEXT_TOKENS,
    EMBED_DURATION,
    EMBED_TOKENS,
    HTTP_ACTIVE,
    LLM_ATTEMPTS,
    LLM_COST_MICROS,
    RAG_RETRIEVAL_DURATION,
    MetricsRegistry,
    bounded_route,
    metrics_registry,
    record_context_tokens,
    record_embed_tokens,
    record_embedding_duration,
    record_llm_attempt,
    record_llm_cost_micros,
    record_rag_retrieval_duration,
)
from httpx import ASGITransport, AsyncClient


def test_metrics_registry_renders_bounded_prometheus_samples() -> None:
    registry = MetricsRegistry()
    registry.increment(
        "troop_test_requests_total",
        help_text="Test requests.",
        labels={"route": bounded_route("/projects/12345678/tasks/987")},
    )
    registry.observe(
        "troop_test_duration_seconds",
        0.02,
        help_text="Test duration.",
        labels={"route": "/projects/{id}"},
    )

    rendered = registry.render_prometheus()

    assert "# TYPE troop_test_requests_total counter" in rendered
    assert 'route="/projects/{id}/tasks/{id}"' in rendered
    assert "12345678" not in rendered
    assert "troop_test_duration_seconds_bucket" in rendered


def test_active_gauge_is_clamped_at_zero() -> None:
    registry = MetricsRegistry()
    registry.increment_gauge(
        HTTP_ACTIVE,
        help_text="Active requests.",
        labels={},
        delta=-1,
    )

    snapshot = registry.snapshot()
    assert snapshot[HTTP_ACTIVE]["values"][()] == 0


def test_ai_latency_and_context_metrics_are_recorded() -> None:
    metrics_registry.reset()
    record_embedding_duration(provider="local", outcome="success", duration_seconds=0.25)
    record_context_tokens(pipeline="rag", tokens=750)
    record_rag_retrieval_duration(
        stage="vector_search",
        outcome="success",
        duration_seconds=0.12,
    )

    snapshot = metrics_registry.snapshot()

    assert snapshot[EMBED_DURATION]["histograms"]
    assert snapshot[CONTEXT_TOKENS]["histograms"]
    assert snapshot[RAG_RETRIEVAL_DURATION]["histograms"]


class _HealthyConnection:
    async def execute(self, _query) -> None:
        return None


class _HealthyEngine:
    @asynccontextmanager
    async def connect(self):
        yield _HealthyConnection()


class _HealthyRedis:
    async def ping(self) -> bool:
        return True


class _BrokenRedis:
    async def ping(self) -> bool:
        raise ConnectionError("redis unavailable")


@pytest.mark.asyncio
async def test_readiness_report_is_ready_when_required_dependencies_are_healthy() -> None:
    report = await readiness_report(
        _HealthyEngine(),
        _HealthyRedis(),
        "redis://localhost:6379/0",
        0.2,
    )

    assert report["status"] == "ok"
    assert report["checks"]["db"]["status"] == "ok"
    assert report["checks"]["queue"]["required"] is True


@pytest.mark.asyncio
async def test_readiness_report_is_not_ready_on_dependency_failure() -> None:
    report = await readiness_report(
        _HealthyEngine(),
        _BrokenRedis(),
        "redis://localhost:6379/0",
        0.2,
    )

    assert report["status"] == "not_ready"
    assert report["checks"]["redis"]["status"] == "error"
    assert report["checks"]["queue"]["status"] == "error"


@pytest.mark.asyncio
async def test_metrics_endpoint_exposes_prometheus_content() -> None:
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/metrics")

    assert response.status_code == 200
    assert "# TYPE" in response.text or response.text == ""


@pytest.mark.asyncio
async def test_readiness_endpoint_returns_503_when_redis_is_unavailable(monkeypatch) -> None:
    monkeypatch.setattr(health_module, "engine", _HealthyEngine())
    monkeypatch.setattr(health_module, "redis_client", _BrokenRedis())
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url="http://testserver"
    ) as client:
        response = await client.get("/health/ready")

    assert response.status_code == 503
    assert response.json()["detail"]["status"] == "not_ready"


def test_registry_label_shape_is_explicit() -> None:
    registry = MetricsRegistry()
    registry.increment("troop_shape_total", help_text="Shape.", labels={"kind": "ok"})
    with pytest.raises(ValueError, match="incompatible shape"):
        registry.increment("troop_shape_total", help_text="Shape.", labels={})


def test_ai_metrics_render_purpose_provider_and_cost() -> None:
    metrics_registry.reset()
    record_llm_attempt(purpose="agent_plan", provider="openai_compatible", result="success")
    record_llm_attempt(purpose="agent_plan", provider="openai_compatible", result="error")
    record_llm_cost_micros(purpose="agent_plan", provider="openai_compatible", micros=1250)
    record_embed_tokens(provider="openai", tokens=512, outcome="success")

    rendered = metrics_registry.render_prometheus()

    assert f"# TYPE {LLM_ATTEMPTS} counter" in rendered
    assert 'purpose="agent_plan"' in rendered
    assert 'provider="openai_compatible"' in rendered
    assert 'result="success"' in rendered
    assert f"# TYPE {LLM_COST_MICROS} counter" in rendered
    assert f"{LLM_COST_MICROS}" in rendered and "1250" in rendered
    assert f"# TYPE {EMBED_TOKENS} counter" in rendered
    assert 'provider="openai"' in rendered
    metrics_registry.reset()


@pytest.mark.asyncio
async def test_execute_prompt_records_direct_path_metrics(monkeypatch) -> None:
    from backend.modules.orchestration.providers import ProviderExecutionResult, execute_prompt

    metrics_registry.reset()
    stub = ProviderExecutionResult(
        model_name="gpt-test",
        output_text="ok",
        output_json=None,
        input_tokens=10,
        output_tokens=5,
        latency_ms=12,
    )

    async def fake_impl(*_args, **_kwargs):
        return stub

    monkeypatch.setattr(
        "backend.modules.orchestration.providers._execute_prompt_impl",
        fake_impl,
    )
    await execute_prompt(
        None,
        model_name="local-heuristic",
        system_prompt="sys",
        user_prompt="usr",
        purpose="health_probe",
    )
    rendered = metrics_registry.render_prometheus()
    assert 'purpose="health_probe"' in rendered
    assert 'provider="local-heuristic"' in rendered
    metrics_registry.reset()
