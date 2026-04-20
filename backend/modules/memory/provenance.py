"""Standardized provenance schema for memory writes (T2.4).

Schema:
    source (str)                 - "api" | "classifier" | "project_decision" | "agent_memory"
                                   | "task_close" | "promoted_working_memory" | "brainstorm" | ...
    source_task_id (str|None)
    source_run_id (str|None)
    source_agent_id (str|None)
    created_by_user_id (str|None)
    confidence (float 0..1)
    supersedes (list[str])       - entry ids this one replaces
    extras (dict)                - free-form source-specific fields (decision_id, etc.)
"""

from __future__ import annotations

from typing import Any, Final

PROVENANCE_KEYS: Final[tuple[str, ...]] = (
    "source",
    "source_task_id",
    "source_run_id",
    "source_agent_id",
    "created_by_user_id",
    "confidence",
    "supersedes",
    "extras",
)

DEFAULT_CONFIDENCE: Final[float] = 0.5

_SOURCE_CONFIDENCE_FLOORS: Final[dict[str, float]] = {
    "api": 0.9,
    "project_decision": 0.85,
    "task_close": 0.7,
    "promoted_working_memory": 0.7,
    "agent_memory": 0.6,
    "classifier": 0.5,
    "brainstorm": 0.55,
}


def _clamp_confidence(v: Any) -> float:
    try:
        f = float(v)
    except (TypeError, ValueError):
        return DEFAULT_CONFIDENCE
    if f < 0.0:
        return 0.0
    if f > 1.0:
        return 1.0
    return round(f, 3)


def _coerce_str_list(v: Any) -> list[str]:
    if not isinstance(v, (list, tuple, set)):
        return []
    out: list[str] = []
    for x in v:
        if x is None:
            continue
        s = str(x).strip()
        if s:
            out.append(s[:64])
    return out[:32]


def normalize_provenance(
    raw: dict[str, Any] | None,
    *,
    default_source: str = "api",
    created_by_user_id: str | None = None,
    source_task_id: str | None = None,
    source_run_id: str | None = None,
    source_agent_id: str | None = None,
    confidence: float | None = None,
) -> dict[str, Any]:
    """Coerce any incoming provenance dict into the canonical shape."""
    raw = dict(raw or {})
    source = str(raw.get("source") or default_source).strip()[:64] or default_source

    conf_in = raw.get("confidence") if confidence is None else confidence
    if conf_in is None:
        conf = _SOURCE_CONFIDENCE_FLOORS.get(source, DEFAULT_CONFIDENCE)
    else:
        conf = _clamp_confidence(conf_in)

    extras_in = raw.get("extras")
    extras: dict[str, Any] = dict(extras_in) if isinstance(extras_in, dict) else {}
    for k, v in raw.items():
        if k in PROVENANCE_KEYS:
            continue
        extras[k] = v

    return {
        "source": source,
        "source_task_id": raw.get("source_task_id") or source_task_id,
        "source_run_id": raw.get("source_run_id") or source_run_id,
        "source_agent_id": raw.get("source_agent_id") or source_agent_id,
        "created_by_user_id": raw.get("created_by_user_id") or created_by_user_id,
        "confidence": conf,
        "supersedes": _coerce_str_list(raw.get("supersedes")),
        "extras": extras,
    }


def get_confidence(provenance: dict[str, Any] | None) -> float:
    if not provenance:
        return DEFAULT_CONFIDENCE
    return _clamp_confidence(provenance.get("confidence"))


def merge_supersedes(provenance: dict[str, Any], new_ids: list[str]) -> dict[str, Any]:
    existing = _coerce_str_list(provenance.get("supersedes"))
    added = _coerce_str_list(new_ids)
    combined = list(dict.fromkeys(existing + added))
    out = dict(provenance)
    out["supersedes"] = combined
    return out


__all__ = [
    "DEFAULT_CONFIDENCE",
    "PROVENANCE_KEYS",
    "get_confidence",
    "merge_supersedes",
    "normalize_provenance",
]
