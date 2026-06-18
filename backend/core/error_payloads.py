from __future__ import annotations

from typing import Any


def error_payload(
    *,
    code: str,
    message: str,
    correlation_id: str | None = None,
    details: Any = None,
) -> dict[str, Any]:
    payload = {
        "detail": message,
        "correlation_id": correlation_id,
        "error": {
            "code": code,
            "message": message,
            "details": details or {},
        },
    }
    return payload
