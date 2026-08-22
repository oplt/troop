from __future__ import annotations

from dataclasses import replace

from backend.modules.rag.schemas import RagChunkMatch


def reciprocal_rank_fusion(
    rankings: list[list[RagChunkMatch]],
    *,
    limit: int,
    rank_constant: int = 60,
) -> list[RagChunkMatch]:
    """Fuse independently ranked result sets without comparing their raw scores."""
    if limit <= 0:
        return []

    scores: dict[str, float] = {}
    candidates: dict[str, RagChunkMatch] = {}
    first_seen: dict[str, int] = {}
    seen_index = 0
    for ranking in rankings:
        ranking_seen: set[str] = set()
        for rank, item in enumerate(ranking, start=1):
            if item.chunk_id in ranking_seen:
                continue
            ranking_seen.add(item.chunk_id)
            if item.chunk_id not in candidates:
                candidates[item.chunk_id] = item
                first_seen[item.chunk_id] = seen_index
                seen_index += 1
            scores[item.chunk_id] = scores.get(item.chunk_id, 0.0) + (
                1.0 / (max(1, rank_constant) + rank)
            )

    ordered_ids = sorted(
        candidates,
        key=lambda item_id: (-scores[item_id], first_seen[item_id]),
    )[:limit]
    if not ordered_ids:
        return []
    max_score = max(scores[item_id] for item_id in ordered_ids)
    fused: list[RagChunkMatch] = []
    for item_id in ordered_ids:
        item = candidates[item_id]
        score = scores[item_id] / max_score
        try:
            fused.append(replace(item, score=score))
        except TypeError:  # Defensive support for third-party VectorStore adapters.
            item.score = score
            fused.append(item)
    return fused
