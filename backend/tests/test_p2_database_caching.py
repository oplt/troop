"""P2 database / caching smoke tests."""

from __future__ import annotations

from pathlib import Path


def test_composite_index_migration_exists():
    root = Path(__file__).resolve().parents[1] / "alembic" / "versions"
    path = root / "d4e5f6a7b8c9_composite_indexes_approvals_tasks_runs.py"
    assert path.is_file()
    text = path.read_text()
    assert "ix_approval_requests_project_status" in text
    assert "ix_task_runs_project_status" in text
    assert "ix_orchestrator_tasks_project_status" in text
    assert 'down_revision' in text and "c3d4e5f6a7b8" in text


def test_emit_run_event_accepts_commit_flag():
    import inspect

    from backend.modules.orchestration.execution.execution_service import (
        OrchestrationExecutionServiceMixin,
    )

    sig = inspect.signature(OrchestrationExecutionServiceMixin._emit_run_event)
    assert "commit" in sig.parameters


def test_list_project_decisions_supports_limit_and_query():
    import inspect

    from backend.modules.orchestration.repository import OrchestrationRepository

    sig = inspect.signature(OrchestrationRepository.list_project_decisions)
    assert "limit" in sig.parameters
    assert "query" in sig.parameters
