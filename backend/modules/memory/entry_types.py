"""Typed semantic memory entry schemas (T1.4).

Per memory.txt: typed entries replace the free-string `entry_type` with a known
set, each with its own metadata expectations.
"""

from __future__ import annotations

from typing import Any, Final

from fastapi import HTTPException, status

SEMANTIC_ENTRY_TYPES: Final[tuple[str, ...]] = (
    "note",
    "decision",
    "adr",
    "convention",
    "glossary",
    "policy",
    "runbook",
    "dependency_rule",
    "integration_contract",
    "preference",
)

_REQUIRED_METADATA: Final[dict[str, tuple[str, ...]]] = {
    "decision": ("rationale",),
    "adr": ("status", "context", "consequences"),
    "convention": ("scope_label",),
    "glossary": ("term",),
    "policy": ("policy_area",),
    "runbook": ("trigger",),
    "dependency_rule": ("package",),
    "integration_contract": ("integration",),
    "preference": ("preference_key",),
}


def validate_entry_type(value: str) -> str:
    if value not in SEMANTIC_ENTRY_TYPES:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entry_type must be one of {SEMANTIC_ENTRY_TYPES}",
        )
    return value


def validate_entry_metadata(entry_type: str, metadata: dict[str, Any]) -> dict[str, Any]:
    validate_entry_type(entry_type)
    required = _REQUIRED_METADATA.get(entry_type, ())
    missing = [k for k in required if k not in metadata or metadata[k] in (None, "")]
    if missing:
        raise HTTPException(
            status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"entry_type {entry_type!r} requires metadata keys: {missing}",
        )
    return metadata


__all__ = [
    "SEMANTIC_ENTRY_TYPES",
    "validate_entry_metadata",
    "validate_entry_type",
]
