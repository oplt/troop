from __future__ import annotations

from backend.modules.memory.layer.schemas import MemoryRecord


def build_memory_context(records: list[MemoryRecord], *, header: str | None = None) -> str:
    """Format retrieved memories into a concise prompt block."""
    if not records:
        return ""

    title = header or "Relevant memory context"
    lines = [f"{title}:"]
    for record in records:
        lines.append(record.display_line)
    return "\n".join(lines)
