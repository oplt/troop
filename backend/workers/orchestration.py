import asyncio

from backend.core.config import settings
from backend.modules.orchestration.service import OrchestrationService
from backend.workers.celery_app import celery_app


class OrchestrationWorkerRuntime:
    async def execute(self, run_id: str) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.execute_run(run_id)

    async def process_github_webhook(self, sync_event_id: str) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.process_github_webhook_sync_event(sync_event_id)

    async def health_check_providers(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.run_provider_health_checks()

    async def poll_github_issue_links(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.poll_stale_github_issue_links()

    async def sweep_expired_memory(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.sweep_expired_memory_globally()

    async def embed_semantic_memory_entry(self, entry_id: str) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.embed_semantic_memory_entry_worker(entry_id)

    async def scan_sla_escalations(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.run_global_sla_escalation_scan()

    async def process_memory_ingest_jobs(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.process_memory_ingest_jobs_worker()

    async def episodic_retention_archive(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.run_episodic_retention_and_archive_job()

    async def episodic_index_embedding_batch(self) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.process_episodic_index_embedding_batch()


@celery_app.task(
    name="backend.workers.orchestration.run_task",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def run_orchestration_task(run_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().execute(run_id))


@celery_app.task(
    name="backend.workers.orchestration.process_github_webhook_event",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def process_github_webhook_event(sync_event_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().process_github_webhook(sync_event_id))


@celery_app.task(
    name="backend.workers.orchestration.provider_healthcheck",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def provider_healthcheck() -> None:
    asyncio.run(OrchestrationWorkerRuntime().health_check_providers())


@celery_app.task(
    name="backend.workers.orchestration.github_issue_poll",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def github_issue_poll() -> None:
    asyncio.run(OrchestrationWorkerRuntime().poll_github_issue_links())


@celery_app.task(
    name="backend.workers.orchestration.memory_expiration_sweep",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def memory_expiration_sweep() -> None:
    asyncio.run(OrchestrationWorkerRuntime().sweep_expired_memory())


@celery_app.task(
    name="backend.workers.orchestration.sla_escalation_scan",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def sla_escalation_scan() -> None:
    asyncio.run(OrchestrationWorkerRuntime().scan_sla_escalations())


@celery_app.task(
    name="backend.workers.orchestration.embed_semantic_memory_entry",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def embed_semantic_memory_entry(entry_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().embed_semantic_memory_entry(entry_id))


@celery_app.task(
    name="backend.workers.orchestration.process_memory_ingest_jobs",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def process_memory_ingest_jobs() -> None:
    asyncio.run(OrchestrationWorkerRuntime().process_memory_ingest_jobs())


@celery_app.task(
    name="backend.workers.orchestration.episodic_retention_archive",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def episodic_retention_archive() -> None:
    asyncio.run(OrchestrationWorkerRuntime().episodic_retention_archive())


@celery_app.task(
    name="backend.workers.orchestration.episodic_index_embedding_batch",
    autoretry_for=(Exception,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def episodic_index_embedding_batch() -> None:
    asyncio.run(OrchestrationWorkerRuntime().episodic_index_embedding_batch())


def queue_orchestration_run(run_id: str) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().execute(run_id))
        else:
            loop.create_task(OrchestrationWorkerRuntime().execute(run_id))
        return
    run_orchestration_task.apply_async(args=[run_id], queue=settings.CELERY_TASK_DEFAULT_QUEUE)


def queue_github_webhook_event(sync_event_id: str) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().process_github_webhook(sync_event_id))
        else:
            loop.create_task(OrchestrationWorkerRuntime().process_github_webhook(sync_event_id))
        return
    process_github_webhook_event.apply_async(args=[sync_event_id], queue=settings.CELERY_QUEUE_GITHUB)


def queue_semantic_embedding(entry_id: str) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().embed_semantic_memory_entry(entry_id))
        else:
            loop.create_task(OrchestrationWorkerRuntime().embed_semantic_memory_entry(entry_id))
        return
    embed_semantic_memory_entry.apply_async(
        args=[entry_id], queue=settings.CELERY_QUEUE_MODEL_GATEWAY
    )


def queue_provider_healthcheck() -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().health_check_providers())
        else:
            loop.create_task(OrchestrationWorkerRuntime().health_check_providers())
        return
    provider_healthcheck.apply_async(queue=settings.CELERY_QUEUE_MODEL_GATEWAY)
