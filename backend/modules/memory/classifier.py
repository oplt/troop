"""Memory Classifier worker (T2.1).

Reads raw signals (run events + closed tasks) and classifies them into
candidate memory entries per layer:

  - working    : short-lived state, kept on the run scratchpad
  - episodic   : timeline snapshot (already handled upstream)
  - semantic   : stable fact worth promoting (decision/convention/runbook/...)
  - procedural : reusable "how we do X" snippet

Only rule-based; LLM classification can be layered on later behind the
same interface. Output candidates feed the promotion rules engine and
the conflict resolver, and may be turned into semantic/procedural rows
by the service layer (gated by approval settings).
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Literal

Layer = Literal["working", "episodic", "semantic", "procedural"]

_DECISION_PATTERNS: list[tuple[str, str]] = [
    ("decision", r"\b(decided|chose|pick(ed)? (this|to)|will go with|accepted|ruled out)\b"),
    ("adr", r"\b(adr[-: ]|architecture decision)\b"),
    ("dependency_rule", r"\b(pin(ned)?|upgrad(ed|ing)|downgrad(ed|ing)|version lock)\b"),
    ("runbook", r"\b(to reproduce|steps:|runbook|playbook)\b"),
    ("convention", r"\b(convention|we name|we format|style is)\b"),
    ("policy", r"\b(policy|never commit|must encrypt|no secrets)\b"),
    ("glossary", r"\b(glossary|term|definition:)\b"),
    ("integration_contract", r"\b(contract|api surface|response shape|schema frozen)\b"),
    ("preference", r"\b(prefer(s|red)?|always use|default to)\b"),
]

_PROCEDURAL_PATTERNS = re.compile(
    r"\b(step ?1\b|^\d+[.)]\s|how to|workflow|checklist|procedure)\b",
    re.IGNORECASE | re.MULTILINE,
)

_WORKING_MARKERS = re.compile(
    r"\b(scratch|todo for now|temporary|wip|thinking aloud|note-to-self)\b", re.IGNORECASE
)


@dataclass
class ClassifierCandidate:
    layer: Layer
    entry_type: str
    title: str
    body: str
    confidence: float
    rationale: str
    source_event_ids: list[str] = field(default_factory=list)
    metadata: dict[str, Any] = field(default_factory=dict)


def _detect_entry_type(text: str) -> tuple[str, float, str]:
    """Pick the best-matching semantic entry_type and a base confidence."""
    lower = text.lower()
    best: tuple[str, float, str] | None = None
    for entry_type, pat in _DECISION_PATTERNS:
        try:
            if re.search(pat, lower):
                conf = 0.55 + (0.1 if entry_type in ("adr", "decision") else 0.0)
                reason = f"matched {entry_type} pattern"
                if best is None or conf > best[1]:
                    best = (entry_type, conf, reason)
        except re.error:
            continue
    return best if best else ("note", 0.4, "no strong pattern, defaulted to note")


def classify_text(
    text: str,
    *,
    source: str = "run_event",
    source_event_ids: list[str] | None = None,
    agent_id: str | None = None,
) -> ClassifierCandidate | None:
    """Classify a single text blob into a single candidate entry."""
    body = (text or "").strip()
    if not body or len(body) < 20:
        return None

    if _WORKING_MARKERS.search(body):
        return ClassifierCandidate(
            layer="working",
            entry_type="note",
            title=_derive_title(body),
            body=body,
            confidence=0.4,
            rationale="working-memory marker matched",
            source_event_ids=list(source_event_ids or []),
            metadata={"source": source, "agent_id": agent_id},
        )

    if _PROCEDURAL_PATTERNS.search(body):
        return ClassifierCandidate(
            layer="procedural",
            entry_type="runbook",
            title=_derive_title(body),
            body=body,
            confidence=0.6,
            rationale="procedural / checklist markers matched",
            source_event_ids=list(source_event_ids or []),
            metadata={"source": source, "agent_id": agent_id},
        )

    entry_type, base_conf, reason = _detect_entry_type(body)
    # Very short bodies with only "note" type are not worth promoting.
    if entry_type == "note" and len(body) < 80:
        return None

    return ClassifierCandidate(
        layer="semantic",
        entry_type=entry_type,
        title=_derive_title(body),
        body=body,
        confidence=round(base_conf, 3),
        rationale=reason,
        source_event_ids=list(source_event_ids or []),
        metadata={"source": source, "agent_id": agent_id},
    )


def classify_run_events(events: list[dict[str, Any]]) -> list[ClassifierCandidate]:
    """Classify a batch of run events into candidate memory entries.

    Each event is expected to be a dict shaped like RunEvent (id/event_type/
    message/payload_json). We only consider "log", "decision", "finding",
    "tool_output" event types; others are ignored.
    """
    out: list[ClassifierCandidate] = []
    accepted_types = {"log", "decision", "finding", "tool_output", "summary"}
    for ev in events or []:
        et = str(ev.get("event_type") or "").lower()
        if et not in accepted_types:
            continue
        msg = str(ev.get("message") or "")
        payload = ev.get("payload_json") or {}
        extra = ""
        if isinstance(payload, dict):
            for key in ("text", "content", "summary", "finding"):
                val = payload.get(key)
                if isinstance(val, str) and val.strip():
                    extra = val
                    break
        merged = (msg + "\n" + extra).strip()
        cand = classify_text(
            merged,
            source=f"run_event:{et}",
            source_event_ids=[str(ev.get("id") or "")] if ev.get("id") else None,
            agent_id=(payload.get("agent_id") if isinstance(payload, dict) else None),
        )
        if cand is not None:
            out.append(cand)
    return out


def _derive_title(body: str) -> str:
    first = body.splitlines()[0] if body else "Memory candidate"
    # Trim leading list markers / quote chars.
    first = re.sub(r"^[\s>*\-]+", "", first).strip()
    return (first[:150] or "Memory candidate")[:255]


__all__ = [
    "ClassifierCandidate",
    "classify_run_events",
    "classify_text",
]
