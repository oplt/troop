from pathlib import Path

import pytest
from backend.app.agents.tools.registry import get_tool, list_tools
from backend.app.agents.workspace import _resolve_inside
from backend.modules.orchestration.markdown import parse_agent_markdown
from fastapi import HTTPException


def test_agent_markdown_supports_deerflow_style_frontmatter():
    content = """---
name: Irrigation Analyst
role: agriculture_imagery_specialist
tools_allowed:
  - file_search
  - python_analysis
model:
  provider: openai
  model: gpt-4.1
---

Agent instructions go here.
"""

    normalized, errors = parse_agent_markdown(content)

    assert errors == []
    assert normalized is not None
    assert normalized["name"] == "Irrigation Analyst"
    assert normalized["role"] == "agriculture_imagery_specialist"
    assert normalized["allowed_tools"] == ["file_search", "python_analysis"]
    assert normalized["model_policy"]["provider"] == "openai"
    assert normalized["model_policy"]["model"] == "gpt-4.1"
    assert normalized["system_prompt"] == "Agent instructions go here."


def test_tool_registry_marks_risky_tools_for_approval():
    tools = {tool.name: tool for tool in list_tools()}

    assert "python_analysis_stub" in tools
    assert tools["python_analysis_stub"].risk_level == "high"
    assert tools["python_analysis_stub"].requires_approval is True
    assert get_tool("web_search_stub") is not None
    assert get_tool("missing") is None


def test_workspace_path_safety_blocks_escape_and_secret_names(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(HTTPException):
        _resolve_inside(root, "../escape.md")

    with pytest.raises(HTTPException):
        _resolve_inside(root, ".env")

    target = _resolve_inside(root, "notes/final.md")
    assert target == (root / "notes" / "final.md").resolve()
