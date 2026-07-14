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
