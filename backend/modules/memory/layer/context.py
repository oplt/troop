from __future__ import annotations

import re
from datetime import UTC, datetime

from backend.modules.memory.layer.schemas import MemoryRecord


def _relevance(record: MemoryRecord, query_tokens: set[str]) -> float:
    if not query_tokens:
        return 0.0
    tokens = set(re.findall(r"[a-z0-9]{3,}", f"{record.title} {record.content}".lower()))
    return len(tokens & query_tokens) / max(1, len(query_tokens))


def _recency(record: MemoryRecord) -> float:
    timestamp = record.updated_at or record.created_at
    if timestamp is None:
        return 0.0
    now = datetime.now(UTC)
    if timestamp.tzinfo is None:
        timestamp = timestamp.replace(tzinfo=UTC)
    age_days = max(0.0, (now - timestamp).total_seconds() / 86400)
    return 1.0 / (1.0 + age_days / 30.0)


def build_memory_context(
    records: list[MemoryRecord],
    *,
    header: str | None = None,
    query: str = "",
    max_tokens: int = 700,
) -> str:
    """Rank and format retrieved memories within a hard prompt budget."""
    if not records:
        return ""

    title = header or "Relevant memory context"
    query_tokens = set(re.findall(r"[a-z0-9]{3,}", (query or "").lower()))
    ranked = sorted(
        records,
        key=lambda record: (
            float(record.score or 0.0) * 0.55
            + _relevance(record, query_tokens) * 0.3
            + float(record.confidence or 0.0) * 0.1
            + _recency(record) * 0.05,
            (record.updated_at or record.created_at).timestamp()
            if (record.updated_at or record.created_at)
            else 0.0,
        ),
        reverse=True,
    )
    lines = [f"{title}:"]
    used_tokens = max(1, len(lines[0]) // 4)
    for record in ranked:
        line = record.display_line
        line_tokens = max(1, len(line) // 4)
        if used_tokens + line_tokens > max(1, max_tokens):
            remaining = max(0, max_tokens - used_tokens)
            if remaining <= 8:
                break
            line = line[: remaining * 4]
        lines.append(line)
        used_tokens += max(1, len(line) // 4)
        if used_tokens >= max(1, max_tokens):
            break
    return "\n".join(lines)
