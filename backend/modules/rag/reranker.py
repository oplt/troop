from __future__ import annotations

import re
from collections.abc import Callable

from backend.modules.rag.schemas import RagChunkMatch

RerankScorer = Callable[[str, list[str]], list[float]]


class RerankerService:
    """Configurable second-stage reranker with a cheap lexical default."""

    def __init__(
        self,
        enabled: bool = False,
        *,
        mode: str = "lexical",
        scorer: RerankScorer | None = None,
    ):
        self._enabled = enabled
        self._mode = mode.strip().lower()
        self._scorer = scorer

    def rerank(self, query: str, matches: list[RagChunkMatch]) -> list[RagChunkMatch]:
        if not self._enabled or not matches or self._mode == "off":
            return matches
        if self._mode in {"cross_encoder", "llm"}:
            if self._scorer is None:
                return matches
            scores = self._scorer(query, [f"{item.title}\n{item.content}" for item in matches])
            if len(scores) != len(matches):
                return matches
            return [
                item
                for _, item in sorted(
                    zip(scores, matches, strict=True),
                    key=lambda pair: pair[0],
                    reverse=True,
                )
            ]
        if self._mode != "lexical":
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
