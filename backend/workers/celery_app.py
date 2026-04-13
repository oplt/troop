from celery import Celery
from celery.schedules import crontab

from backend.core.config import settings

celery_app = Celery(
    "app_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=["backend.workers.tasks", "backend.workers.orchestration"],
)

def _orchestration_task_routes() -> dict[str, dict[str, str]]:
    """Route orchestration tasks to service-scoped queues (same codebase, split workers)."""
    s = settings
    return {
        "backend.workers.orchestration.run_task": {"queue": s.CELERY_TASK_DEFAULT_QUEUE},
        "backend.workers.orchestration.process_github_webhook_event": {"queue": s.CELERY_QUEUE_GITHUB},
        "backend.workers.orchestration.provider_healthcheck": {"queue": s.CELERY_QUEUE_MODEL_GATEWAY},
        "backend.workers.orchestration.github_issue_poll": {"queue": s.CELERY_QUEUE_GITHUB},
        "backend.workers.orchestration.memory_expiration_sweep": {"queue": s.CELERY_QUEUE_OBSERVABILITY},
        "backend.workers.orchestration.sla_escalation_scan": {"queue": s.CELERY_QUEUE_OBSERVABILITY},
        "backend.workers.orchestration.embed_semantic_memory_entry": {"queue": s.CELERY_QUEUE_MODEL_GATEWAY},
        "backend.workers.orchestration.process_memory_ingest_jobs": {"queue": s.CELERY_QUEUE_MODEL_GATEWAY},
        "backend.workers.orchestration.episodic_retention_archive": {"queue": s.CELERY_QUEUE_OBSERVABILITY},
        "backend.workers.orchestration.episodic_index_embedding_batch": {"queue": s.CELERY_QUEUE_MODEL_GATEWAY},
    }


celery_app.conf.update(
    task_default_queue=settings.CELERY_TASK_DEFAULT_QUEUE,
    task_routes={
        "backend.workers.tasks.send_email_task": {"queue": settings.CELERY_EMAIL_QUEUE},
        **_orchestration_task_routes(),
    },
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    result_expires=settings.CELERY_RESULT_EXPIRES_SECONDS,
    broker_connection_retry_on_startup=True,
    task_track_started=True,
    task_ignore_result=True,
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "provider-healthcheck": {
            "task": "backend.workers.orchestration.provider_healthcheck",
            "schedule": crontab(minute=f"*/{max(1, settings.PROVIDER_HEALTHCHECK_INTERVAL_MINUTES)}"),
        },
        "github-issue-poll": {
            "task": "backend.workers.orchestration.github_issue_poll",
            "schedule": crontab(minute=f"*/{max(1, settings.GITHUB_ISSUE_POLL_INTERVAL_MINUTES)}"),
        },
        "memory-expiration-sweep": {
            "task": "backend.workers.orchestration.memory_expiration_sweep",
            "schedule": crontab(minute=15, hour=3),  # daily ~03:15 UTC
        },
        "orchestration-sla-escalation-scan": {
            "task": "backend.workers.orchestration.sla_escalation_scan",
            "schedule": crontab(minute=f"*/{max(1, settings.ORCHESTRATION_SLA_SCAN_INTERVAL_MINUTES)}"),
        },
        "memory-ingest-jobs": {
            "task": "backend.workers.orchestration.process_memory_ingest_jobs",
            "schedule": crontab(minute="*/2"),
        },
        "episodic-index-embedding-batch": {
            "task": "backend.workers.orchestration.episodic_index_embedding_batch",
            "schedule": crontab(minute="*/5"),
        },
        "episodic-retention-archive": {
            "task": "backend.workers.orchestration.episodic_retention_archive",
            "schedule": crontab(minute=45, hour=4),
        },
    },
)
