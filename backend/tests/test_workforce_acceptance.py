"""Acceptance-oriented workforce scenario tests (deterministic, no live LLM)."""

from types import SimpleNamespace

from backend.modules.workforce.constants import LEGACY_STATUS_ALIASES, TASK_TRANSITIONS
from backend.modules.workforce.services.markdown_skill_import import parse_skill_markdown
from backend.modules.workforce.services.skill_matcher import _scope_allowed
from backend.modules.workforce.services.task_analyzer import _heuristic_analyze
from backend.modules.workforce.services.workflow_runtime import WorkflowRuntimeService


def test_sales_greenhouse_heuristic_requirements():
    task = SimpleNamespace(
        id="t1",
        title="Belgium Greenhouse Sales Expansion research",
        description=(
            "Identify 50 greenhouse operators in Belgium and the Netherlands. "
            "Research each company, classify commercial greenhouses, enrich firmographics, "
            "verify sources, qualify leads, and produce a structured prospect dataset."
        ),
        objective="Build qualified greenhouse prospect list",
        expected_output="Structured prospect dataset",
        acceptance_criteria="50 prospects with verified sources",
        acceptance_criteria_json=["50 prospects", "verified sources"],
        labels_json=["sales", "research"],
        task_type="research",
        risk_level="medium",
        autonomy_level="semi-autonomous",
    )
    result = _heuristic_analyze(task)
    caps = {c.lower() for c in result.required_capabilities}
    assert any("research" in c or "web" in c or "company" in c or "lead" in c for c in caps)
    assert result.required_tools
    assert result.risk_level in {"low", "medium", "high", "critical"}


def test_engineering_status_alias_not_terminal_github_sync():
    assert LEGACY_STATUS_ALIASES.get("synced_to_github") == "completed"
    # Generic completed remains a first-class status; sync is not required to finish.
    assert "completed" in TASK_TRANSITIONS
    assert "archived" in TASK_TRANSITIONS["completed"]


def test_markdown_import_creates_skill_draft_fields():
    md = """# Greenhouse Lead Qualifier

## Purpose
Qualify greenhouse operators against ICP.

## When to use
When enriching sales leads for agriculture.

## Capabilities
- company_discovery
- lead_qualification

## Tools
- web_search
- web_fetch

## Instructions
Search public sources, classify greenhouse operators, and return structured rows.
"""
    parsed = parse_skill_markdown(md, file_name="greenhouse.md")
    assert parsed["source_type"] == "markdown_import"
    assert parsed["slug"]
    assert "company_discovery" in parsed["capabilities"] or parsed["capabilities"]
    assert "web_search" in parsed["required_tools"] or parsed["required_tools"]
    assert len(parsed["instructions_markdown"]) > 20


def test_skill_scope_hard_filter_task_vs_org():
    skill = SimpleNamespace(
        status="active",
        current_version_id="v1",
        scope="task",
        task_id="task-a",
        project_id=None,
        company_id=None,
    )
    assert _scope_allowed(skill, task_id="task-a", project_id="p1", company_id="c1") is True
    assert _scope_allowed(skill, task_id="task-b", project_id="p1", company_id="c1") is False


def test_workflow_graph_validation_supports_required_node_types():
    runtime = WorkflowRuntimeService.__new__(WorkflowRuntimeService)
    errors = runtime.validate_graph(
        nodes=[
            {"id": "a", "type": "agent"},
            {"id": "b", "type": "approval"},
        ],
        edges=[{"from": "a", "to": "b"}],
        entry_node_id="a",
    )
    assert errors == []
    bad = runtime.validate_graph(
        nodes=[{"id": "a", "type": "unknown"}],
        edges=[],
        entry_node_id="a",
    )
    assert any("unsupported" in e for e in bad)
