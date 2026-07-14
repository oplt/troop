# Phase 4 operations: bounded async execution

Phase 4 establishes explicit ownership and backpressure for long-lived async work.

## HTTP clients

External provider, GitHub, webhook, platform, and local-runtime calls use
`backend.core.http_clients.managed_http_client`. The pool is process-local, keyed
by integration purpose/base URL/timeout, and bounded by
`EXTERNAL_HTTP_MAX_CLIENTS`. FastAPI closes it during application shutdown and
Celery closes it during worker shutdown. Authentication headers remain per
request; callers must not mutate shared client headers.

## Worker queues and shutdown

Celery routes provider calls, GitHub work, CPU work, observability, email, and
default orchestration work to separate logical queues. `task_acks_late` and
`task_reject_on_worker_lost` preserve at-least-once delivery for tasks that are
safe to retry. Tasks must therefore remain idempotent and persist durable
checkpoints before acknowledging progress. `worker_prefetch_multiplier=1`
prevents a worker from reserving a large batch it cannot service promptly.

Soft and hard time limits are configured globally as a safety net. A deployment
may tune them per worker class, but should keep the broker visibility timeout
longer than the hard limit plus the expected shutdown/drain window.

Recommended worker groups are independently deployable, for example:

```text
celery -A backend.workers.celery_app.celery_app worker -Q default,observability --concurrency=4
celery -A backend.workers.celery_app.celery_app worker -Q model_gateway --concurrency=4
celery -A backend.workers.celery_app.celery_app worker -Q github --concurrency=2
celery -A backend.workers.celery_app.celery_app worker -Q cpu --pool=solo --concurrency=1
```

The exact counts require load measurement. CPU workers should be sized for the
host, while model/GitHub workers should be sized for provider rate limits and
connection budgets. Email remains isolated through `CELERY_EMAIL_QUEUE`.

## RAG bulk ingestion

`bulk_ingest_documents_parallel` processes bounded batches instead of creating a
task for every input document. `RAG_BULK_INGEST_CONCURRENCY` limits active
embedding/database operations and `RAG_BULK_INGEST_BATCH_SIZE` limits scheduled
work. Cancellation cancels and drains child tasks before propagating, and each
completed batch emits progress telemetry. The request limit remains bounded by
`RAG_BULK_INGEST_MAX_DOCUMENTS`.

## SSE streams

Live snapshot streams use a process-local connection semaphore, emit compact
heartbeats, stop after `SSE_MAX_DURATION_SECONDS`, reject excess connections
with `503 Retry-After`, and check client disconnects before polling. Responses
disable intermediary buffering. The browser hook aborts both the active fetch
and any reconnect delay on unmount or route changes, so reconnect timers cannot
keep a stale stream alive.

Monitor `troop_sse_connections` and `troop_sse_events_total` by bounded stream
and event labels. Resource identifiers belong in logs/traces, not metric labels.
