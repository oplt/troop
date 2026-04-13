"""Project-scoped memory settings (stored under `settings_json.memory`)."""

from __future__ import annotations

from typing import Any

DEFAULT_MEMORY_SETTINGS: dict[str, Any] = {
    "auto_promote_decisions": True,
    "auto_promote_approved_agent_memory": True,
    "second_stage_rag": False,
    "semantic_write_requires_approval": False,
    "auto_ingest_bypasses_semantic_approval": True,
    "episodic_retrieval_depth": 8,
    "episodic_retention_days": 90,
    "episodic_archive_enabled": True,
    "episodic_delete_index_after_archive": True,
    "task_close_auto_promote_working_memory": False,
    "enable_semantic_vector_search": True,
    "enable_episodic_vector_search": True,
    "deep_recall_mode": False,
    "deep_recall_episodic_candidates": 24,
    "classifier_worker_enabled": True,
}


def merge_memory_settings(settings_json: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(DEFAULT_MEMORY_SETTINGS)
    raw = settings_json or {}
    mem = raw.get("memory")
    if isinstance(mem, dict):
        for k, v in mem.items():
            if k in base:
                base[k] = v
    return base
