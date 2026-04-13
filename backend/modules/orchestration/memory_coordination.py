"""Shared blackboard + per-agent private scratchpads (task metadata)."""

from __future__ import annotations

from typing import Any

MEMORY_COORDINATION_KEY = "memory_coordination"


def extract_blackboard_sections(
    task_metadata: dict[str, Any] | None,
    *,
    agent_id: str | None,
) -> tuple[str, str]:
    """Return (shared_markdown, private_markdown_for_agent)."""
    meta = task_metadata or {}
    raw = meta.get(MEMORY_COORDINATION_KEY)
    if not isinstance(raw, dict):
        return "", ""
    shared = raw.get("shared")
    shared_s = shared.strip() if isinstance(shared, str) else ""
    priv_map = raw.get("private")
    priv_s = ""
    if isinstance(priv_map, dict) and agent_id:
        p = priv_map.get(agent_id)
        if isinstance(p, str) and p.strip():
            priv_s = p.strip()
    return shared_s, priv_s
