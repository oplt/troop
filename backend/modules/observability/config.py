"""Configuration boundary for application observability."""

from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import settings


@dataclass(frozen=True, slots=True)
class ObservabilityConfig:
    enabled: bool
    metrics_enabled: bool
    metrics_public: bool
    readiness_timeout_seconds: float
    otlp_endpoint: str
    otlp_insecure: bool
    sentry_dsn: str
    sentry_sample_rate: float

    @classmethod
    def from_settings(cls) -> ObservabilityConfig:
        return cls(
            enabled=settings.OBSERVABILITY_ENABLED,
            metrics_enabled=settings.METRICS_ENABLED,
            metrics_public=settings.METRICS_PUBLIC,
            readiness_timeout_seconds=settings.HEALTH_READY_TIMEOUT_SECONDS,
            otlp_endpoint=settings.OTLP_ENDPOINT,
            otlp_insecure=settings.OTLP_INSECURE,
            sentry_dsn=settings.SENTRY_DSN,
            sentry_sample_rate=settings.SENTRY_TRACES_SAMPLE_RATE,
        )
