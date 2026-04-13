# Celery queues and logical service boundaries

Orchestration-related work is split across **Redis broker queues** so you can run **separate Celery worker processes** for GitHub sync, model/provider health, and observability sweeps without splitting the Python package (see ADR 0006).

## Queue map

| Logical plane | Env var | Default queue name | Tasks |
|---------------|---------|----------------------|--------|
| Agent orchestration | `CELERY_TASK_DEFAULT_QUEUE` | `default` | `run_task` |
| Email | `CELERY_EMAIL_QUEUE` | `email` | `send_email_task` |
| GitHub integration | `CELERY_QUEUE_GITHUB` | `github` | `process_github_webhook_event`, `github_issue_poll` |
| Model gateway | `CELERY_QUEUE_MODEL_GATEWAY` | `model_gateway` | `provider_healthcheck` |
| Observability | `CELERY_QUEUE_OBSERVABILITY` | `observability` | `memory_expiration_sweep` |

## Single worker (typical dev)

Consume every queue so scheduled and API-queued tasks are handled:

```bash
cd backend
.venv/bin/celery -A backend.workers.celery_app:celery_app worker \
  --loglevel=INFO \
  -Q default,email,github,model_gateway,observability
```

**Celery Beat** (scheduled tasks) should run in a **separate** process; it only schedules, workers execute:

```bash
.venv/bin/celery -A backend.workers.celery_app:celery_app beat --loglevel=INFO
```

## Split workers (production-style)

Example: four workers, each with a narrow subscription (adjust replicas as needed):

```bash
# Orchestration + email (high throughput paths)
celery -A backend.workers.celery_app:celery_app worker -Q default,email -c 4

# GitHub webhooks + polling
celery -A backend.workers.celery_app:celery_app worker -Q github -c 2

# Provider / model health
celery -A backend.workers.celery_app:celery_app worker -Q model_gateway -c 1

# Housekeeping / observability
celery -A backend.workers.celery_app:celery_app worker -Q observability -c 1
```

`CELERY_TASK_ALWAYS_EAGER=true` runs tasks in-process and ignores queue separation—use only for local API tests.

## Runtime visibility

`GET /orchestration/runtime-info` returns `celery_queues` with the resolved queue names for the current environment.
