"""Tests for Jira + Linear connector integrations (CONN-007)."""

from __future__ import annotations

from backend.modules.orchestration.execution.hitl.exact_effect import (
    compute_effect_hash,
    normalize_proposed_effect,
)
from backend.modules.workforce.integrations.issue_tracking import (
    canonical_jira_issue_arguments,
    canonical_linear_issue_arguments,
    jira_issue_arguments_hash,
    linear_issue_arguments_hash,
)


def test_jira_issue_hash_is_canonical() -> None:
    base = {
        "provider": "jira",
        "connector_installation_id": "install-a",
        "project_key": "ENG",
        "summary": "Fix login bug",
        "description": "Users cannot sign in",
        "issue_type": "Bug",
    }
    reordered = {**base, "issue_type": "Bug"}
    assert jira_issue_arguments_hash(base) == jira_issue_arguments_hash(reordered)
    assert jira_issue_arguments_hash(base) != jira_issue_arguments_hash({**base, "summary": "Changed"})
    canonical = canonical_jira_issue_arguments(base)
    assert canonical["provider"] == "jira"
    assert canonical["project_key"] == "ENG"


def test_linear_issue_hash_is_canonical() -> None:
    base = {
        "provider": "linear",
        "connector_installation_id": "install-b",
        "team_id": "team-1",
        "title": "Improve onboarding",
        "description": "Add checklist",
    }
    assert linear_issue_arguments_hash(base) == linear_issue_arguments_hash(dict(base))
    canonical = canonical_linear_issue_arguments(base)
    assert canonical["team_id"] == "team-1"
    assert canonical["title"] == "Improve onboarding"


def test_exact_effect_normalizes_jira_mutations() -> None:
    arguments = {
        "connector_installation_id": "install-a",
        "issue_key": "ENG-42",
        "comment_body": "Shipped fix",
    }
    normalized = normalize_proposed_effect("jira.add_comment", arguments)
    assert normalized["issue_key"] == "ENG-42"
    assert normalized["comment_body"] == "Shipped fix"
    assert compute_effect_hash(normalized, action_key="jira.add_comment") == jira_issue_arguments_hash(
        arguments
    )


def test_exact_effect_normalizes_linear_mutations() -> None:
    arguments = {
        "connector_installation_id": "install-b",
        "issue_id": "issue-99",
        "title": "Updated title",
    }
    normalized = normalize_proposed_effect("linear.update_issue", arguments)
    assert normalized["issue_id"] == "issue-99"
    assert compute_effect_hash(normalized, action_key="linear.update_issue") == linear_issue_arguments_hash(
        arguments
    )


def test_issue_tools_registered_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    jira = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("jira.")}
    linear = {item["slug"] for item in NATIVE_TOOL_CATALOG if item["slug"].startswith("linear.")}
    assert jira >= {
        "jira.search_issues",
        "jira.get_issue",
        "jira.get_issue_comments",
        "jira.create_issue",
        "jira.update_issue",
        "jira.add_comment",
    }
    assert linear >= {
        "linear.search_issues",
        "linear.get_issue",
        "linear.get_issue_comments",
        "linear.create_issue",
        "linear.update_issue",
        "linear.add_comment",
    }


def test_issue_mutations_require_approval_in_catalog() -> None:
    from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

    by_slug = {item["slug"]: item for item in NATIVE_TOOL_CATALOG}
    for slug in (
        "jira.create_issue",
        "jira.update_issue",
        "jira.add_comment",
        "linear.create_issue",
        "linear.update_issue",
        "linear.add_comment",
    ):
        assert by_slug[slug]["requires_approval"] is True
    for slug in ("jira.search_issues", "linear.get_issue", "linear.get_issue_comments"):
        assert by_slug[slug]["requires_approval"] is False


def test_issue_manifests_registered() -> None:
    from backend.modules.workforce.connectors import (
        ConnectorManifestRegistry,
        register_builtin_manifests,
    )

    ConnectorManifestRegistry.reset()
    register_builtin_manifests()
    for slug in ("jira", "linear"):
        manifest = ConnectorManifestRegistry.get_manifest(slug)
        assert manifest is not None
        action_slugs = {item.slug for item in manifest.actions}
        assert f"{slug}.search_issues" in action_slugs
        assert f"{slug}.add_comment" in action_slugs
