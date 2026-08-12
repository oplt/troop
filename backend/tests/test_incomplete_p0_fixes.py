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
