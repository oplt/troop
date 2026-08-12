"""Regression tests for incomplete.txt P0 security / contract fixes."""

from __future__ import annotations

import pytest

from backend.modules.orchestration.tool_execution_context import may_fail_open, policy_fail_open_enabled
from backend.modules.workforce.services.outbound_url import UnsafeURLError, validate_outbound_url


def test_ssrf_blocks_metadata_and_loopback(monkeypatch):
    monkeypatch.delenv("TROOP_ALLOW_PRIVATE_CONNECTOR_URLS", raising=False)
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://127.0.0.1/mcp")
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://169.254.169.254/latest/meta-data")
    with pytest.raises(UnsafeURLError):
        validate_outbound_url("http://localhost/mcp")


def test_ssrf_allows_private_when_explicit(monkeypatch):
    monkeypatch.setenv("TROOP_ALLOW_PRIVATE_CONNECTOR_URLS", "1")
    assert validate_outbound_url("http://127.0.0.1:8080/mcp", allow_http=True).startswith("http://")


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
