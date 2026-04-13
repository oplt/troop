"""Layer 2 — run-scoped working memory (Phase 2).

Structured scratchpad stored in ``TaskRun.checkpoint_json`` under :data:`WORKING_MEMORY_KEY`.
Bounded fields avoid unbounded transcripts in the hot path; use ``RunEvent`` for full history.

**LangGraph / thread alignment:** ``execution_thread_id`` in ``checkpoint_json`` is set to
``run.id`` when execution starts so external checkpoint stores can use the same id
(see ``execute_run``).
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from typing import Any

WORKING_MEMORY_KEY = "working_memory_v1"
EXECUTION_THREAD_ID_KEY = "execution_thread_id"

# Per-field character limits (UTF-8 safe via len() for practical bounds).
FIELD_LIMITS: dict[str, int] = {
    "objective": 2000,
    "accepted_plan": 6000,
    "latest_findings": 6000,
    "temp_notes": 4000,
    "open_questions": 3000,
    "discussion_summary": 4000,
}
MAX_ARTIFACT_REFS = 24
MAX_REF_LENGTH = 128
MAX_TOTAL_SERIALIZED = 52_000

ALLOWED_PATCH_KEYS = frozenset(FIELD_LIMITS) | {"artifact_refs"}


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _clip(s: str, max_len: int) -> str:
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + "…"


def empty_working_memory() -> dict[str, Any]:
    return {
        "schema_version": "1.0",
        "objective": "",
        "accepted_plan": "",
        "latest_findings": "",
        "temp_notes": "",
        "open_questions": "",
        "discussion_summary": "",
        "artifact_refs": [],
        "updated_at": _utcnow().isoformat(),
    }


def normalize_working_memory(raw: Any) -> dict[str, Any]:
    """Coerce unknown input into a bounded working-memory document."""
    base = empty_working_memory()
    if not isinstance(raw, dict):
        return base
    for key, limit in FIELD_LIMITS.items():
        val = raw.get(key)
        if isinstance(val, str):
            base[key] = _clip(val, limit)
        elif val is not None:
            base[key] = _clip(str(val), limit)
    refs = raw.get("artifact_refs")
    if isinstance(refs, list):
        cleaned: list[str] = []
        for item in refs[:MAX_ARTIFACT_REFS]:
            if isinstance(item, str) and item.strip():
                cleaned.append(_clip(item.strip(), MAX_REF_LENGTH))
        base["artifact_refs"] = cleaned
    if isinstance(raw.get("updated_at"), str):
        base["updated_at"] = raw["updated_at"]
    return base


def merge_working_memory_patch(
    current: dict[str, Any] | None, patch: dict[str, Any]
) -> dict[str, Any]:
    """Shallow merge: only keys in ``ALLOWED_PATCH_KEYS``; then normalize."""
    merged = normalize_working_memory(current)
    for key, value in patch.items():
        if key not in ALLOWED_PATCH_KEYS:
            continue
        if key == "artifact_refs":
            merged[key] = normalize_working_memory(
                {**merged, "artifact_refs": value}
            )["artifact_refs"]
        elif isinstance(value, str):
            merged[key] = _clip(value, FIELD_LIMITS[key])
        elif value is None:
            merged[key] = ""
        else:
            merged[key] = _clip(str(value), FIELD_LIMITS[key])
    merged["updated_at"] = _utcnow().isoformat()
    serialized = json.dumps(merged, ensure_ascii=False)
    if len(serialized) > MAX_TOTAL_SERIALIZED:
        raise ValueError("Working memory exceeds maximum serialized size")
    return merged


def working_memory_from_checkpoint(checkpoint_json: dict[str, Any] | None) -> dict[str, Any]:
    raw = (checkpoint_json or {}).get(WORKING_MEMORY_KEY)
    return normalize_working_memory(raw)


def format_working_memory_for_prompt(wm: dict[str, Any]) -> str:
    """Compact block for user/context prompts (empty sections omitted)."""
    lines: list[str] = []
    labels = [
        ("objective", "Objective"),
        ("accepted_plan", "Accepted plan"),
        ("latest_findings", "Latest findings"),
        ("temp_notes", "Notes"),
        ("open_questions", "Open questions"),
        ("discussion_summary", "Discussion summary"),
    ]
    for key, label in labels:
        text = str(wm.get(key) or "").strip()
        if text:
            lines.append(f"{label}:\n{text}")
    refs = wm.get("artifact_refs") or []
    if isinstance(refs, list) and refs:
        lines.append("Artifact refs:\n" + ", ".join(str(r) for r in refs))
    if not lines:
        return ""
    return "\n\n".join(lines)


def patch_allowed_for_run_status(status: str) -> bool:
    return status in ("queued", "in_progress", "blocked")
