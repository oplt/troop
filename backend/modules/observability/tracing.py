"""Optional OpenTelemetry setup and no-op span compatibility helpers."""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager, nullcontext
from typing import Any

from backend.core.logging import get_logger
from backend.core.request_context import set_context

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
        logger.info("observability.tracing_enabled endpoint=%s service=%s", endpoint, service_name)
    except ImportError:
        logger.warning("observability.otel_unavailable endpoint=%s", endpoint)
    except Exception:
        logger.exception("observability.otel_setup_failed endpoint=%s", endpoint)


def current_trace_context() -> dict[str, str | None]:
    """Return hex trace/span ids from the active OTel span, if any."""
    try:
        from opentelemetry import trace

        span = trace.get_current_span()
        ctx = span.get_span_context() if span is not None else None
        if ctx is None or not ctx.is_valid:
            return {"trace_id": None, "span_id": None}
        return {
            "trace_id": format(ctx.trace_id, "032x"),
            "span_id": format(ctx.span_id, "016x"),
        }
    except ImportError:
        return {"trace_id": None, "span_id": None}


def bind_active_trace_context() -> None:
    """Mirror the active OTel span into request context for logs and Celery headers."""
    ctx = current_trace_context()
    if ctx["trace_id"]:
        set_context(trace_id=ctx["trace_id"], span_id=ctx["span_id"])


def enrich_with_trace_context(payload: Mapping[str, Any] | None) -> dict[str, Any]:
    """Attach trace identifiers to run-event payloads when available."""
    merged = dict(payload or {})
    for key, value in current_trace_context().items():
        if value and key not in merged:
            merged[key] = value
    return merged


@contextmanager
def span(name: str, attributes: Mapping[str, Any] | None = None) -> Iterator[Any]:
    """Start a span when OTel is available, otherwise remain a no-op."""
    try:
        from opentelemetry import trace

        tracer = trace.get_tracer("troop")
        with tracer.start_as_current_span(name, attributes=dict(attributes or {})) as current:
            bind_active_trace_context()
            yield current
    except ImportError:
        with nullcontext():
            yield None


@contextmanager
def celery_task_span(task_name: str, *, task_id: str | None = None) -> Iterator[Any]:
    attrs: dict[str, Any] = {"celery.task": task_name}
    if task_id:
        attrs["celery.task_id"] = task_id
    with span("celery.task", attrs) as current:
        yield current


@contextmanager
def llm_invoke_span(
    *,
    purpose: str,
    provider: str,
    model: str,
) -> Iterator[Any]:
    with span(
        "llm.invoke",
        {
            "llm.purpose": purpose,
            "llm.provider": provider,
            "llm.model": model,
        },
    ) as current:
        yield current


def record_llm_span_result(
    span: Any,
    *,
    input_tokens: int,
    output_tokens: int,
    result: str,
) -> None:
    if span is None:
        return
    try:
        span.set_attribute("llm.input_tokens", int(input_tokens))
        span.set_attribute("llm.output_tokens", int(output_tokens))
        span.set_attribute("llm.result", result)
    except Exception:
        return


__all__ = [
    "bind_active_trace_context",
    "celery_task_span",
    "current_trace_context",
    "enrich_with_trace_context",
    "llm_invoke_span",
    "record_llm_span_result",
    "setup_sentry",
    "setup_tracing",
    "span",
]
