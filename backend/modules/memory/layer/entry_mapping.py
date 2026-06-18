from __future__ import annotations

from typing import Any

from backend.modules.memory.entry_types import SEMANTIC_ENTRY_TYPES

_ENTRY_TYPE_ALIASES: dict[str, str] = {
    "fact": "note",
    "constraint": "policy",
    "outcome": "decision",
}


def normalize_entry_type(raw: str) -> str:
    value = _ENTRY_TYPE_ALIASES.get(raw, raw)
    if value not in SEMANTIC_ENTRY_TYPES:
        return "note"
    return value


def default_metadata_for_entry_type(
    entry_type: str, content: str, metadata: dict[str, Any]
) -> dict[str, Any]:
    """Fill required metadata keys with safe defaults for memory-layer writes."""
    meta = dict(metadata)
    if entry_type == "decision" and not meta.get("rationale"):
        meta["rationale"] = "Captured from agent interaction."
    if entry_type == "policy" and not meta.get("policy_area"):
        meta["policy_area"] = "general"
    if entry_type == "preference" and not meta.get("preference_key"):
        meta["preference_key"] = content[:64].strip().lower().replace(" ", "_") or "general"
    if entry_type == "convention" and not meta.get("scope_label"):
        meta["scope_label"] = "project"
    if entry_type == "runbook" and not meta.get("trigger"):
        meta["trigger"] = "manual"
    return meta
