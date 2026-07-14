"""Versioned service-level objectives used by dashboards and alert rules."""

from __future__ import annotations

from dataclasses import asdict, dataclass


@dataclass(frozen=True, slots=True)
class ServiceLevelObjective:
    name: str
    target: float
    window: str
    owner: str
    severity: str
    indicator: str
    runbook: str

    @property
    def error_budget(self) -> float:
        return round(1.0 - self.target, 6)


SLO_DEFINITIONS: tuple[ServiceLevelObjective, ...] = (
    ServiceLevelObjective(
        name="api_availability",
        target=0.995,
        window="30d",
        owner="platform",
        severity="page",
        indicator="HTTP 5xx ratio",
        runbook="docs/PHASE7_OPERATIONS.md#api-availability",
    ),
    ServiceLevelObjective(
        name="api_p95_latency",
        target=0.95,
        window="30d",
        owner="platform",
        severity="ticket",
        indicator="HTTP p95 duration <= 1.5s",
        runbook="docs/PHASE7_OPERATIONS.md#api-latency",
    ),
    ServiceLevelObjective(
        name="run_success",
        target=0.95,
        window="30d",
        owner="orchestration",
        severity="page",
        indicator="completed / terminal runs",
        runbook="docs/PHASE7_OPERATIONS.md#run-success",
    ),
    ServiceLevelObjective(
        name="provider_reliability",
        target=0.90,
        window="30d",
        owner="ai-platform",
        severity="ticket",
        indicator="successful provider calls",
        runbook="docs/PHASE7_OPERATIONS.md#provider-reliability",
    ),
    ServiceLevelObjective(
        name="memory_retrieval_latency",
        target=0.95,
        window="30d",
        owner="memory",
        severity="ticket",
        indicator="memory retrieval p95 <= 1.0s",
        runbook="docs/PHASE7_OPERATIONS.md#memory-retrieval",
    ),
)


def slo_catalog() -> list[dict[str, object]]:
    return [asdict(item) | {"error_budget": item.error_budget} for item in SLO_DEFINITIONS]


__all__ = ["SLO_DEFINITIONS", "ServiceLevelObjective", "slo_catalog"]
