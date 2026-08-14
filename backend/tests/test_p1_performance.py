"""P1 performance / correctness smoke tests."""

from __future__ import annotations

from backend.modules.orchestration._helpers import resolve_query_limit
from backend.modules.orchestration.local_repo import (
    build_context_pack_async,
    create_isolated_worktree_async,
    inspect_workspace_async,
    read_repo_file_async,
    run_safe_command_async,
)


def test_resolve_query_limit_caps_zero():
    assert resolve_query_limit(0, default=100, maximum=500) == 500
    assert resolve_query_limit(None, default=100, maximum=500) == 100


def test_local_repo_async_wrappers_exist():
    assert callable(inspect_workspace_async)
    assert callable(create_isolated_worktree_async)
    assert callable(run_safe_command_async)
    assert callable(read_repo_file_async)
    assert callable(build_context_pack_async)


def test_plan_skip_condition_helpers_importable():
    from backend.modules.orchestration.execution.execution_service import (
        OrchestrationExecutionServiceMixin,
    )

    assert hasattr(OrchestrationExecutionServiceMixin, "_plan_agent_execution")


def test_portfolio_bundle_method_exists():
    from backend.modules.orchestration.repository import OrchestrationRepository

    assert hasattr(OrchestrationRepository, "load_portfolio_control_plane_bundle")
    assert hasattr(OrchestrationRepository, "count_runs_by_status_for_owner")
    assert hasattr(OrchestrationRepository, "list_episodic_index_rows_for_sources")
