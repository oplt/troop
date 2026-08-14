from celery import Celery
from celery.schedules import crontab

from backend.core.config import settings
from backend.core.http_clients import register_worker_http_shutdown
from backend.modules.observability.instrumentation import register_worker_observability_signals
from backend.workers.context import register_task_context_signals

celery_app = Celery(
    "app_backend",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
    include=[
        "backend.workers.tasks",
        "backend.workers.orchestration",
        "backend.workers.integrations",
    ],
)
register_task_context_signals()
register_worker_observability_signals()
register_worker_http_shutdown()

if settings.OTLP_ENDPOINT:
    from backend.modules.observability.tracing import setup_tracing

    setup_tracing(
        settings.OTLP_ENDPOINT,
        f"{settings.APP_NAME}-worker",
        settings.OTLP_INSECURE,
    )


def _orchestration_task_routes() -> dict[str, dict[str, str]]:
    """Route orchestration tasks to service-scoped queues (same codebase, split workers)."""
    s = settings
    return {
        "backend.workers.orchestration.run_task": {"queue": s.CELERY_TASK_DEFAULT_QUEUE},
        "backend.workers.orchestration.run_code_execution": {"queue": s.CELERY_QUEUE_CPU},
        "backend.workers.orchestration.process_github_webhook_event": {
            "queue": s.CELERY_QUEUE_GITHUB
        },
        "backend.workers.orchestration.github_connection_resync": {"queue": s.CELERY_QUEUE_GITHUB},
        "backend.workers.orchestration.provider_healthcheck": {
            "queue": s.CELERY_QUEUE_MODEL_GATEWAY
        },
        "backend.workers.orchestration.github_issue_poll": {"queue": s.CELERY_QUEUE_GITHUB},
        "backend.workers.orchestration.memory_expiration_sweep": {
            "queue": s.CELERY_QUEUE_OBSERVABILITY
        },
        "backend.workers.orchestration.stale_in_progress_recovery": {
            "queue": s.CELERY_QUEUE_OBSERVABILITY
        },
        "backend.workers.orchestration.sla_escalation_scan": {
            "queue": s.CELERY_QUEUE_OBSERVABILITY
        },
        "backend.workers.orchestration.embed_semantic_memory_entry": {
            "queue": s.CELERY_QUEUE_MODEL_GATEWAY
        },
        "backend.workers.orchestration.execute_ai_studio_run": {
            "queue": s.CELERY_QUEUE_MODEL_GATEWAY
        },
        "backend.workers.orchestration.process_memory_ingest_jobs": {
            "queue": s.CELERY_QUEUE_MODEL_GATEWAY
        },
        "backend.workers.orchestration.episodic_retention_archive": {
            "queue": s.CELERY_QUEUE_OBSERVABILITY
        },
        "backend.workers.orchestration.memory_compaction_backfill": {
            "queue": s.CELERY_QUEUE_OBSERVABILITY
        },
        "backend.workers.orchestration.episodic_index_embedding_batch": {
            "queue": s.CELERY_QUEUE_MODEL_GATEWAY
        },
        "backend.workers.orchestration.resume_workflow_after_delay": {
            "queue": s.CELERY_TASK_DEFAULT_QUEUE
        },
        "backend.workers.integrations.process_external_event": {
            "queue": s.CELERY_QUEUE_INTEGRATIONS
        },
        "backend.workers.integrations.renew_gmail_watches": {"queue": s.CELERY_QUEUE_INTEGRATIONS},
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
    task_acks_late=settings.CELERY_TASK_ACKS_LATE,
    task_reject_on_worker_lost=settings.CELERY_TASK_REJECT_ON_WORKER_LOST,
    worker_prefetch_multiplier=max(1, settings.CELERY_WORKER_PREFETCH_MULTIPLIER),
    task_soft_time_limit=settings.CELERY_TASK_SOFT_TIME_LIMIT_SECONDS,
    task_time_limit=settings.CELERY_TASK_TIME_LIMIT_SECONDS,
    broker_transport_options={
        "visibility_timeout": settings.CELERY_BROKER_VISIBILITY_TIMEOUT_SECONDS,
    },
    timezone="UTC",
    enable_utc=True,
    beat_schedule={
        "provider-healthcheck": {
            "task": "backend.workers.orchestration.provider_healthcheck",
            "schedule": crontab(
                minute=f"*/{max(1, settings.PROVIDER_HEALTHCHECK_INTERVAL_MINUTES)}"
            ),
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
            "schedule": crontab(
                minute=f"*/{max(1, settings.ORCHESTRATION_SLA_SCAN_INTERVAL_MINUTES)}"
            ),
        },
        "stale-in-progress-recovery": {
            "task": "backend.workers.orchestration.stale_in_progress_recovery",
            "schedule": crontab(minute="*/5"),
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
        "memory-compaction-backfill": {
            "task": "backend.workers.orchestration.memory_compaction_backfill",
            "schedule": crontab(minute=20, hour=5, day_of_week=0),
        },
        "gmail-watch-renewal": {
            "task": "backend.workers.integrations.renew_gmail_watches",
            "schedule": crontab(minute=f"*/{max(5, settings.GMAIL_WATCH_RENEW_INTERVAL_MINUTES)}"),
        },
    },
)
