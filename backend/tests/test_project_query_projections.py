"""Regression coverage for project summary and detail query projections."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.orchestration.execution.run_queries import ExecutionRunQueriesMixin
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.services.approvals_service import (
    OrchestrationApprovalsServiceMixin,
)
from backend.modules.orchestration.services.base import OrchestrationRunQueryMixin
from backend.modules.projects.portfolio.overview import PortfolioOverviewMixin
from backend.modules.projects.project_crud import ProjectCrudMixin


class CaptureDb:
    def __init__(self) -> None:
        self.statement = None
        self.statements = []

    async def execute(self, statement):
        self.statement = statement
        self.statements.append(statement)
        result = MagicMock()
        result.scalars.return_value.all.return_value = []
        result.all.return_value = []
        return result


def selected_columns_sql(statement) -> str:
    sql = str(statement.compile()).lower()
    return sql.split("\nfrom ", maxsplit=1)[0]


@pytest.mark.asyncio
async def test_project_detail_query_keeps_fields_required_by_overview() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_projects("owner-1")

    sql = selected_columns_sql(db.statement)
    assert "goals_markdown" in sql
    assert "settings_json" in sql
    assert "knowledge_policy_json" in sql
    assert "budget_json" in sql
    assert "metadata_json" in sql
    assert "knowledge_summary" in sql


@pytest.mark.asyncio
async def test_project_summary_query_omits_detail_fields() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_project_summaries("owner-1")

    sql = selected_columns_sql(db.statement)
    assert "goals_markdown" not in sql
    assert "settings_json" not in sql
    assert "knowledge_policy_json" not in sql
    assert "budget_json" not in sql
    assert "metadata_json" not in sql
    assert "knowledge_summary" not in sql


@pytest.mark.asyncio
async def test_project_list_service_uses_summary_projection() -> None:
    repo = SimpleNamespace(list_project_summaries=AsyncMock(return_value=[]))
    service = SimpleNamespace(repo=repo)

    result = await ProjectCrudMixin.list_projects(service, SimpleNamespace(id="owner-1"))

    assert result == []
    repo.list_project_summaries.assert_awaited_once_with("owner-1")


@pytest.mark.asyncio
async def test_overview_uses_full_project_projection() -> None:
    repo = SimpleNamespace(
        list_projects=AsyncMock(return_value=[]),
        list_agents=AsyncMock(return_value=[]),
        list_runs=AsyncMock(return_value=[]),
        list_approvals=AsyncMock(return_value=[]),
        list_sync_events=AsyncMock(return_value=[]),
    )
    service = SimpleNamespace(repo=repo)

    result = await PortfolioOverviewMixin.get_overview(service, SimpleNamespace(id="owner-1"))

    assert result["projects"] == []
    repo.list_projects.assert_awaited_once_with("owner-1")


@pytest.mark.asyncio
async def test_run_detail_query_keeps_fields_required_by_overview() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_runs("owner-1", limit=10)

    sql = selected_columns_sql(db.statement)
    assert "triggered_by_user_id" in sql
    assert "orchestrator_agent_id" in sql
    assert "checkpoint_json" in sql
    assert "input_payload_json" in sql
    assert "output_payload_json" in sql


@pytest.mark.asyncio
async def test_run_summary_query_omits_detail_fields() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_run_summaries("owner-1", limit=10)

    sql = selected_columns_sql(db.statement)
    assert "triggered_by_user_id" not in sql
    assert "orchestrator_agent_id" not in sql
    assert "checkpoint_json" not in sql
    assert "input_payload_json" not in sql
    assert "output_payload_json" not in sql


@pytest.mark.asyncio
async def test_event_detail_query_keeps_payload_required_by_snapshots() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_run_events("run-1")

    sql = selected_columns_sql(db.statement)
    assert "payload_json" in sql


@pytest.mark.asyncio
async def test_event_summary_query_omits_payload() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_run_event_summaries("run-1")

    sql = selected_columns_sql(db.statement)
    assert "payload_json" not in sql


@pytest.mark.asyncio
async def test_approval_detail_query_keeps_fields_required_by_overview() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_approvals("owner-1", status="pending")

    sql = selected_columns_sql(db.statements[0])
    assert "requested_by_user_id" in sql
    assert "payload_json" in sql
    assert "precondition_fingerprint" in sql
    assert "routing_snapshot_json" in sql
    assert "sla_policy_json" in sql


@pytest.mark.asyncio
async def test_approval_summary_query_omits_detail_fields() -> None:
    db = CaptureDb()

    await OrchestrationRepository(db).list_approval_summaries("owner-1", status="pending")

    sql = selected_columns_sql(db.statements[0])
    assert "requested_by_user_id" not in sql
    assert "payload_json" not in sql
    assert "precondition_fingerprint" not in sql
    assert "routing_snapshot_json" not in sql
    assert "sla_policy_json" not in sql


@pytest.mark.asyncio
async def test_paginated_run_service_uses_summary_projection() -> None:
    repo = SimpleNamespace(list_run_summaries=AsyncMock(return_value=[]))
    service = SimpleNamespace(repo=repo)

    result = await OrchestrationRunQueryMixin.list_task_run_summaries(
        service, SimpleNamespace(id="owner-1"), limit=10
    )

    assert result == []
    repo.list_run_summaries.assert_awaited_once_with(
        "owner-1",
        None,
        limit=10,
        cursor_created_at=None,
        cursor_id=None,
    )


@pytest.mark.asyncio
async def test_paginated_event_service_uses_summary_projection() -> None:
    run = SimpleNamespace(id="run-1")
    repo = SimpleNamespace(list_run_event_summaries=AsyncMock(return_value=[]))
    service = SimpleNamespace(repo=repo, get_run=AsyncMock(return_value=run))

    result = await ExecutionRunQueriesMixin.list_run_event_summaries(
        service, SimpleNamespace(id="owner-1"), "run-1", limit=10
    )

    assert result == []
    repo.list_run_event_summaries.assert_awaited_once_with(
        "run-1",
        limit=10,
        cursor_created_at=None,
        cursor_id=None,
    )


@pytest.mark.asyncio
async def test_paginated_approval_service_uses_summary_projection() -> None:
    repo = SimpleNamespace(list_approval_summaries=AsyncMock(return_value=[]))
    service = SimpleNamespace(repo=repo)

    result = await OrchestrationApprovalsServiceMixin.list_approval_summaries(
        service, SimpleNamespace(id="owner-1"), limit=10
    )

    assert result == []
    repo.list_approval_summaries.assert_awaited_once_with(
        "owner-1",
        limit=10,
        cursor_created_at=None,
        cursor_id=None,
    )
