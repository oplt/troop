from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.memory.models import MemoryIngestJob
from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.modules.orchestration.services.memory_domain import MemoryService


class _MemoryHarness(OrchestrationMemoryServiceMixin):
    def __init__(self, db: MagicMock, repo: MagicMock) -> None:
        self.db = db
        self.repo = repo
        self.ai_providers = MagicMock()


@pytest.mark.asyncio
async def test_process_memory_ingest_jobs_worker_parallelizes_with_separate_sessions() -> None:
    db = MagicMock()
    repo = MagicMock()
    jobs = [
        MemoryIngestJob(
            id=f"job-{idx}",
            owner_id="owner",
            project_id="proj",
            job_type="document_ingest",
            status="pending",
            payload_json={},
            created_at=datetime.now(UTC),
        )
        for idx in range(3)
    ]
    repo.list_pending_memory_ingest_jobs = AsyncMock(return_value=jobs)
    repo.get_memory_ingest_job = AsyncMock(side_effect=lambda job_id: next(j for j in jobs if j.id == job_id))
    repo.update_memory_ingest_job = AsyncMock()
    db.commit = AsyncMock()

    harness = _MemoryHarness(db, repo)
    harness._execute_memory_ingest_job_body = AsyncMock()

    session_instances: list[MagicMock] = []

    class _SessionCtx:
        def __init__(self, session: MagicMock) -> None:
            self._session = session

        async def __aenter__(self) -> MagicMock:
            return self._session

        async def __aexit__(self, *_args: object) -> None:
            return None

    def _make_session() -> MagicMock:
        session = MagicMock()
        session_instances.append(session)
        return session

    orchestration_service = MagicMock()
    orchestration_service.process_memory_ingest_job_by_id = AsyncMock(return_value=True)

    with (
        patch("backend.modules.memory.service.settings.MEMORY_INGEST_JOB_CONCURRENCY", 3),
        patch("backend.db.session.SessionLocal", side_effect=lambda: _SessionCtx(_make_session())),
        patch(
            "backend.modules.orchestration.services.service.OrchestrationService",
            return_value=orchestration_service,
        ),
    ):
        result = await harness.process_memory_ingest_jobs_worker(limit=3)

    assert result == {"processed": 3, "batch_size": 3}
    assert len(session_instances) == 3
    assert orchestration_service.process_memory_ingest_job_by_id.await_count == 3


@pytest.mark.asyncio
async def test_process_memory_ingest_job_by_id_skips_non_pending() -> None:
    db = MagicMock()
    repo = MagicMock()
    job = MemoryIngestJob(
        id="job-1",
        owner_id="owner",
        project_id="proj",
        job_type="document_ingest",
        status="running",
        payload_json={},
        created_at=datetime.now(UTC),
    )
    repo.get_memory_ingest_job = AsyncMock(return_value=job)
    harness = _MemoryHarness(db, repo)
    harness._process_memory_ingest_job = AsyncMock(return_value=True)

    assert await harness.process_memory_ingest_job_by_id("job-1") is False
    harness._process_memory_ingest_job.assert_not_awaited()


@pytest.mark.asyncio
async def test_assemble_user_context_packet_batches_independent_fetches() -> None:
    db = MagicMock()
    repo = MagicMock()
    harness = _MemoryHarness(db, repo)

    run = MagicMock()
    run.id = "run-1"
    run.task_id = "task-1"
    run.project_id = "proj-1"
    run.project_id = "proj-1"
    run.worker_agent_id = None
    run.orchestrator_agent_id = None
    run.input_payload_json = None
    run.checkpoint_json = None

    task = MagicMock()
    task.id = "task-1"
    task.project_id = "proj-1"
    task.title = "Task"
    task.description = ""
    task.acceptance_criteria = None
    task.assigned_agent_id = None
    task.metadata_json = {}

    project = MagicMock()
    project.id = "proj-1"
    project.name = "Project"
    project.goals_markdown = ""
    project.settings_json = {}
    project.owner_id = "owner"

    db.get = AsyncMock(side_effect=[task, project])
    harness._build_run_scratchpad_context = AsyncMock(return_value=("", ""))
    harness._build_project_knowledge_context = AsyncMock(return_value="docs")
    harness._build_company_brief_section = AsyncMock(return_value="brief")
    harness._semantic_context_snippets_for_prompt = AsyncMock(return_value="semantic")
    harness._build_memory_layer_context_for_run = AsyncMock(return_value="layer")
    harness._procedural_playbook_excerpt = AsyncMock(return_value="playbook")
    harness._build_episodic_recall_sections = AsyncMock(return_value=("", ""))
    repo.list_task_comments = AsyncMock(return_value=[])
    repo.list_task_artifacts = AsyncMock(return_value=[])

    gather_calls: list[int] = []

    original_gather = asyncio.gather

    async def _spy_gather(*coros, **kwargs):
        gather_calls.append(len(coros))
        return await original_gather(*coros, **kwargs)

    with patch("backend.modules.memory.service.asyncio.gather", side_effect=_spy_gather):
        packet = await harness._assemble_user_context_packet(run, agent=None)

    assert gather_calls
    assert gather_calls[-1] >= 6
    assert "knowledge" in packet.sections
    assert packet.sections["knowledge"].endswith("docs")


def test_memory_service_exposes_ingest_job_helpers() -> None:
    db = MagicMock()
    service = MemoryService(db)
    assert hasattr(service, "process_memory_ingest_job_by_id")
    assert hasattr(service, "_build_episodic_recall_sections")
