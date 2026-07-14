from backend.modules.orchestration.markdown import parse_agent_markdown
from backend.modules.team.service import TeamServiceMixin


def test_agent_markdown_normalizes_the_full_registry_contract() -> None:
    normalized, errors = parse_agent_markdown(
        """---
name: Backend Builder
role: specialist
capabilities: [coding, review]
tools_allowed: [fs_read, fs_write]
permissions: code-write
escalation_path: manager-agent
task_filters: [backend, '^bug:backend']
model:
  provider: openai
  model: gpt-4.1
  fallback_model: gpt-4.1-mini
memory_policy:
  scope: project-only
budget:
  token_budget: 12000
  time_budget_seconds: 900
  retry_budget: 2
output_schema: patch_proposal
---

# Mission

Implement backend work with tests.
"""
    )

    assert errors == []
    assert normalized is not None
    assert normalized["permissions"] == "code-write"
    assert normalized["escalation_path"] == "manager-agent"
    assert normalized["task_filters"] == ["backend", "^bug:backend"]
    assert normalized["model_policy"]["permissions"] == "code-write"
    assert normalized["output_schema"] == {"format": "patch_proposal"}


def test_agent_payload_mapping_keeps_contract_fields_explicit() -> None:
    mapped = TeamServiceMixin()._agent_payload_to_model(
        {
            "name": "Docs",
            "slug": "docs",
            "permissions": "comment-only",
            "escalation_path": "manager",
            "task_filters": ["docs"],
            "metadata": {"source": "test"},
        }
    )

    assert mapped["model_policy_json"] == {
        "permissions": "comment-only",
        "escalation_path": "manager",
    }
    assert mapped["metadata_json"] == {"source": "test", "task_filters": ["docs"]}
