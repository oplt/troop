# Phase 3 cache and query operations

Phase 3 adds a typed cache contract while keeping `backend.core.cache` as the
compatibility import surface. Redis remains the current provider; callers use
`CachePolicy`, `CacheStore`, `cache_get_or_set_json`, and
`cache_singleflight` instead of depending on Redis commands for read-through
behavior.

## Cache policy

Cache policies are named and bounded in `backend/core/cache.py`. The name is
the only cache metric label. User, project, session, document, and query
identifiers must never be metric labels or log fields.

Every normal TTL receives small jitter to avoid synchronized expiry. Negative
results use a shorter policy TTL where configured. A cache outage is fail-open
for safe reads: the database/provider path remains authoritative. Cache
failures must not grant authorization; ACL callers treat a cache error as a
miss and evaluate the source of truth.

## Invalidation

RAG retrieval, project ACL, and project memory-context keys use a Redis
namespace generation. A write increments the generation, making old keys
unreadable without scanning the namespace. Legacy pattern deletion remains
available only for bounded cleanup paths such as user-session cleanup and
deletes in batches of 200 through a non-transactional Redis pipeline.

Generation invalidation is compatible with multiple API processes because the
generation is stored in Redis. Old keys expire under their original TTL and
can be removed during normal Redis maintenance.

## Stampede control

`cache_singleflight` and `cache_get_or_set_json` coalesce only safe expensive
fills. RAG vector retrieval and embedding batches use a process-local
single-flight lock and re-check Redis after acquiring it. Authorization checks
are not single-flighted across users. The single-flight table is bounded and
does not replace durable distributed locking for jobs.

## Query and pagination policy

The orchestration task and run list endpoints now expose explicit bounded
`limit` parameters. The orchestration task page loads its dependency graph in
one SQL statement using a limited task-id subquery followed by an outer join;
this avoids per-task dependency queries without truncating dependency rows.
The legacy project task endpoint also has a bounded default and maximum.

Existing single-column indexes cover the verified filters. Composite indexes
are intentionally not added until representative PostgreSQL plans confirm a
sort or scan bottleneck. Capture a plan on representative data with:

```sql
EXPLAIN (ANALYZE, BUFFERS)
SELECT ...
FROM orchestrator_tasks
WHERE project_id = '<project-id>'
ORDER BY position ASC, created_at ASC
LIMIT 500;
```

Use the database query metrics exposed by Phase 2 to compare p50/p95/p99
durations before and after any measured migration. Do not run `EXPLAIN
(ANALYZE, BUFFERS)` against production without an approved maintenance window
or a safe replica plan.

## Validation

The cache contract tests cover 100-way concurrent misses, generation-based
ACL/RAG freshness, TTL-safe round trips, and provider embedding reuse. The
query-path test asserts one bounded task/dependency statement. Run the Phase 3
subset with:

```bash
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
PYTEST_PLUGINS=pytest_asyncio.plugin \
DATABASE_URL=postgresql+asyncpg://postgres:postgres@127.0.0.1:5432/app \
REDIS_URL=redis://127.0.0.1:6379/0 \
JWT_SECRET=ci-only-secret-not-for-production \
JWT_ALGORITHM=HS256 ACCESS_TOKEN_EXPIRE_MINUTES=30 \
REFRESH_TOKEN_EXPIRE_DAYS=30 CELERY_TASK_ALWAYS_EAGER=true \
backend/.venv/bin/python -m pytest \
  backend/tests/test_cache_layer.py backend/tests/test_phase3_query_paths.py -q
```
