"""Compatibility shim for the consolidated observability module."""

from typing import Any

from backend.modules.observability.instrumentation import setup_observability
from backend.modules.observability.tracing import setup_sentry, setup_tracing


def setup_telemetry(app: Any = None) -> None:
    """Keep the historical startup hook while delegating to Phase 2 ports."""
    setup_observability(app)


def _setup_sentry(dsn: str, environment: str, traces_sample_rate: float) -> None:
    """Compatibility helper for callers that imported the old private hook."""
    setup_sentry(dsn, environment, traces_sample_rate)


def _setup_otel(endpoint: str, service_name: str, insecure: bool, app: Any = None) -> None:
    """Compatibility helper for callers that imported the old private hook."""
    setup_tracing(endpoint, service_name, insecure, app)
