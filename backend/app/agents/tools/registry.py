from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field

RiskLevel = Literal["low", "medium", "high"]


class ToolSpec(BaseModel):
    name: str
    description: str
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    enabled: bool = True
    risk_level: RiskLevel = "low"
    requires_approval: bool = False


_TEXT_QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


_TOOL_SPECS: dict[str, ToolSpec] = {
    "web_search_stub": ToolSpec(
        name="web_search_stub",
        description="Placeholder web search capability. No network call is executed.",
        input_schema=_TEXT_QUERY_SCHEMA,
        output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
        risk_level="low",
    ),
    "file_read_stub": ToolSpec(
        name="file_read_stub",
        description="Placeholder read-only workspace file lookup.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
        risk_level="low",
    ),
    "python_analysis_stub": ToolSpec(
        name="python_analysis_stub",
        description="Placeholder Python analysis. Code execution is intentionally disabled.",
        input_schema={
            "type": "object",
            "properties": {"notebook_goal": {"type": "string"}},
            "required": ["notebook_goal"],
        },
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
        risk_level="high",
        requires_approval=True,
    ),
    "github_issue_stub": ToolSpec(
        name="github_issue_stub",
        description="Placeholder GitHub issue read/write capability. No GitHub API call is executed.",
        input_schema=_TEXT_QUERY_SCHEMA,
        output_schema={"type": "object", "properties": {"issue": {"type": "object"}}},
        risk_level="medium",
        requires_approval=True,
    ),
    "geospatial_analysis_stub": ToolSpec(
        name="geospatial_analysis_stub",
        description="Placeholder geospatial analysis capability for imagery and field data.",
        input_schema=_TEXT_QUERY_SCHEMA,
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
        risk_level="medium",
    ),
}


def list_tools(*, enabled_only: bool = False) -> list[ToolSpec]:
    tools = list(_TOOL_SPECS.values())
    if enabled_only:
        tools = [tool for tool in tools if tool.enabled]
    return sorted(tools, key=lambda tool: tool.name)


def get_tool(name: str) -> ToolSpec | None:
    return _TOOL_SPECS.get(name)
