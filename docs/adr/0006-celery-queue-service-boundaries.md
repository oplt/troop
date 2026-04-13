# ADR 0006: GitHub / model gateway / observability as separate worker planes (Celery queues)

## Status

Accepted

## Context

`product_idea.txt` §8 and todo §16 describe separate **GitHub integration**, **model gateway**, and **observability** processes. The codebase remains a modular monolith (ADR 0001); spinning up three new HTTP microservices would duplicate auth, DB, and deployment without immediate benefit.

## Decision

1. **Keep a single deployable API and one Celery app** (`backend.workers.celery_app`).
2. **Split work by Redis broker queues** so each logical plane can run in a **dedicated Celery worker process** that only consumes its queue(s):
   - **`CELERY_TASK_DEFAULT_QUEUE` (`default`)** — agent orchestration runs (`run_task`).
   - **`CELERY_EMAIL_QUEUE` (`email`)** — transactional email.
   - **`CELERY_QUEUE_GITHUB` (`github`)** — GitHub webhook sync events, scheduled issue polling.
   - **`CELERY_QUEUE_MODEL_GATEWAY` (`model_gateway`)** — provider health checks (model/provider plane).
   - **`CELERY_QUEUE_OBSERVABILITY` (`observability`)** — memory expiration sweep and future metrics/audit batch jobs.
3. **Route tasks** via `task_routes` in `celery_app.py` and explicit `queue=` in `apply_async` where tasks are queued from the API.
4. **Operations** run either:
   - **One dev worker** listening to all queues: `-Q default,email,github,model_gateway,observability`, or
   - **Multiple workers** in production, each subscribed to a subset for isolation and scaling.

## Consequences

- No new network hops or service discovery; boundaries are process + queue affinity.
- Deployments must ensure **at least one worker** consumes each non-empty queue or tasks stall (documented in `docs/deployment/celery-service-queues.md`).
- Future extraction to standalone services can preserve queue names as the integration contract or move to a message bus.

## References

- ADR 0002 (Celery + Redis)
- `backend/workers/celery_app.py`, `backend/workers/orchestration.py`
