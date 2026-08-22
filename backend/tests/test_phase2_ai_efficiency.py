from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.modules.ai.evaluations.execution import execute_evaluation_cases
from backend.modules.ai.router import router as ai_router
from backend.modules.ai.service import AiService
from fastapi import FastAPI


def test_high_growth_ai_lists_expose_cursor_pages() -> None:
    app = FastAPI()
    app.include_router(ai_router, prefix="/ai")
    schema = app.openapi()

    for path in ("/ai/documents", "/ai/runs", "/ai/evaluation-runs"):
        operation = schema["paths"][path]["get"]
        parameters = {item["name"] for item in operation["parameters"]}
        assert {"limit", "cursor_created_at", "cursor_id"} <= parameters
        response_schema = operation["responses"]["200"]["content"]["application/json"]["schema"]
        assert "CursorPageResponse" in response_schema["$ref"]


@pytest.mark.asyncio
async def test_ai_overview_uses_counts_and_five_recent_runs_only() -> None:
    service = AiService.__new__(AiService)
    service.repo = MagicMock()
    service.repo.get_overview_counts_for_user = AsyncMock(
        return_value={
            "prompt_template_count": 4,
            "document_count": 9,
            "pending_review_count": 2,
            "dataset_count": 3,
        }
    )
    service.repo.list_runs_for_user = AsyncMock(return_value=["run"])

    result = await service.get_overview(SimpleNamespace(id="user-1"))

    service.repo.get_overview_counts_for_user.assert_awaited_once_with("user-1")
    service.repo.list_runs_for_user.assert_awaited_once_with("user-1", limit=5)
    assert result["recent_runs"] == ["run"]
    assert result["document_count"] == 9
    assert "documents" not in result
    assert "datasets" not in result


@pytest.mark.asyncio
async def test_evaluation_cases_use_an_independent_session_per_case() -> None:
    sessions: list[MagicMock] = []
    repositories: list[MagicMock] = []

    class SessionContext:
        def __init__(self) -> None:
            self.session = MagicMock()
            self.session.commit = AsyncMock()
            sessions.append(self.session)

        async def __aenter__(self):
            return self.session

        async def __aexit__(self, *_args):
            return None

    def service_factory(session):
        repo = MagicMock()
        repo.get_dataset_case = AsyncMock(
            return_value=SimpleNamespace(
                id=f"case-{len(repositories)}",
                input_variables_json={},
            )
        )
        repo.create_evaluation_run_item = AsyncMock()
        repositories.append(repo)
        service = MagicMock(repo=repo)
        service.run_prompt = AsyncMock(
            return_value=SimpleNamespace(
                id=f"ai-run-{len(repositories)}",
                output_text="ok",
                output_json=None,
            )
        )
        return service

    with (
        patch("backend.db.session.SessionLocal", side_effect=SessionContext),
        patch("backend.modules.ai.service.AiService", side_effect=service_factory),
        patch(
            "backend.modules.ai.evaluations.execution.score_evaluation_case",
            return_value=(1.0, True, None),
        ),
        patch(
            "backend.modules.ai.evaluations.execution.run_qualitative_judge",
            return_value=(None, None, None),
        ),
        patch(
            "backend.modules.ai.evaluations.execution.build_case_metrics",
            return_value={"score": 1.0},
        ),
    ):
        results = await execute_evaluation_cases(
            user=SimpleNamespace(id="user-1"),
            case_ids=["case-1", "case-2", "case-3"],
            evaluation_run_id="eval-1",
            dataset_id="dataset-1",
            template_key="prompt",
            prompt_version_id="version-1",
            response_format="text",
            model_name=None,
            qualitative_rubric=None,
            concurrency=2,
        )

    assert len(results) == 3
    assert len({id(session) for session in sessions}) == 3
    assert all(repo.create_evaluation_run_item.await_count == 1 for repo in repositories)
    assert all(session.commit.await_count == 1 for session in sessions)
