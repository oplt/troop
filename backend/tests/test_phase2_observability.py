from __future__ import annotations

from contextlib import asynccontextmanager

import pytest
from backend.api.main import app
from backend.api.v1 import health as health_module
from backend.modules.observability.health import readiness_report
from backend.modules.observability.metrics import (
    HTTP_ACTIVE,
    MetricsRegistry,
    bounded_route,
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
