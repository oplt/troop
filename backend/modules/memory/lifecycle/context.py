from __future__ import annotations

from backend.modules.memory.layer.context import build_memory_context
from backend.modules.memory.layer.schemas import MemoryRecord


class MemoryContextLifecycle:
    """Prompt-facing context assembly kept independent from persistence."""

    def build(
        self,
        records: list[MemoryRecord],
        *,
        query: str = "",
        header: str | None = None,
        max_tokens: int = 700,
    ) -> str:
        return build_memory_context(
            records,
            query=query,
            header=header,
            max_tokens=max_tokens,
        )
