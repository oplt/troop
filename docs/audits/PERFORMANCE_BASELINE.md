# Performance baseline

Captured on 22 August 2026 before the remediation performance work.

## Current evidence

| Signal | Baseline | Source |
| --- | ---: | --- |
| Frontend production assets | 2,588,110 bytes | `artifacts/frontend-build-baseline.json` |
| Frontend JavaScript | 2,136,474 bytes | `artifacts/frontend-build-baseline.json` |
| AI Studio lazy route | 35,688 bytes | Vite build output |
| Project detail lazy route | 115,552 bytes | Vite build output |
| Run inspector lazy route | 48,876 bytes | Vite build output |
| Live API p50/p95/p99 | unavailable | No API process is reachable in this workspace |
| PostgreSQL query timing/count | unavailable | PostgreSQL is not reachable in this workspace |
| Redis/cache sampling | unavailable | Socket access to Redis is unavailable in this workspace |

Unavailable measurements remain explicit in `artifacts/phase0-baseline.json`. They are not represented as zero. Run the same harness against a seeded environment before accepting latency or query-count changes.

## Representative workloads

The backend harness records p50, p95, p99, SQL count, process CPU/RSS, queue depth, Redis latency, and database latency for:

- dashboard overview;
- project detail;
- task detail;
- AI Studio overview;
- semantic memory;
- RAG search;
- agent run detail;
- evaluation datasets.

Runtime telemetry exposes HTTP and SQL duration/count, provider/LLM latency, embedding latency and tokens, RAG/memory retrieval latency, cache outcomes for hit-ratio calculation, and selected context token count. Frontend page request counts are captured with `pnpm baseline:requests`.

## Reproduction

```bash
PYTHONPATH=. python backend/tools/phase0_baseline.py \
  --url http://127.0.0.1:8000/api/v1/orchestration/overview \
  --url http://127.0.0.1:8000/api/v1/ai/overview \
  --in-process --owner-id <seeded-owner-id> --samples 20 \
  --output artifacts/phase0-baseline.json

cd frontend
pnpm build
pnpm baseline:build -- --output ../artifacts/frontend-build-baseline.json
pnpm baseline:requests -- \
  --storage-state playwright/.auth/user.json \
  --route /dashboard --route /projects/<seeded-project-id> --route /ai \
  --output ../artifacts/frontend-request-baseline.json
```

Performance changes must attach a before/after artifact captured with the same seed data, process topology, sample count, and concurrency.
