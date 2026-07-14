# Phase 7 operations: SLOs, failure validation, and horizontal scaling

Phase 7 makes reliability measurable and keeps the current modular monolith
safe to run with multiple API and worker processes. It does not introduce
microservices or a production fault-injection endpoint.

## SLO catalog

The source of truth is `backend/modules/observability/slo.py`. Alert rules are
in `infra/observability/prometheus/alerts.yml`; Grafana is intentionally a
visualization layer and does not define thresholds.

Set `METRICS_QUEUE_REFRESH_ENABLED=true` on API instances scraped by Prometheus
to refresh bounded Redis queue depth and durable orchestration queue age. It is
opt-in because a metrics endpoint must remain dependency-light during a Redis
incident; `/health/ready` remains the dependency authority.

| SLO | Target | Window | Owner | Alert threshold |
| --- | ---: | --- | --- | --- |
| API availability | 99.5% | 30d | platform | 5xx ratio > 0.5% for 10m |
| API p95 latency | 95% under 1.5s | 30d | platform | p95 > 1.5s for 15m |
| Run success | 95% | 30d | orchestration | failure ratio > 5% for 15m |
| Provider reliability | 90% | 30d | ai-platform | non-success > 10% for 10m |
| Memory retrieval latency | 95% under 1.0s | 30d | memory | p95 > 1.0s for 15m |

These are initial objectives, not claims about current performance. Rebaseline
them after representative production traffic is available.

## Alert ownership and response

Every alert carries `owner`, `severity`, and a runbook link. Page alerts are
for customer-impacting availability, queue starvation, and orchestration
failure. Ticket alerts are for sustained latency or provider/memory
degradation that has not yet caused an availability incident.

### API availability

1. Check `/health/ready` and the HTTP error dashboard.
2. Use the route and correlation IDs from logs/traces to identify the failing
   dependency; do not add IDs as Prometheus labels.
3. If PostgreSQL or Redis is degraded, remove the instance from service using
   the deployment platform and restore the dependency before retrying writes.

### API latency

Compare HTTP p95 with database, cache, provider, and active-request metrics.
Reduce traffic or disable the affected optional feature before increasing pool
sizes. Pool changes require a database connection budget review.

### Queue age

Inspect queue-specific depth, oldest age, worker active tasks, and Celery
worker logs. Scale the owning queue only within provider, database, and Redis
capacity. Do not scale CPU workers for provider-bound queues.

### Run success

Inspect the run status, checkpoint, last durable event, provider outcome, and
retry count. Duplicate Celery delivery is expected to be at-least-once; the
worker claims runs with a database row lock and ignores active/terminal
duplicates.

### Provider reliability

Check provider healthcheck results, timeout/retry rates, and the provider's
external status. Fail over only through the configured provider policy; never
log API keys, prompts, or full provider payloads.

### Memory retrieval

Check cache hit/miss rate, embedding latency, vector query duration, and
retrieval scope. Keep owner/project filters in place. Do not increase context
budgets as a first response because that can increase both latency and data
exposure.

## Load validation

The read-only bounded probe targets a running environment:

```bash
PYTHONPATH=. backend/.venv/bin/python backend/tools/phase7_validation.py \
  --url http://127.0.0.1:8000/health/live \
  --requests 100 --concurrency 10
```

Run it against `/health/live`, `/health/ready`, and an authenticated read-only
endpoint separately. Capture p50/p95/p99, error rate, CPU/RSS, DB pool usage,
Redis latency, queue age, and provider metrics. Start with low concurrency and
increase only after the previous run is stable. The tool bounds client
connections and does not mutate application data.

## Failure-injection validation

Use test doubles and isolated staging dependencies, never a hidden production
HTTP switch:

```bash
PYTHONPATH=. backend/.venv/bin/pytest -q -p no:launch_testing \
  backend/tests/test_phase7_reliability.py
```

The suite covers Redis/DB readiness failure, lease contention and release,
duplicate run claim policy, bounded load statistics, and slow/disconnected SSE
behavior. For staging drills, stop Redis, exhaust the PostgreSQL pool with a
bounded connection fixture, make a provider transport return timeout/503, and
restart one worker during a checkpointed run. Expected behavior is fail-closed
readiness, bounded retries, no secret leakage, durable checkpoint recovery, and
no duplicate terminal artifact.

## Horizontal scaling

Run separate API and worker processes against the same PostgreSQL and Redis:

```bash
uvicorn backend.api.main:app --host 0.0.0.0 --port 8000 --workers 2
celery -A backend.workers.celery_app.celery_app worker -Q default,observability --concurrency=4
celery -A backend.workers.celery_app.celery_app worker -Q model_gateway --concurrency=2
```

For a second worker group, use the same queues only when its capacity budget
has been reviewed. `RedisLease` serializes periodic singleton jobs across
workers. Run execution uses a PostgreSQL row lock plus an explicit claimability
check, so duplicate delivery does not start an active or terminal run twice.
Sessions, cache, queue state, and durable orchestration state remain in shared
services; process-local pools are only performance optimizations.

Set `INSTANCE_ID` per deployment instance. `/health/version` exposes it for
diagnostics but it is not a metric label. Verify two instances with:

```bash
curl -s http://127.0.0.1:8000/health/version
```

Rollback: disable the additional alert group and stop the second worker group;
the application code remains compatible with one API and one worker. Do not
delete Redis lease keys manually unless the owning worker is stopped or the
lease TTL has expired.

## Validation commands

```bash
python -m json.tool infra/observability/grafana/dashboards/troop-overview.json
PYTHONPATH=. backend/.venv/bin/pytest -q -p no:launch_testing \
  backend/tests/test_phase7_reliability.py backend/tests/test_phase2_observability.py \
  backend/tests/test_phase4_concurrency.py backend/tests/test_celery_tasks.py
```

`promtool check rules infra/observability/prometheus/alerts.yml` should be run
when Prometheus tooling is available. The local observability compose overlay
is optional and must not be used as a production authentication or retention
configuration.
