"""Lightweight in-process counters for memory pipeline observability."""

from __future__ import annotations

import threading
from typing import Any

_lock = threading.Lock()
_counts: dict[str, int] = {}


def increment_memory_metric(name: str, delta: int = 1) -> None:
    with _lock:
        _counts[name] = _counts.get(name, 0) + delta


def snapshot_memory_metrics() -> dict[str, Any]:
    with _lock:
        return dict(_counts)
