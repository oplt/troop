"""Task-close compaction: episodic snapshot text + checkpoint pruning."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.modules.orchestration.working_memory import WORKING_MEMORY_KEY, working_memory_from_checkpoint

TASK_CLOSE_SNAPSHOT_KIND = "task_close_snapshot"
AGENT_MEMORY_TTL_SNAPSHOT_KIND = "agent_memory_ttl"
PROJECT_DOCUMENT_TTL_SNAPSHOT_KIND = "project_document_ttl"


def snapshot_source_id(task_id: str, run_id: str) -> str:
    return f"{task_id}:{run_id}"


def build_task_close_snapshot_text(
    *,
    task_title: str,
    task_id: str,
    wm: dict[str, Any],
    event_lines: list[str],
    max_len: int = 12_000,
) -> str:
    parts: list[str] = [
        f"[task_close_snapshot] task_id={task_id}",
        f"title: {task_title}",
    ]
    for key in ("objective", "accepted_plan", "latest_findings", "open_questions", "discussion_summary"):
        val = str(wm.get(key) or "").strip()
        if val:
            parts.append(f"{key}:\n{val[:4000]}")
    if event_lines:
        parts.append("recent_run_events:\n" + "\n".join(event_lines[-120:]))
    text = "\n\n".join(parts).strip()
    return text[:max_len]


def prune_checkpoint_after_compaction(checkpoint_json: dict[str, Any] | None) -> dict[str, Any]:
    """Drop bulky WM / scratchpad; keep workflow keys."""
    cp = dict(checkpoint_json or {})
    wm = working_memory_from_checkpoint(cp)
    now = datetime.now(UTC).isoformat()
    cp[WORKING_MEMORY_KEY] = {
        "schema_version": str(wm.get("schema_version") or "1.0"),
        "objective": str(wm.get("objective") or "")[:800],
        "accepted_plan": "",
        "latest_findings": str(wm.get("latest_findings") or "")[:1200],
        "temp_notes": "",
        "open_questions": "",
        "discussion_summary": "",
        "artifact_refs": (wm.get("artifact_refs") or [])[:8] if isinstance(wm.get("artifact_refs"), list) else [],
        "updated_at": now,
        "compacted": True,
    }
    ss = cp.get("scratchpad_summary")
    if isinstance(ss, str) and len(ss) > 600:
        cp["scratchpad_summary"] = ss[:600] + "…"
    return cp
