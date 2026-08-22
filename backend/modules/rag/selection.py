from __future__ import annotations

import re
from collections import Counter, defaultdict, deque
from collections.abc import Callable

from backend.modules.rag.schemas import RagChunkMatch

_TOKEN_PATTERN = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)


def _tokens(text: str) -> set[str]:
    return {token.lower() for token in _TOKEN_PATTERN.findall(str(text or ""))}


def _near_duplicate(
    item: RagChunkMatch,
    selected: list[RagChunkMatch],
    *,
    threshold: float,
) -> bool:
    if threshold > 1:
        return False
    item_tokens = _tokens(item.content)
    if not item_tokens:
        return any(not candidate.content.strip() for candidate in selected)
    for candidate in selected:
        candidate_tokens = _tokens(candidate.content)
        union = item_tokens | candidate_tokens
        similarity = len(item_tokens & candidate_tokens) / max(len(union), 1)
        if similarity >= threshold:
            return True
    return False


def _source_key(item: RagChunkMatch) -> str:
    metadata = item.metadata if isinstance(item.metadata, dict) else {}
    for key in ("source_id", "repository_id", "drive_file_id", "source_url"):
        value = metadata.get(key)
        if value:
            return f"{key}:{value}"
    return f"document:{item.document_id}"


def select_context_matches(
    matches: list[RagChunkMatch],
    *,
    limit: int,
    max_context_tokens: int,
    max_chunks_per_document: int,
    max_chunks_per_source: int,
    dedup_similarity_threshold: float,
    estimate_tokens: Callable[[str], int],
) -> list[RagChunkMatch]:
    """Select diverse context under document, source, count, and token budgets."""
    if limit <= 0 or max_context_tokens <= 0:
        return []

    unique: list[RagChunkMatch] = []
    document_counts: Counter[str] = Counter()
    source_counts: Counter[str] = Counter()
    for item in matches:
        source = _source_key(item)
        if document_counts[item.document_id] >= max(1, max_chunks_per_document):
            continue
        if source_counts[source] >= max(1, max_chunks_per_source):
            continue
        if _near_duplicate(item, unique, threshold=dedup_similarity_threshold):
            continue
        unique.append(item)
        document_counts[item.document_id] += 1
        source_counts[source] += 1

    # Round-robin sources so a lower-ranked independent source is not starved by
    # several adjacent chunks from one document family.
    source_order: list[str] = []
    queues: dict[str, deque[RagChunkMatch]] = defaultdict(deque)
    for item in unique:
        source = _source_key(item)
        if source not in queues:
            source_order.append(source)
        queues[source].append(item)

    diversified: list[RagChunkMatch] = []
    while len(diversified) < len(unique):
        made_progress = False
        for source in source_order:
            if queues[source]:
                diversified.append(queues[source].popleft())
                made_progress = True
        if not made_progress:
            break

    selected: list[RagChunkMatch] = []
    token_count = 0
    for item in diversified:
        item_tokens = max(1, estimate_tokens(str(item.content or "")))
        if token_count + item_tokens > max_context_tokens:
            continue
        selected.append(item)
        token_count += item_tokens
        if len(selected) >= limit:
            break
    return selected
