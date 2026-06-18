# Deployment Runbook

## Required Services

- Postgres with `pgvector` enabled.
- Redis for cache, rate limits, and Celery broker/result backend.
- FastAPI web process.
- Celery workers for orchestration/default, model gateway, memory, GitHub sync, and evaluation queues.
- Celery beat for scheduled orchestration and memory maintenance jobs.

## Release Checks

Run these before deploy:

```bash
cd backend
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -p pytest_asyncio.plugin \
  tests/test_orchestration_domain_services.py \
  tests/test_golden_retrieval.py \
  tests/test_error_payloads.py
.venv/bin/python -m backend.tools.rag_eval_gate tests/fixtures/rag_eval_golden.json --min-pass-rate 1.0

cd ../frontend
pnpm exec tsc --noEmit
pnpm exec vitest run src/pages/DashboardPage.test.tsx src/pages/OrchestrationProjectDetailPage.test.tsx
```

## Database And pgvector

Apply migrations before starting new workers. Confirm the HNSW indexes exist:

- `ix_project_document_chunks_embedding_hnsw`
- `ix_semantic_memory_entries_embedding_hnsw`
- `ix_episodic_search_index_embedding_hnsw`
- `ix_ai_document_chunks_embedding_hnsw`

Validate query plans on a production-like project with at least 10k chunks:

```bash
cd backend
.venv/bin/python -m backend.tools.pgvector_plan_check \
  --project-id "$PROJECT_ID" \
  --database-url "$DATABASE_URL" \
  --require-index
```

Expected result: JSON output shows each expected index exists and the vector plans use the index. If a plan chooses a sequential scan, run `ANALYZE`, verify chunk count/selectivity, and tune pgvector index settings before release.

## Celery Topology

Run separate worker pools for latency-sensitive model work and background ingest:

```bash
celery -A backend.workers.celery_app worker -Q orchestration,default --concurrency 4
celery -A backend.workers.celery_app worker -Q model_gateway --concurrency 2
celery -A backend.workers.celery_app worker -Q memory --concurrency 2
celery -A backend.workers.celery_app worker -Q github --concurrency 2
celery -A backend.workers.celery_app beat
```

Tune concurrency from DB pool limits, provider rate limits, and observed queue latency. Keep model gateway workers smaller than provider concurrency caps.

## Load Testing

Before large releases, test:

- Concurrent task runs with SSE listeners attached.
- Document ingest backlog while users query RAG.
- Memory extraction plus semantic/episodic embedding batches.
- Approval flows during active runs.

Minimum smoke:

```bash
cd backend
.venv/bin/python -m backend.tools.pgvector_plan_check --project-id "$PROJECT_ID" --require-index
.venv/bin/python -m backend.tools.rag_eval_gate tests/fixtures/rag_eval_golden.json --min-pass-rate 1.0
```

Monitor Postgres active connections, Redis queue depth, Celery task latency, RAG answer latency, and frontend route errors.

## Observability

Set these in production:

- `SENTRY_DSN`
- `SENTRY_TRACES_SAMPLE_RATE`
- `OTLP_ENDPOINT`
- `OTLP_INSECURE` only for trusted internal collectors

Backend traces cover FastAPI and SQLAlchemy when OTLP is configured. Route error boundaries tag frontend Sentry events with route and project id when a browser Sentry client is present.

## Rollback

1. Stop new web traffic.
2. Drain Celery queues or pause workers.
3. Roll back app images.
4. Roll back migrations only when the migration is marked reversible and no new writes depend on it.
5. Re-run RAG eval gate and pgvector plan check before restoring traffic.
