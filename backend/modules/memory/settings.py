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
    # Tier 3 — retrieval scoping + context packet token budgets
    "retrieval_stage_min_hits": 3,
    "retrieval_cross_project_limit": 6,
    "context_packet_max_tokens": 3500,
    "context_packet_max_chars": 48000,
    "context_packet_section_token_budgets": None,
    "context_packet_section_priority_scores": None,
    # Tier 4 — compaction / archival / lifecycle
    "compaction_on_task_close_enabled": True,
    "task_close_archive_unpromoted_memory": True,
    "task_close_low_value_archive_days": 14,
    # Memory layer (mem0-inspired unified API over semantic storage)
    "memory_layer_enabled": True,
    "layer": {
        "enabled": True,
        "default_search_limit": 5,
        "extraction_enabled": True,
        "llm_extraction_enabled": False,
        "dedup_enabled": True,
        "min_extraction_confidence": 0.45,
        "inject_context_before_llm": True,
    },
}


def merge_memory_settings(settings_json: dict[str, Any] | None) -> dict[str, Any]:
    base = dict(DEFAULT_MEMORY_SETTINGS)
    raw = settings_json or {}
    mem = raw.get("memory")
    if isinstance(mem, dict):
        for k, v in mem.items():
            if k == "layer" and isinstance(v, dict):
                layer = dict(base.get("layer") or {})
                layer.update(v)
                base["layer"] = layer
            elif k in base:
                base[k] = v
    return base
