from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.memory.domain_errors import MemoryDomainError
from backend.modules.memory.procedural import ProceduralMemoryService


def _service() -> tuple[ProceduralMemoryService, MagicMock, MagicMock]:
    db = MagicMock()
    db.commit = AsyncMock()
    db.refresh = AsyncMock()
    db.delete = AsyncMock()
    repo = MagicMock()
    project = SimpleNamespace(id="project-1", owner_id="owner-1")
    get_project = AsyncMock(return_value=project)
    return ProceduralMemoryService(db, repo, get_project), db, repo


@pytest.mark.asyncio
async def test_procedural_create_normalizes_and_persists() -> None:
    service, db, repo = _service()
    row = SimpleNamespace(id="playbook-1")
    repo.create_procedural_playbook = AsyncMock(return_value=row)

    result = await service.create_for_project(
        SimpleNamespace(id="owner-1"),
        "project-1",
        {"slug": "Deploy Safely!", "title": "Deploy", "body_md": "Run checks."},
    )

    assert result is row
    assert repo.create_procedural_playbook.await_args.kwargs["slug"] == "deploy-safely"
    assert repo.create_procedural_playbook.await_args.kwargs["namespace"] == (
        "project/project-1/procedural/deploy-safely"
    )
    db.commit.assert_awaited_once()
    db.refresh.assert_awaited_once_with(row)


@pytest.mark.asyncio
async def test_procedural_create_uses_transport_neutral_domain_error() -> None:
    service, _, _ = _service()

    with pytest.raises(MemoryDomainError) as exc_info:
        await service.create_for_project(
            SimpleNamespace(id="owner-1"),
            "project-1",
            {"slug": "empty", "body_md": ""},
        )

    assert exc_info.value.status_code == 422
