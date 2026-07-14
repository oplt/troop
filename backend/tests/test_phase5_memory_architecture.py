from __future__ import annotations

from datetime import UTC, datetime
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.memory.layer.config import MemoryConfig
from backend.modules.memory.layer.context import build_memory_context
from backend.modules.memory.layer.provider import SemanticMemoryProvider
from backend.modules.memory.layer.schemas import MemoryAccessContext, MemoryRecord
from backend.modules.memory.layer.service import MemoryService
from backend.modules.memory.namespaces import build_namespace, parse_namespace


def test_memory_access_context_builds_scoped_filters() -> None:
    context = MemoryAccessContext(
        owner_id="user-1",
        company_id="company-1",
        project_id="project-1",
        agent_id="agent-1",
        task_id="task-1",
    )
    filters = context.filters(scope="task")

    assert filters.user_id == "user-1"
    assert filters.company_id == "company-1"
    assert filters.project_id == "project-1"
    assert filters.task_id == "task-1"
    assert filters.scope == "task"


def test_user_and_task_namespaces_are_explicitly_validated() -> None:
    user_namespace = build_namespace("user", "user-1", "preferences")
    task_namespace = build_namespace("task", "task-1", "working")

    assert parse_namespace(user_namespace) == ("user", "user-1", ["preferences"])
    assert parse_namespace(task_namespace) == ("task", "task-1", ["working"])


def test_project_memory_config_includes_retention_and_context_limits() -> None:
    config = MemoryConfig.from_settings(
        {
            "memory": {
                "default_ttl_days": 30,
                "max_ttl_days": 365,
                "context_max_tokens": 256,
            }
        }
    )

    assert config.default_ttl_days == 30
    assert config.max_ttl_days == 365
    assert config.context_max_tokens == 256


@pytest.mark.asyncio
async def test_canonical_memory_service_records_retention_metadata() -> None:
    captured: dict[str, object] = {}

    class Provider:
        async def add(self, **kwargs):
            captured.update(kwargs)
            return MemoryRecord(id="m1", content=kwargs["content"], user_id=kwargs["owner_id"])

        async def find_duplicate(self, *_args, **_kwargs):
            return None

    session = AsyncMock()
    service = MemoryService(
        session,
        config=MemoryConfig(default_ttl_days=0, max_ttl_days=365),
        provider=Provider(),  # type: ignore[arg-type]
    )
    record = await service.add_memory(
        "user-1",
        "The project uses bounded memory retention policies.",
        project_id="project-1",
        ttl_days=30,
        retention_policy="project-default",
    )

    metadata = captured["metadata"]
    assert record is not None
    assert metadata["ttl_days"] == 30
    assert metadata["retention_policy"] == "project-default"
    assert datetime.fromisoformat(str(metadata["expires_at"])).tzinfo is not None


def test_memory_context_is_ranked_and_bounded() -> None:
    now = datetime.now(UTC)
    records = [
        MemoryRecord(
            id="old",
            content="Unrelated historical note " * 20,
            user_id="u1",
            updated_at=now.replace(year=now.year - 1),
        ),
        MemoryRecord(
            id="relevant",
            content="Project retention policy keeps semantic memory bounded.",
            user_id="u1",
            confidence=0.9,
            updated_at=now,
        ),
    ]

    context = build_memory_context(records, query="retention policy", max_tokens=24)

    assert "retention policy" in context
    assert len(context) <= 24 * 4 + 32


@pytest.mark.asyncio
async def test_provider_builds_user_namespace_without_project_leakage() -> None:
    row = SimpleNamespace(
        id="m1",
        body="A private preference",
        owner_id="user-1",
        title="Private preference",
        entry_type="note",
        scope="user",
        project_id=None,
        company_id=None,
        agent_id=None,
        source_run_id=None,
        metadata_json={},
        provenance_json={},
        created_by_user_id="user-1",
        source_chunk_id=None,
        source_task_id=None,
        created_at=datetime.now(UTC),
        updated_at=datetime.now(UTC),
        ttl_days=None,
        expires_at=None,
        deleted_at=None,
        retention_policy="default",
        memory_version=1,
        embedding_model=None,
        embedding_version=None,
    )
    repository = MagicMock()
    repository.create = AsyncMock(return_value=row)
    repository.enqueue_embedding = AsyncMock()
    provider = SemanticMemoryProvider(repository)

    await provider.add(
        owner_id="user-1",
        content="A private preference",
        scope="user",
        project_id=None,
        metadata={"entry_type": "preference", "title": "Private preference"},
    )

    kwargs = repository.create.await_args.kwargs
    assert kwargs["scope"] == "user"
    assert kwargs["namespace"] == "user/user-1/memory"
