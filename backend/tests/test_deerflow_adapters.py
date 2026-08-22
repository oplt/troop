from pathlib import Path

import pytest
from backend.api.compat.tools import get_compat_tool, list_compat_tools
from backend.modules.orchestration.markdown import parse_agent_markdown
from backend.modules.orchestration.workspace.storage import (
    MAX_ARTIFACT_BYTES,
    LocalWorkspaceStorage,
    WorkspacePathError,
    WorkspaceSizeError,
    _resolve_inside,
)


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
    tools = {tool.name: tool for tool in list_compat_tools()}

    assert "python_analysis_stub" in tools
    assert tools["python_analysis_stub"].risk_level == "high"
    assert tools["python_analysis_stub"].requires_approval is True
    assert get_compat_tool("web_search_stub") is not None
    assert get_compat_tool("missing") is None


def test_workspace_path_safety_blocks_escape_and_secret_names(tmp_path: Path):
    root = tmp_path / "workspace"
    root.mkdir()

    with pytest.raises(WorkspacePathError):
        _resolve_inside(root, "../escape.md")

    with pytest.raises(WorkspacePathError):
        _resolve_inside(root, ".env")

    with pytest.raises(WorkspacePathError):
        _resolve_inside(root, "/tmp/escape.md")

    with pytest.raises(WorkspacePathError):
        _resolve_inside(root, "payload.exe")

    target = _resolve_inside(root, "notes/final.md")
    assert target == (root / "notes" / "final.md").resolve()


def test_local_workspace_storage_lists_files_and_avoids_overwrite(tmp_path: Path):
    storage = LocalWorkspaceStorage(tmp_path)
    root = storage._workspace_root("projects/p/tasks/t/runs/r")

    first = storage._write_bytes_sync(root, "notes/final.md", b"one")
    second = storage._write_bytes_sync(root, "notes/final.md", b"two")
    files = storage._list_files_sync(root)

    assert first.path == "notes/final.md"
    assert second.path.startswith("notes/final-")
    assert sorted(item.size_bytes for item in files) == [3, 3]


@pytest.mark.asyncio
async def test_local_workspace_storage_rejects_oversized_content(tmp_path: Path):
    storage = LocalWorkspaceStorage(tmp_path)

    with pytest.raises(WorkspaceSizeError):
        await storage.write_text(
            "projects/p/tasks/t/runs/r", "large.md", "x" * (MAX_ARTIFACT_BYTES + 1)
        )
