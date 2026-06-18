from __future__ import annotations

import re

from backend.modules.rag.schemas import RagChunkMatch


class RerankerService:
    """Optional lightweight reranking (keyword overlap boost).

    When ``RAG_RERANK_ENABLED`` is true, boosts chunks whose title/body overlap
    query terms. Cross-encoder reranking can be added behind the same flag later.
    """

    def __init__(self, enabled: bool = False):
        self._enabled = enabled

    def rerank(self, query: str, matches: list[RagChunkMatch]) -> list[RagChunkMatch]:
        if not self._enabled or not matches:
            return matches
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
        if not q_tokens:
            return matches

        def boosted(item: RagChunkMatch) -> float:
            blob = f"{item.title} {item.content}".lower()
            t_tokens = set(re.findall(r"[a-z0-9]{3,}", blob))
            overlap = len(q_tokens & t_tokens) / max(len(q_tokens), 1)
            return item.score + (0.15 * overlap)

        return sorted(matches, key=boosted, reverse=True)
