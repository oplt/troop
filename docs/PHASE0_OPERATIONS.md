# Phase 0 Operations Contract

This document describes the baseline and context contracts implemented for the
Phase 0 modernization work.

## Baseline capture

Run from the repository root with the API and optional dependencies available:

```bash
python backend/tools/phase0_baseline.py \
  --url http://127.0.0.1:8000/health/live \
  --url http://127.0.0.1:8000/health/ready \
  --pid "$(pgrep -f 'uvicorn.*backend.api.main' | head -1)" \
  --redis-url "${REDIS_URL:-redis://127.0.0.1:6379/0}" \
  --queue "${CELERY_TASK_DEFAULT_QUEUE:-default}" \
  --output artifacts/phase0-baseline.json
```

The report includes endpoint p50/p95/p99, status counts, Redis `PING` timing,
`SELECT 1` timing when `DATABASE_URL` is available, Redis queue depth, process
CPU, RSS, repository revision, and the exact sampling parameters. Endpoint
failures are recorded in the artifact rather than represented as zero-latency
successes.

After a frontend build:

```bash
cd frontend
pnpm run build
pnpm run baseline:build -- --output ../artifacts/frontend-baseline.json
```

That report records total output, JavaScript/CSS bytes, file count, and the 20
largest assets. It is a build baseline, not a substitute for browser traces or
real-device Core Web Vitals.

## Context fields

`backend/core/request_context.py` is the canonical allowlist. The fields are:

| Field | Established by | Propagated to |
| --- | --- | --- |
| `request_id` | `X-Request-ID`, or generated from the correlation ID | request logs, response header, Celery headers |
| `correlation_id` | `X-Correlation-ID`, or generated UUID | request logs, response header, Celery headers |
| `trace_id`, `span_id` | reserved for tracing integration | logs and Celery headers when available |
| `user_id` | authenticated-user dependency | request logs and Celery headers |
| `tenant_id` | authenticated tenant boundary when available | logs and Celery headers |
| `project_id` | enqueue/run boundary when available | logs and Celery headers |
| `task_id` | task/run boundary when available | logs and Celery headers |
| `run_id` | orchestration enqueue boundary | logs and Celery headers |
| `job_id` | Celery task runtime | worker logs |
| `task_name` | Celery task runtime | worker logs |

Only identifiers are allowed. Never put cookies, access tokens, provider keys,
prompts, memory bodies, document text, or tool payloads in context. Values are
stripped of control characters and capped at 128 characters before they are
stored, echoed, or sent as task headers.

The HTTP middleware binds request and correlation context for the duration of a
request and resets it even when the handler raises. Authenticated dependencies
add `user_id`. Celery enqueue helpers copy the allowlisted context into message
headers; Celery prerun/postrun signals bind and reset that context in the worker.

## CI gate

The quality workflow runs backend non-integration tests, Ruff checks and format
validation, the RAG evaluation gate, frontend typecheck, lint, tests, build,
and build-size baseline generation. Integration tests remain a separate local
or environment-backed command because they require PostgreSQL and Redis.
