"""Optional OpenTelemetry setup and no-op span compatibility helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from typing import Any

from backend.core.logging import get_logger

logger = get_logger(__name__)
_configured = False
_sentry_configured = False


def setup_sentry(dsn: str, environment: str, traces_sample_rate: float) -> None:
    global _sentry_configured
    if _sentry_configured or not dsn:
        return
    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration

        sentry_sdk.init(
            dsn=dsn,
            environment=environment,
            traces_sample_rate=traces_sample_rate,
            integrations=[FastApiIntegration(), SqlalchemyIntegration()],
        )
        _sentry_configured = True
        logger.info("observability.sentry_enabled environment=%s", environment)
    except ImportError:
        logger.warning("observability.sentry_unavailable environment=%s", environment)
    except Exception:
        logger.exception("observability.sentry_setup_failed environment=%s", environment)


def setup_tracing(endpoint: str, service_name: str, insecure: bool, app: Any = None) -> None:
    global _configured
    if _configured or not endpoint:
        return
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.grpc.trace_exporter import OTLPSpanExporter
        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor
        from opentelemetry.instrumentation.sqlalchemy import SQLAlchemyInstrumentor
        from opentelemetry.sdk.resources import SERVICE_NAME, Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor

        from backend.db.session import engine

        provider = TracerProvider(resource=Resource(attributes={SERVICE_NAME: service_name}))
        provider.add_span_processor(
            BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, insecure=insecure))
        )
        trace.set_tracer_provider(provider)
        if app is not None and not getattr(app.state, "troop_otel_instrumented", False):
            FastAPIInstrumentor.instrument_app(app)
            app.state.troop_otel_instrumented = True
        SQLAlchemyInstrumentor().instrument(engine=engine.sync_engine)
        _configured = True
        logger.info("observability.tracing_enabled endpoint=%s", endpoint)
    except ImportError:
        logger.warning("observability.otel_unavailable endpoint=%s", endpoint)
    except Exception:
        logger.exception("observability.otel_setup_failed endpoint=%s", endpoint)


@contextmanager
def span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
    """Start a span when OTel is available, otherwise remain a no-op."""
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("troop")
        with tracer.start_as_current_span(name, attributes=dict(attributes or {})) as current:
            yield current
    except ImportError:
        with nullcontext():
            yield None


__all__ = ["setup_sentry", "setup_tracing", "span"]
