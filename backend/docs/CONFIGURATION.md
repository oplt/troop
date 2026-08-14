# Configuration and feature flags

Troop loads settings from `backend/.env` and optional repo-root `.env` (see `core/config.py`). This document lists **supported** toggles and deployment defaults. Unsupported or removed paths are called out so prod does not accidentally enable legacy fallbacks.

## Required (every environment)

| Variable | Purpose |
|----------|---------|
| `DATABASE_URL` | Async PostgreSQL URL (`postgresql+asyncpg://…`) |
| `REDIS_URL` | Broker, cache, rate limits, distributed locks |
| `JWT_SECRET` | ≥32 chars, high entropy (not `replace-me`) |
| `JWT_ALGORITHM` | Usually `HS256` |
| `ACCESS_TOKEN_EXPIRE_MINUTES` | 1–30 |
| `REFRESH_TOKEN_EXPIRE_DAYS` | 1–30 |

## Connection pools (pin in staging/prod)

Total DB connections ≈ **process count × (`POOL_SIZE` + `MAX_OVERFLOW`)** per role.

| Variable | Default | Notes |
|----------|---------|-------|
| `DATABASE_POOL_SIZE` | 10 | API / web processes |
| `DATABASE_MAX_OVERFLOW` | 20 | Burst above pool size |
| `DATABASE_POOL_SIZE_WORKER` | 5 | Celery workers |
| `DATABASE_MAX_OVERFLOW_WORKER` | 5 | Worker burst |
| `DATABASE_PROCESS_ROLE` | `auto` | `api`, `worker`, or `auto` (detect Celery argv) |
| `DATABASE_POOL_RECYCLE_SECONDS` | 1800 | Recycle stale connections |
| `DATABASE_POOL_TIMEOUT_SECONDS` | 10 | Wait for checkout |
| `REDIS_MAX_CONNECTIONS` | 50 | Shared Redis client pool |
| `REDIS_SOCKET_CONNECT_TIMEOUT_SECONDS` | 2.0 | Connect timeout |
| `REDIS_SOCKET_TIMEOUT_SECONDS` | 5.0 | Command timeout |

Empty `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` fall back to `REDIS_URL`.

## Supported feature flags

### Orchestration execution

| Flag | Default | Supported values | Notes |
|------|---------|------------------|-------|
| `ORCHESTRATION_DURABLE_QUEUE_BACKEND` | `celery` | **`celery` only** | Other values fail closed until a worker adapter exists |
| `CELERY_TASK_ALWAYS_EAGER` | `false` | bool | `true` runs tasks in-process (dev/tests) |
| `ORCHESTRATION_PROVIDER_FAILOVER` | `true` | bool | Intra-provider model chain |
| `ORCHESTRATION_LLM_ATTEMPT_BUDGET` | 3 | int | Max paid LLM HTTP attempts per routing purpose |
| `ORCHESTRATION_STALE_IN_PROGRESS_SECONDS` | 3600 | int | Stuck-run recovery threshold |

**Removed:** LangGraph runner and `ORCHESTRATION_USE_LANGGRAPH`. Durable runs use Celery only.

### Vector / RAG fallbacks (keep off in prod)

| Flag | Default | Notes |
|------|---------|-------|
| `RAG_PYTHON_FALLBACK_ENABLED` | `false` | Scan chunks in Python when pgvector unavailable |
| `VECTOR_FALLBACK_JSON` | `false` | **Alias** for `RAG_PYTHON_FALLBACK_ENABLED` — prefer `RAG_*` name |
| `VECTOR_WRITE_EMBEDDING_JSON` | `false` | Duplicate embeddings in JSON column |
| `AI_RETRIEVE_PYTHON_FALLBACK_ENABLED` | `false` | AI retrieve path Python scan |

Use `settings.vector_python_fallback_enabled` in code (OR of the two RAG flags).

### Memory and RAG product toggles

| Flag | Default | Notes |
|------|---------|-------|
| `MEMORY_LAYER_ENABLED` | `true` | Semantic memory facade |
| `MEMORY_LLM_EXTRACTION_ENABLED` | `false` | LLM vs rule-based extraction |
| `RAG_ENABLED` | `true` | Project document RAG |
| `AI_DOCUMENT_INGEST_ASYNC` | `true` | Celery vs inline ingest |

### Observability

| Flag | Default | Notes |
|------|---------|-------|
| `OBSERVABILITY_ENABLED` | `true` | Request metrics middleware |
| `METRICS_ENABLED` | `true` | `/metrics` Prometheus scrape |
| `METRICS_PUBLIC` | `false` | Require auth for `/metrics` when false |
| `METRICS_QUEUE_REFRESH_ENABLED` | `false` | Refresh queue/run/pool gauges on scrape |
| `OTLP_ENDPOINT` | empty | Distributed tracing export |

See [OBSERVABILITY.md](./OBSERVABILITY.md) for metric names and dashboards.

### Caching

| Flag | Default |
|------|---------|
| `CACHE_ENABLED` | `true` |

When disabled, session/RAG/embedding caches bypass Redis reads (writes may still occur depending on call site).

### SkillPack (legacy)

SkillPack HTTP write paths return **410 Gone**. Canonical skills use workforce `Skill` / `SkillDraft`. Legacy packs remain readable for migration only.

## Production posture

With `APP_ENV=production`, settings validation requires:

- `COOKIE_SECURE=true`
- HTTPS CORS / `FRONTEND_URL`
- `ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE > 0`
- `STORAGE_PUBLIC_READ=false` on the primary artifact bucket
- `SECRETS_ENCRYPTION_KEY` set to a dedicated Fernet key (not JWT-derived)

### Secrets encryption key rotation

1. Generate a new Fernet key and set `SECRETS_ENCRYPTION_PREVIOUS_KEY` to the current `SECRETS_ENCRYPTION_KEY`.
2. Set `SECRETS_ENCRYPTION_KEY` to the new key and restart API/workers.
3. Run `python backend/tools/rotate_secrets_encryption.py` to re-encrypt stored connector/provider secrets.
4. Verify connector health and provider calls.
5. Remove `SECRETS_ENCRYPTION_PREVIOUS_KEY` after `undecryptable=0` for all targets.

Legacy ciphertext encrypted with the JWT-derived fallback key continues to decrypt after a dedicated key is configured until rows are re-encrypted.

Dev (`APP_ENV=dev`) skips the orchestration run rate limiter entirely.

## Object storage

| Variable | Default | Notes |
|----------|---------|-------|
| `STORAGE_BUCKET` | empty | Primary **private** bucket for artifacts, episodic archives, documents |
| `STORAGE_PUBLIC_READ` | `false` | **Must stay false in production** for the primary bucket |
| `STORAGE_PUBLIC_ASSET_BUCKET` | empty | Optional separate bucket for public avatars/branding |
| `STORAGE_PRESIGNED_URL_TTL_SECONDS` | 3600 | Authorized download URLs for private objects |

Deployment checklist:

1. Keep the primary artifact bucket private (no world-readable bucket policy).
2. Use `STORAGE_PUBLIC_ASSET_BUCKET` only when avatars/branding must be permanently public.
3. Serve private artifacts through authenticated API routes or short-lived presigned URLs.

## Local reference

Copy `backend/.env.example` and adjust pools for your process layout. Run settings smoke tests:

```bash
cd backend && pytest tests/test_settings_hygiene.py -q
```
