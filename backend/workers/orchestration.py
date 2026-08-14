import asyncio

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.distributed_lock import RedisLease
from backend.core.logging import get_logger
from backend.modules.observability.metrics import record_run_outcome
from backend.modules.orchestration.execution.cpu_executor import execute_code_job
from backend.modules.orchestration.services.service import OrchestrationService
from backend.workers.celery_app import celery_app
from backend.workers.context import task_context_headers
from backend.workers.retry import CELERY_TRANSIENT_EXCEPTIONS

logger = get_logger(__name__)


class OrchestrationWorkerRuntime:
    async def _run_singleton(self, name: str, operation) -> None:
        async with RedisLease(
            redis_client,
            f"troop:singleton:{name}",
            ttl_seconds=settings.DISTRIBUTED_LOCK_TTL_SECONDS,
            metric_name=name,
        ) as acquired:
            if not acquired:
                logger.info("singleton_worker_skipped lock=%s", name)
                return
            await operation()

    async def execute(self, run_id: str, *, expected_owner_id: str | None = None) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            try:
                run = await service.execute_run(run_id, expected_owner_id=expected_owner_id)
            except Exception as exc:
                record_run_outcome("orchestration", "worker_error")
                # SoftTimeLimitExceeded is not always importable in eager/dev; match by name.
                if (
                    type(exc).__name__ == "SoftTimeLimitExceeded"
                    or "SoftTimeLimit" in type(exc).__name__
                ):
                    try:
                        run = await service.repo.get_run_for_worker(run_id)
                        if run is not None and run.status == "in_progress":
                            run.status = "failed"
                            run.error_message = "Celery soft time limit exceeded"
                            await service.db.commit()
                    except Exception:
                        logger.exception("soft_time_limit_recovery_failed run_id=%s", run_id)
                raise
            record_run_outcome("orchestration", str(getattr(run, "status", "unknown")))

    async def process_github_webhook(self, sync_event_id: str) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.process_github_webhook_sync_event(sync_event_id)

    async def github_connection_resync(self, connection_id: str) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.resync_github_connection_installation(connection_id)

    async def health_check_providers(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.run_provider_health_checks()

        await self._run_singleton("provider_healthcheck", operation)

    async def poll_github_issue_links(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.poll_stale_github_issue_links()

        await self._run_singleton("github_issue_poll", operation)

    async def sweep_expired_memory(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.sweep_expired_memory_globally()

        await self._run_singleton("memory_expiration_sweep", operation)

    async def embed_semantic_memory_entry(self, entry_id: str) -> None:
        from backend.db.session import SessionLocal

        async with SessionLocal() as db:
            service = OrchestrationService(db)
            await service.embed_semantic_memory_entry_worker(entry_id)

    async def execute_ai_studio_run(self, run_id: str) -> None:
        from backend.db.session import SessionLocal
        from backend.modules.ai.service import AiService

        async with SessionLocal() as db:
            await AiService(db).execute_queued_ai_run(run_id)

    async def scan_sla_escalations(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.run_global_sla_escalation_scan()

        await self._run_singleton("sla_escalation_scan", operation)

    async def scan_approval_sla(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal
            from backend.modules.orchestration.services.approvals_domain import ApprovalsService

            async with SessionLocal() as db:
                service = ApprovalsService(db)
                await service.run_approval_sla_scan()

        await self._run_singleton("approval_sla_scan", operation)

    async def recover_stale_in_progress_runs(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.recover_stale_in_progress_runs()

        await self._run_singleton("stale_in_progress_recovery", operation)

    async def process_memory_ingest_jobs(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.process_memory_ingest_jobs_worker()

        await self._run_singleton("memory_ingest_jobs", operation)

    async def episodic_retention_archive(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.run_episodic_retention_and_archive_job()

        await self._run_singleton("episodic_retention_archive", operation)

    async def memory_compaction_backfill(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.run_memory_compaction_backfill(limit=40)

        await self._run_singleton("memory_compaction_backfill", operation)

    async def episodic_index_embedding_batch(self) -> None:
        async def operation() -> None:
            from backend.db.session import SessionLocal

            async with SessionLocal() as db:
                service = OrchestrationService(db)
                await service.process_episodic_index_embedding_batch()

        await self._run_singleton("episodic_index_embedding_batch", operation)

    async def resume_workflow_after_delay(
        self,
        run_id: str,
        node_id: str,
        owner_id: str,
        *,
        expected_resume_at: str | None = None,
    ) -> None:
        from backend.db.session import SessionLocal
        from backend.modules.workforce.models import WorkflowRun
        from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService

        async with SessionLocal() as db:
            run = await db.get(WorkflowRun, run_id)
            if run is None or run.status != "paused":
                logger.info(
                    "workflow_delay_resume_skipped run_id=%s status=%s",
                    run_id,
                    getattr(run, "status", None),
                )
                return
            if run.current_node_id != node_id:
                logger.info(
                    "workflow_delay_resume_skipped run_id=%s cursor=%s expected=%s",
                    run_id,
                    run.current_node_id,
                    node_id,
                )
                return
            delay_state = dict((run.context_json or {}).get("vars", {}).get("_delay_resume") or {})
            if delay_state.get("node_id") != node_id:
                return
            if expected_resume_at and delay_state.get("resume_at") != expected_resume_at:
                return
            service = WorkflowRuntimeService(db)
            try:
                await service.resume_run(str(owner_id), run_id)
            except ValueError as exc:
                logger.info("workflow_delay_resume_not_ready run_id=%s reason=%s", run_id, exc)


@celery_app.task(
    name="backend.workers.orchestration.run_code_execution",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
    ignore_result=False,
)
def run_code_execution(
    shell_cmd: str,
    cwd: str,
    timeout_seconds: int,
    use_shell_wrap: bool = True,
    require_docker: bool = False,
) -> dict:
    """Runs in the CPU Celery queue; ``subprocess.run`` blocking is intentional here."""
    return execute_code_job(
        shell_cmd=shell_cmd,
        cwd=cwd,
        timeout=timeout_seconds,
        use_shell_wrap=use_shell_wrap,
        require_docker=require_docker,
    )


@celery_app.task(
    name="backend.workers.orchestration.run_task",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def run_orchestration_task(run_id: str, expected_owner_id: str | None = None) -> None:
    asyncio.run(OrchestrationWorkerRuntime().execute(run_id, expected_owner_id=expected_owner_id))


@celery_app.task(
    name="backend.workers.orchestration.process_github_webhook_event",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def process_github_webhook_event(sync_event_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().process_github_webhook(sync_event_id))


@celery_app.task(
    name="backend.workers.orchestration.github_connection_resync",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def github_connection_resync(connection_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().github_connection_resync(connection_id))


@celery_app.task(
    name="backend.workers.orchestration.provider_healthcheck",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def provider_healthcheck() -> None:
    asyncio.run(OrchestrationWorkerRuntime().health_check_providers())


@celery_app.task(
    name="backend.workers.orchestration.github_issue_poll",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def github_issue_poll() -> None:
    asyncio.run(OrchestrationWorkerRuntime().poll_github_issue_links())


@celery_app.task(
    name="backend.workers.orchestration.memory_expiration_sweep",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def memory_expiration_sweep() -> None:
    asyncio.run(OrchestrationWorkerRuntime().sweep_expired_memory())


@celery_app.task(
    name="backend.workers.orchestration.sla_escalation_scan",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def sla_escalation_scan() -> None:
    asyncio.run(OrchestrationWorkerRuntime().scan_sla_escalations())


@celery_app.task(
    name="backend.workers.orchestration.approval_sla_scan",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def approval_sla_scan() -> None:
    asyncio.run(OrchestrationWorkerRuntime().scan_approval_sla())


@celery_app.task(
    name="backend.workers.orchestration.embed_semantic_memory_entry",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def embed_semantic_memory_entry(entry_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().embed_semantic_memory_entry(entry_id))


@celery_app.task(
    name="backend.workers.orchestration.execute_ai_studio_run",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def execute_ai_studio_run(run_id: str) -> None:
    asyncio.run(OrchestrationWorkerRuntime().execute_ai_studio_run(run_id))


def queue_ai_studio_run(run_id: str) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().execute_ai_studio_run(run_id))
        else:
            loop.create_task(OrchestrationWorkerRuntime().execute_ai_studio_run(run_id))
        return
    execute_ai_studio_run.apply_async(
        args=[run_id],
        queue=settings.CELERY_QUEUE_MODEL_GATEWAY,
        headers=task_context_headers(),
    )


@celery_app.task(
    name="backend.workers.orchestration.process_memory_ingest_jobs",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def process_memory_ingest_jobs() -> None:
    asyncio.run(OrchestrationWorkerRuntime().process_memory_ingest_jobs())


@celery_app.task(
    name="backend.workers.orchestration.episodic_retention_archive",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def episodic_retention_archive() -> None:
    asyncio.run(OrchestrationWorkerRuntime().episodic_retention_archive())


@celery_app.task(
    name="backend.workers.orchestration.memory_compaction_backfill",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=1,
)
def memory_compaction_backfill() -> None:
    asyncio.run(OrchestrationWorkerRuntime().memory_compaction_backfill())


@celery_app.task(
    name="backend.workers.orchestration.episodic_index_embedding_batch",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def episodic_index_embedding_batch() -> None:
    asyncio.run(OrchestrationWorkerRuntime().episodic_index_embedding_batch())


@celery_app.task(
    name="backend.workers.orchestration.resume_workflow_after_delay",
    autoretry_for=CELERY_TRANSIENT_EXCEPTIONS,
    retry_backoff=True,
    retry_jitter=True,
    max_retries=2,
)
def resume_workflow_after_delay(
    run_id: str,
    node_id: str,
    owner_id: str,
    expected_resume_at: str | None = None,
) -> None:
    asyncio.run(
        OrchestrationWorkerRuntime().resume_workflow_after_delay(
            run_id,
            node_id,
            owner_id,
            expected_resume_at=expected_resume_at,
        )
    )


def queue_workflow_delay_resume(
    *,
    run_id: str,
    node_id: str,
    owner_id: str,
    resume_at_iso: str,
) -> None:
    from datetime import UTC, datetime

    resume_at = datetime.fromisoformat(resume_at_iso)
    countdown = max(0, int((resume_at - datetime.now(UTC)).total_seconds()))
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                OrchestrationWorkerRuntime().resume_workflow_after_delay(
                    run_id,
                    node_id,
                    owner_id,
                    expected_resume_at=resume_at_iso,
                )
            )
        else:
            loop.create_task(
                OrchestrationWorkerRuntime().resume_workflow_after_delay(
                    run_id,
                    node_id,
                    owner_id,
                    expected_resume_at=resume_at_iso,
                )
            )
        return
    resume_workflow_after_delay.apply_async(
        args=[run_id, node_id, owner_id, resume_at_iso],
        countdown=countdown,
        queue=settings.CELERY_TASK_DEFAULT_QUEUE,
        headers={**task_context_headers(), "workflow_run_id": run_id},
    )


def queue_orchestration_run(run_id: str, *, expected_owner_id: str | None = None) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(
                OrchestrationWorkerRuntime().execute(run_id, expected_owner_id=expected_owner_id)
            )
        else:
            loop.create_task(
                OrchestrationWorkerRuntime().execute(run_id, expected_owner_id=expected_owner_id)
            )
        return
    run_orchestration_task.apply_async(
        args=[run_id],
        kwargs={"expected_owner_id": expected_owner_id},
        queue=settings.CELERY_TASK_DEFAULT_QUEUE,
        headers={**task_context_headers(), "run_id": run_id},
    )


def queue_github_webhook_event(sync_event_id: str) -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().process_github_webhook(sync_event_id))
        else:
            loop.create_task(OrchestrationWorkerRuntime().process_github_webhook(sync_event_id))
        return
    process_github_webhook_event.apply_async(
        args=[sync_event_id],
        queue=settings.CELERY_QUEUE_GITHUB,
        headers=task_context_headers(),
    )


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
        args=[entry_id],
        queue=settings.CELERY_QUEUE_MODEL_GATEWAY,
        headers=task_context_headers(),
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
    provider_healthcheck.apply_async(
        queue=settings.CELERY_QUEUE_MODEL_GATEWAY,
        headers=task_context_headers(),
    )


def queue_memory_ingest_jobs() -> None:
    if settings.CELERY_TASK_ALWAYS_EAGER:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(OrchestrationWorkerRuntime().process_memory_ingest_jobs())
        else:
            loop.create_task(OrchestrationWorkerRuntime().process_memory_ingest_jobs())
        return
    process_memory_ingest_jobs.apply_async(
        queue=settings.CELERY_QUEUE_MODEL_GATEWAY,
        headers=task_context_headers(),
    )
