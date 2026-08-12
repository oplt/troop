"""Regression tests for incomplete.txt P0 security / contract fixes."""

from __future__ import annotations

import pytest
from backend.modules.orchestration.skill_evaluation_hooks import _criteria_scores_unmeasured
from backend.modules.orchestration.tool_execution_context import (
    arguments_hash,
    may_fail_open,
    policy_fail_open_enabled,
)
from backend.modules.workforce.services.outbound_url import UnsafeURLError, validate_outbound_url
from backend.modules.workforce.services.skill_validation import _is_json_schema


def test_ssrf_blocks_metadata_and_loopback(monkeypatch):
    monkeypatch.delenv("TROOP_ALLOW_PRIVATE_CONNECTOR_URLS", raising=False)
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://127.0.0.1/mcp")
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://localhost/mcp")
    # allow_http alone must not bypass HTTPS default
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://example.com/mcp", allow_http=True)


def test_ssrf_allows_private_when_explicit(monkeypatch):
    monkeypatch.setenv("TROOP_ALLOW_PRIVATE_CONNECTOR_URLS", "1")
    assert validate_outbound_url("http://127.0.0.1:8080/mcp").startswith("http://")


def test_ssrf_https_public_ok(monkeypatch):
    monkeypatch.delenv("TROOP_ALLOW_PRIVATE_CONNECTOR_URLS", raising=False)
    # May fail DNS in some CI sandboxes; accept UnsafeURLError only for private/blocked
    try:
        assert validate_outbound_url("https://example.com/mcp").startswith("https://")
    except UnsafeURLError as exc:
        # DNS failure is acceptable in offline environments
        assert "resolve" in str(exc).lower() or "not allowed" in str(exc).lower()


def test_policy_fail_open_defaults_closed(monkeypatch):
    monkeypatch.delenv("TOOL_POLICY_FAIL_OPEN", raising=False)
    assert policy_fail_open_enabled() is False
    assert may_fail_open("web_search") is False
    assert may_fail_open("fs_write") is False
    assert may_fail_open("mcp.x") is False


def test_policy_fail_open_only_low_risk(monkeypatch):
    monkeypatch.setenv("TOOL_POLICY_FAIL_OPEN", "1")
    assert may_fail_open("web_search") is True
    assert may_fail_open("fs_write") is False
    assert may_fail_open("github_create_pr") is False
    assert may_fail_open("a2a.send_task") is False


def test_arguments_hash_stable():
    assert arguments_hash({"b": 1, "a": 2}) == arguments_hash({"a": 2, "b": 1})
    assert arguments_hash({"a": 1}) != arguments_hash({"a": 2})


def test_criteria_scores_are_unmeasured_not_invented():
    scores = _criteria_scores_unmeasured(["citation_quality", {"name": "coverage"}])
    assert scores["citation_quality"]["status"] == "unmeasured"
    assert scores["citation_quality"]["score"] is None
    assert scores["coverage"]["status"] == "unmeasured"


def test_json_schema_distinguishes_invalid_schema():
    assert _is_json_schema({"type": "object", "properties": {"x": {"type": "string"}}}) is True
    assert _is_json_schema({"type": "not-a-real-type"}) is False


def test_fingerprint_includes_project_context():
    from types import SimpleNamespace

    from backend.modules.workforce.services.task_analyzer import _fingerprint_task

    task = SimpleNamespace(
        title="t",
        description="d",
        objective="o",
        acceptance_criteria="a",
        expected_output="e",
        acceptance_criteria_json=["a"],
        labels_json=["sales"],
        task_type="research",
        risk_level="medium",
    )
    project = SimpleNamespace(
        id="p1",
        company_id="c1",
        department_id="d1",
        goals_markdown="grow",
        description="proj",
    )
    fp1 = _fingerprint_task(task, project=project, catalog_fingerprint="abc")
    fp2 = _fingerprint_task(task, project=project, catalog_fingerprint="xyz")
    assert fp1 != fp2
    fp3 = _fingerprint_task(
        task, project=project, catalog_fingerprint="abc", dependency_fingerprint="dep1"
    )
    fp4 = _fingerprint_task(
        task, project=project, catalog_fingerprint="abc", dependency_fingerprint="dep2"
    )
    assert fp3 != fp4


def test_department_policy_clear_and_cycle_helpers():
    """Smoke: DepartmentService helpers exist and policy uses is not None semantics."""
    import inspect

    from backend.modules.workforce.services.department_service import DepartmentService

    src = inspect.getsource(DepartmentService.update)
    assert "is not None" in src
    assert "_assert_no_parent_cycle" in inspect.getsource(DepartmentService)


@pytest.mark.asyncio
async def test_consume_or_check_tool_approval_requires_arguments_hash_for_high_risk():
    from unittest.mock import AsyncMock, MagicMock

    from backend.modules.orchestration.models import ApprovalRequest
    from backend.modules.orchestration.tool_execution_context import consume_or_check_tool_approval

    row = ApprovalRequest(
        id="apr-1",
        status="approved",
        project_id="proj-1",
        run_id="run-1",
        task_id="task-1",
        approval_type="tool:fs_write",
        payload_json={"action_key": "tool:fs_write"},
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    ok = await consume_or_check_tool_approval(
        db,
        owner_id="owner-1",
        tool_name="fs_write",
        arguments_hash="abc123",
        run_id="run-1",
        task_id="task-1",
        project_id="proj-1",
        agent_id="agent-1",
        consume=False,
        require_arguments_hash=True,
    )
    assert ok is False


@pytest.mark.asyncio
async def test_consume_or_check_tool_approval_accepts_matching_hash():
    from unittest.mock import AsyncMock, MagicMock

    from backend.modules.orchestration.models import ApprovalRequest
    from backend.modules.orchestration.tool_execution_context import consume_or_check_tool_approval

    args_hash = "deadbeef"
    row = ApprovalRequest(
        id="apr-2",
        status="approved",
        project_id="proj-1",
        run_id="run-1",
        task_id="task-1",
        approval_type="tool:fs_write",
        payload_json={"action_key": "tool:fs_write", "arguments_hash": args_hash},
    )
    result = MagicMock()
    result.scalars.return_value.all.return_value = [row]
    db = AsyncMock()
    db.execute = AsyncMock(return_value=result)

    ok = await consume_or_check_tool_approval(
        db,
        owner_id="owner-1",
        tool_name="fs_write",
        arguments_hash=args_hash,
        run_id="run-1",
        task_id="task-1",
        project_id="proj-1",
        agent_id="agent-1",
        consume=False,
        require_arguments_hash=True,
    )
    assert ok is True


@pytest.mark.asyncio
async def test_authorize_tool_denies_when_not_permitted():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.workforce.services.tool_registry import ToolRegistryService

    db = AsyncMock()
    service = ToolRegistryService(db)
    provider = MagicMock()
    provider.validate_permissions = AsyncMock(return_value=False)
    service.providers["native"] = provider

    with patch.object(
        service.policy, "resolve", AsyncMock(return_value={"decision": "autonomous"})
    ):
        auth = await service.authorize_tool(
            "owner-1",
            "fs_write",
            {"allowed_tools": ["fs_read"], "owner_id": "owner-1"},
        )

    assert auth["permitted"] is False
    assert auth["decision"] == "autonomous"


@pytest.mark.asyncio
async def test_authorize_tool_fails_closed_when_effective_permissions_error():
    from unittest.mock import AsyncMock, MagicMock, patch

    from backend.modules.workforce.services.tool_registry import ToolRegistryService

    db = AsyncMock()
    service = ToolRegistryService(db)
    provider = MagicMock()
    provider.validate_permissions = AsyncMock(return_value=True)
    service.providers["native"] = provider

    with (
        patch.object(
            service.policy, "resolve", AsyncMock(return_value={"decision": "autonomous"})
        ),
        patch(
            "backend.modules.workforce.services.effective_permissions.resolve_effective_tool_permissions",
            AsyncMock(side_effect=RuntimeError("resolver boom")),
        ),
    ):
        auth = await service.authorize_tool(
            "owner-1",
            "fs_write",
            {
                "allowed_tools": ["fs_write"],
                "owner_id": "owner-1",
                "agent_id": "agent-1",
                "project_id": "proj-1",
            },
        )

    assert auth["permitted"] is False
    assert (auth.get("resolution") or {}).get("matched_scope") == "effective_permissions_error"


@pytest.mark.asyncio
async def test_web_fetch_blocks_private_urls():
    from unittest.mock import AsyncMock, MagicMock

    from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError

    toolbox = OrchestrationToolbox(
        db=AsyncMock(),
        repo=MagicMock(),
        project=MagicMock(id="p1", owner_id="o1", settings_json={}),
        task=None,
        run=None,
        context=MagicMock(
            triggered_by_user_id="o1",
            task_run_id=None,
            workflow_run_id="wf-1",
            id="wf-1",
        ),
    )
    with pytest.raises(ToolExecutionError, match="blocked unsafe URL"):
        await toolbox._web_fetch({"url": "http://127.0.0.1/secret"})


def test_action_policy_fingerprint_changes_when_decision_changes():
    from types import SimpleNamespace

    from backend.modules.workforce.services.task_analyzer import _fingerprint_action_policies

    p1 = SimpleNamespace(
        id="1",
        action_key="fs_write",
        decision="autonomous",
        scope_type="project",
        scope_id="p1",
        risk_level="high",
        updated_at="2026-01-01",
    )
    p2 = SimpleNamespace(
        id="1",
        action_key="fs_write",
        decision="prohibited",
        scope_type="project",
        scope_id="p1",
        risk_level="high",
        updated_at="2026-01-02",
    )
    assert _fingerprint_action_policies([p1]) != _fingerprint_action_policies([p2])
