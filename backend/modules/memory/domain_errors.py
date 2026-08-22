from __future__ import annotations

from typing import Any


class MemoryDomainError(Exception):
    """Transport-neutral memory-domain failure translated by the HTTP façade."""

    def __init__(self, status_code: int, detail: str | dict[str, Any]) -> None:
        super().__init__(str(detail))
        self.status_code = status_code
        self.detail = detail
