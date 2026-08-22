"""Legacy tool catalog representation backed by the workforce catalog."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from fastapi import APIRouter, HTTPException

from backend.api.compat.schemas import ToolListResponse, ToolSpec
from backend.modules.workforce.constants import NATIVE_TOOL_CATALOG

router = APIRouter()

_TEXT_QUERY_SCHEMA = {
    "type": "object",
    "properties": {"query": {"type": "string"}},
    "required": ["query"],
}


@dataclass(frozen=True, slots=True)
class LegacyToolAlias:
    canonical_slug: str
    description: str
    input_schema: dict[str, Any] = field(default_factory=dict)
    output_schema: dict[str, Any] = field(default_factory=dict)


_ALIASES: dict[str, LegacyToolAlias] = {
    "web_search_stub": LegacyToolAlias(
        canonical_slug="web_search",
        description="Compatibility alias for the canonical web search tool.",
        input_schema=_TEXT_QUERY_SCHEMA,
        output_schema={"type": "object", "properties": {"results": {"type": "array"}}},
    ),
    "file_read_stub": LegacyToolAlias(
        canonical_slug="fs_read",
        description="Compatibility alias for the canonical workspace read tool.",
        input_schema={
            "type": "object",
            "properties": {"path": {"type": "string"}},
            "required": ["path"],
        },
        output_schema={"type": "object", "properties": {"content": {"type": "string"}}},
    ),
    "python_analysis_stub": LegacyToolAlias(
        canonical_slug="code_execute",
        description="Compatibility alias for canonical sandboxed code execution.",
        input_schema={
            "type": "object",
            "properties": {"notebook_goal": {"type": "string"}},
            "required": ["notebook_goal"],
        },
        output_schema={"type": "object", "properties": {"summary": {"type": "string"}}},
    ),
    "github_issue_stub": LegacyToolAlias(
        canonical_slug="github_comment",
        description="Compatibility alias for the canonical governed GitHub action.",
        input_schema=_TEXT_QUERY_SCHEMA,
        output_schema={"type": "object", "properties": {"issue": {"type": "object"}}},
    ),
    "geospatial_analysis_stub": LegacyToolAlias(
        canonical_slug="code_execute",
        description="Compatibility alias for canonical sandboxed analysis.",
        input_schema=_TEXT_QUERY_SCHEMA,
        output_schema={"type": "object", "properties": {"findings": {"type": "array"}}},
    ),
}

_CANONICAL_BY_SLUG = {str(item["slug"]): item for item in NATIVE_TOOL_CATALOG}


def _tool_spec(name: str, alias: LegacyToolAlias) -> ToolSpec:
    canonical = _CANONICAL_BY_SLUG[alias.canonical_slug]
    risk = str(canonical.get("risk_level") or "medium")
    if risk not in {"low", "medium", "high"}:
        risk = "high"
    return ToolSpec(
        name=name,
        description=alias.description,
        input_schema=alias.input_schema or dict(canonical.get("schema_json") or {}),
        output_schema=alias.output_schema,
        enabled=True,
        risk_level=risk,
        requires_approval=bool(canonical.get("requires_approval")),
    )


def list_compat_tools(*, enabled_only: bool = False) -> list[ToolSpec]:
    tools = [_tool_spec(name, alias) for name, alias in _ALIASES.items()]
    if enabled_only:
        tools = [tool for tool in tools if tool.enabled]
    return sorted(tools, key=lambda tool: tool.name)


def get_compat_tool(name: str) -> ToolSpec | None:
    alias = _ALIASES.get(name)
    return _tool_spec(name, alias) if alias else None


@router.get("", response_model=ToolListResponse)
async def get_tools(enabled_only: bool = False):
    return ToolListResponse(tools=list_compat_tools(enabled_only=enabled_only))


@router.get("/{name}", response_model=ToolSpec)
async def get_tool_spec(name: str):
    tool = get_compat_tool(name)
    if tool is None:
        raise HTTPException(status_code=404, detail="Tool not found")
    return tool


__all__ = ["get_compat_tool", "list_compat_tools", "router"]
