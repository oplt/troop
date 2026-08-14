"""Lightweight in-process counters + histogram buckets for memory pipeline observability."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_counts: dict[str, int] = {}


def increment_memory_metric(name: str, delta: int = 1) -> None:
    with _lock:
        _counts[name] = _counts.get(name, 0) + delta


def _char_size_bucket(n: int) -> int:
    if n <= 0:
        return 0
    if n <= 256:
        return 1
    if n <= 512:
        return 2
    if n <= 1024:
        return 3
    if n <= 2048:
        return 4
    if n <= 4096:
        return 5
    if n <= 8192:
        return 6
    return 7


def record_working_memory_char_histogram(total_chars: int) -> None:
    increment_memory_metric(f"wm_chars_b{_char_size_bucket(total_chars)}")


def record_context_section_char_histogram(section_key: str, char_len: int) -> None:
    safe = "".join(ch if ch.isalnum() or ch == "_" else "_" for ch in section_key)[:64] or "unknown"
    increment_memory_metric(f"ctx_section_{safe}_b{_char_size_bucket(char_len)}")


def record_context_packet_histograms(sections: dict[str, str]) -> None:
    for key, text in sections.items():
        record_context_section_char_histogram(key, len(text or ""))
    wm = (sections.get("working_memory") or "").strip()
    if wm:
        record_working_memory_char_histogram(len(wm))


def _build_rollup(c: dict[str, int]) -> dict[str, Any]:
    def rate(num: int, den: int) -> float | None:
        if den <= 0:
            return None
        return round(num / den, 6)

    def pair(hit_key: str, miss_key: str) -> dict[str, Any]:
        h = c.get(hit_key, 0)
        m = c.get(miss_key, 0)
        return {"hits": h, "misses": m, "hit_rate": rate(h, h + m)}

    wm_hist = {f"b{i}": c.get(f"wm_chars_b{i}", 0) for i in range(8)}
    ctx_sections: dict[str, dict[str, int]] = {}
    for k, v in c.items():
        if not k.startswith("ctx_section_"):
            continue
        tail = k[len("ctx_section_") :]
        if "_b" not in tail:
            continue
        sec, bpart = tail.rsplit("_b", 1)
        if not bpart.isdigit():
            continue
        ctx_sections.setdefault(sec, {})[f"b{bpart}"] = v

    prom_acc = c.get("promotion_semantic_approval_accepted", 0)
    prom_rej = c.get("promotion_semantic_approval_rejected", 0)
    prom_q = prom_acc + prom_rej

    conf_res = c.get("semantic_conflict_resolved_merge", 0)
    emb_g = max(0, c.get("semantic_conflict_embedding_groups", 0))

    return {
        "retrieval_keyword_semantic": {
            "task": pair("retrieval_kw_semantic_task_hit", "retrieval_kw_semantic_task_miss"),
            "project": pair(
                "retrieval_kw_semantic_project_hit", "retrieval_kw_semantic_project_miss"
            ),
            "company": pair(
                "retrieval_kw_semantic_company_hit", "retrieval_kw_semantic_company_miss"
            ),
            "cross_project": pair(
                "retrieval_kw_semantic_cross_project_hit",
                "retrieval_kw_semantic_cross_project_miss",
            ),
        },
        "retrieval_vector_semantic": {
            "task": pair("retrieval_vec_semantic_task_hit", "retrieval_vec_semantic_task_miss"),
            "project": pair(
                "retrieval_vec_semantic_project_hit", "retrieval_vec_semantic_project_miss"
            ),
            "company": pair(
                "retrieval_vec_semantic_company_hit", "retrieval_vec_semantic_company_miss"
            ),
            "cross_project": pair(
                "retrieval_vec_semantic_cross_project_hit",
                "retrieval_vec_semantic_cross_project_miss",
            ),
        },
        "retrieval_keyword_episodic": {
            "task": pair("retrieval_kw_episodic_task_hit", "retrieval_kw_episodic_task_miss"),
            "project": pair(
                "retrieval_kw_episodic_project_hit", "retrieval_kw_episodic_project_miss"
            ),
        },
        "retrieval_vector_episodic": {
            "project": pair(
                "retrieval_vec_episodic_project_hit", "retrieval_vec_episodic_project_miss"
            ),
            "cross_project": pair(
                "retrieval_vec_episodic_cross_project_hit",
                "retrieval_vec_episodic_cross_project_miss",
            ),
        },
        "promotion_semantic_approval": {
            "accepted": prom_acc,
            "rejected": prom_rej,
            "accept_rate": rate(prom_acc, prom_q),
            "candidates_queued": c.get("promotion_candidate_queued", 0),
        },
        "conflicts": {
            "detections_write_path": c.get("semantic_conflict_detected", 0),
            "embedding_groups_scan": emb_g,
            "title_duplicate_groups_scan": c.get(
                "semantic_conflict_scan_title_duplicate_groups", 0
            ),
            "scan_total_groups": c.get("semantic_conflict_scan_total_groups", 0),
            "resolved_merge": conf_res,
            "merge_per_embedding_group_heuristic": rate(conf_res, max(1, emb_g)),
            "note": "merge_per_embedding_group_heuristic = merges / embedding groups from conflict scan, not labeled FP rate.",
        },
        "working_memory_char_histogram": wm_hist,
        "context_section_char_histogram": ctx_sections,
    }


def snapshot_memory_metrics() -> dict[str, Any]:
    with _lock:
        flat = dict(_counts)
    out: dict[str, Any] = {**flat, "_rollup": _build_rollup(flat)}
    return out
