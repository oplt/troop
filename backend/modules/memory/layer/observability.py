from __future__ import annotations

import json
import time

from backend.core.logging import get_logger

logger = get_logger(__name__)


def _safe_preview(text: str, *, max_len: int = 48) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def log_memory_event(
    event: str,
    *,
    user_id: str | None = None,
    memory_id: str | None = None,
    count: int | None = None,
    duration_ms: float | None = None,
    error: str | None = None,
    content_preview: str | None = None,
    log_content: bool = False,
) -> None:
    parts = [f"memory.{event}"]
    if user_id:
        parts.append(f"user_id={user_id}")
    if memory_id:
        parts.append(f"memory_id={memory_id}")
    if count is not None:
        parts.append(f"count={count}")
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.1f}")
    if error:
        parts.append(f"error={error}")
    if log_content and content_preview:
        parts.append(f"preview={json.dumps(_safe_preview(content_preview))}")

    message = " ".join(parts)
    if error:
        logger.warning(message)
    else:
        logger.info(message)


class MemoryTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0
