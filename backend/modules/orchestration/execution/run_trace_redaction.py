"""Redact run-trace payloads into safe user-visible views (OBS-002A)."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.hitl_policy import redact_approval_payload
from backend.modules.orchestration.schemas.run_trace import RunTraceRestrictedRef

_SENSITIVE_KEY_MARKERS = (
    "secret",
    "token",
    "password",
    "credential",
    "authorization",
    "cookie",
    "api_key",
    "access_key",
    "refresh_key",
    "private_key",
)

_RAW_PAYLOAD_KEYS = frozenset(
    {
        "arguments",
        "draft_arguments",
        "raw_arguments",
        "prompt",
        "messages",
        "checkpoint",
        "checkpoint_excerpt",
        "result",
        "output_payload",
        "input_payload",
    }
)


def _key_is_sensitive(key: str) -> bool:
    normalized = str(key).lower().replace("-", "_")
    return normalized in _RAW_PAYLOAD_KEYS or any(marker in normalized for marker in _SENSITIVE_KEY_MARKERS)


def redact_trace_payload(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded, redacted payload suitable for operator-facing trace views."""
    if depth > 6:
        return "[truncated]"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            if _key_is_sensitive(str(key)):
                output[str(key)] = "[restricted]"
            else:
                output[str(key)] = redact_trace_payload(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        return [redact_trace_payload(item, depth=depth + 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value if len(value) <= 2000 else value[:2000] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:2000]


def build_safe_payload(
    payload: dict[str, Any] | None,
    *,
    event_type: str | None = None,
) -> tuple[dict[str, Any], RunTraceRestrictedRef]:
    raw = dict(payload or {})
    redacted = redact_approval_payload(redact_trace_payload(raw))
    restricted_fields = sorted(
        {
            str(key)
            for key in raw
            if _key_is_sensitive(str(key)) or (isinstance(raw.get(key), (dict, list)) and key in _RAW_PAYLOAD_KEYS)
        }
    )
    if event_type in {"tool_call_completed", "llm_response"} and "result_preview" not in redacted:
        preview = raw.get("result_preview")
        if isinstance(preview, str):
            redacted["result_preview"] = preview[:500]
    return redacted, RunTraceRestrictedRef(
        has_restricted=bool(restricted_fields),
        restricted_fields=restricted_fields,
    )
