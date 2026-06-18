from __future__ import annotations

import logging
import time
from typing import Literal

logger = logging.getLogger(__name__)

LogLevel = Literal["info", "warning", "error", "debug"]


def _safe_preview(text: str, max_len: int = 48) -> str:
    compact = " ".join((text or "").split())
    if len(compact) <= max_len:
        return compact
    return compact[: max_len - 3] + "..."


def log_rag_event(
    event: str,
    *,
    user_id: str | None = None,
    project_id: str | None = None,
    document_id: str | None = None,
    count: int | None = None,
    duration_ms: float | None = None,
    attempt: int | None = None,
    error: str | None = None,
    content_preview: str | None = None,
    level: LogLevel = "info",
) -> None:
    parts = [f"rag.{event}"]
    if user_id:
        parts.append(f"user_id={user_id}")
    if project_id:
        parts.append(f"project_id={project_id}")
    if document_id:
        parts.append(f"document_id={document_id}")
    if count is not None:
        parts.append(f"count={count}")
    if duration_ms is not None:
        parts.append(f"duration_ms={duration_ms:.1f}")
    if attempt is not None:
        parts.append(f"attempt={attempt}")
    if error:
        parts.append(f"error={error}")
    if content_preview:
        parts.append(f"preview={_safe_preview(content_preview)!r}")

    message = " ".join(parts)
    if level == "error" or error:
        logger.error(message)
    elif level == "warning":
        logger.warning(message)
    elif level == "debug":
        logger.debug(message)
    else:
        logger.info(message)


class RagTimer:
    def __init__(self) -> None:
        self._start = time.perf_counter()

    @property
    def elapsed_ms(self) -> float:
        return (time.perf_counter() - self._start) * 1000.0
