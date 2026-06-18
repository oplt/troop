from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import MagicMock

import httpx
import pytest
from fastapi import HTTPException

from backend.modules.memory.models import MemoryIngestJob
from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.workers.retry import CELERY_TRANSIENT_EXCEPTIONS, is_transient_worker_error


class _MemoryHarness(OrchestrationMemoryServiceMixin):
    def __init__(self, db: MagicMock, repo: MagicMock) -> None:
        self.db = db
        self.repo = repo
        self.ai_providers = MagicMock()


def test_transient_worker_errors_include_network_failures():
    assert is_transient_worker_error(TimeoutError("timed out"))
    assert is_transient_worker_error(httpx.ConnectError("connection refused"))
    assert not is_transient_worker_error(HTTPException(status_code=400, detail="bad request"))
    assert not is_transient_worker_error(ValueError("invalid input"))
    assert HTTPException not in CELERY_TRANSIENT_EXCEPTIONS


@pytest.mark.asyncio
async def test_unknown_memory_ingest_job_type_fails():
    db = MagicMock()
    repo = MagicMock()
    job = MemoryIngestJob(
        id="job-unknown",
        owner_id="owner",
        project_id="proj",
        job_type="classifier_stub",
        status="pending",
        payload_json={},
        created_at=datetime.now(UTC),
    )
    harness = _MemoryHarness(db, repo)
    with pytest.raises(RuntimeError, match="Unsupported memory ingest job type"):
        await harness._execute_memory_ingest_job_body(job)
