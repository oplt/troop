# Application observability

This package is the compatibility boundary for application instrumentation.
It owns bounded process metrics, HTTP/worker/database instrumentation,
readiness checks, optional tracing, and the Prometheus scrape route.

The existing `backend.core.telemetry` module remains a compatibility shim and
delegates initialization here. Exporters are optional: unset `OTLP_ENDPOINT`
and `SENTRY_DSN` do not change application startup, and missing optional
packages are logged once and ignored.

Metric labels are deliberately limited to route templates, HTTP methods,
status classes, operation names, provider types, queue categories, task names,
and outcomes. User IDs, run IDs, project IDs, prompts, document IDs, and
credentials belong in logs/traces only when operationally justified.

## Tracing (optional OTLP)

Set `OTLP_ENDPOINT` (gRPC, e.g. `http://localhost:4317`) and optionally
`OTLP_INSECURE=true` for local collectors. API processes export FastAPI +
SQLAlchemy spans; Celery workers export `celery.task` spans when the same env
is present at worker boot.

Additional spans:

- `llm.invoke` — provider, model, purpose, token counts, result
- Run events include `trace_id` / `span_id` in `payload_json` when a span is active

Celery enqueue calls `task_context_headers()` which propagates `trace_id` and
`span_id` in message headers for cross-process correlation.

Smoke check:

```bash
curl -s http://127.0.0.1:8000/health/live
# then inspect collector for service.name=troop and llm.invoke / celery.task spans
```
