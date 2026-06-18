from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.modules.orchestration.constants import GITHUB_WEBHOOK_EVENT_ALLOWLIST, TASK_TRANSITIONS
from backend.modules.orchestration.services.base import (
    GITHUB_WEBHOOK_EVENT_ALLOWLIST as BASE_GITHUB,
    TASK_TRANSITIONS as BASE_TRANSITIONS,
)
from backend.modules.orchestration.tools import OrchestrationToolbox
from backend.modules.rag.schemas import RagChunkMatch


def test_task_transitions_single_source():
    assert TASK_TRANSITIONS is BASE_TRANSITIONS
    assert "queued" in TASK_TRANSITIONS["backlog"]


def test_github_webhook_allowlist_single_source():
    assert GITHUB_WEBHOOK_EVENT_ALLOWLIST is BASE_GITHUB
    assert "push" in GITHUB_WEBHOOK_EVENT_ALLOWLIST


@pytest.mark.asyncio
async def test_repo_search_prefers_vector_retrieval():
    toolbox = OrchestrationToolbox(
        db=MagicMock(),
        repo=MagicMock(),
        project=MagicMock(id="project-1"),
        task=None,
        run=MagicMock(triggered_by_user_id="user-1"),
    )
    vector_match = RagChunkMatch(
        chunk_id="c1",
        document_id="d1",
        title="README.md",
        content="vector hit",
        chunk_index=0,
        score=0.91,
        metadata={"path": "src/main.py"},
    )
    mock_rag = MagicMock()
    mock_rag.retrieve = AsyncMock(return_value=[vector_match])

    with patch("backend.modules.rag.service.RagService", return_value=mock_rag):
        result = await toolbox._repo_search({"query": "auth middleware", "limit": 3})

    assert result["retrieval"] == "vector"
    assert result["items"][0]["path"] == "src/main.py"
    mock_rag.retrieve.assert_awaited_once()
