from __future__ import annotations

import json
import re
from dataclasses import dataclass

from backend.modules.memory.classifier import classify_text
from backend.modules.memory.layer.redaction import sanitize_for_storage

_EXTRACTION_JSON_SCHEMA = (
    'Return JSON only: {"memories":[{"text":"...",'
    '"memory_type":"fact|preference|decision|constraint|outcome","confidence":0.0-1.0}]}'
)

_SYSTEM_PROMPT = """You extract durable facts from conversations for long-term agent memory.
Store only stable information: user preferences, constraints, decisions,
project facts, and task outcomes.
Do NOT store secrets, credentials, tokens, passwords, or transient chit-chat.
If nothing durable is present, return {"memories":[]}."""


@dataclass(slots=True)
class ExtractedMemory:
    text: str
    memory_type: str
    confidence: float
    source: str = "llm_extractor"


def extract_with_rules(
    messages: list[dict[str, str]],
    *,
    min_confidence: float = 0.45,
) -> list[ExtractedMemory]:
    """Rule-based extraction using the existing memory classifier."""
    out: list[ExtractedMemory] = []
    for msg in messages:
        role = str(msg.get("role") or "user")
        if role not in {"user", "assistant", "system"}:
            continue
        text = str(msg.get("content") or "").strip()
        if len(text) < 20:
            continue
        candidate = classify_text(text, source=f"interaction:{role}")
        if candidate is None or candidate.layer != "semantic":
            continue
        if candidate.confidence < min_confidence:
            continue
        safe, _ = sanitize_for_storage(candidate.body)
        if not safe:
            continue
        out.append(
            ExtractedMemory(
                text=safe,
                memory_type=candidate.entry_type,
                confidence=candidate.confidence,
                source="rule_extractor",
            )
        )
    return out


def parse_llm_extraction(raw: str) -> list[ExtractedMemory]:
    text = (raw or "").strip()
    if not text:
        return []
    # Strip markdown fences if present.
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*", "", text)
        text = re.sub(r"\s*```$", "", text)
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return []
    items = payload.get("memories") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    out: list[ExtractedMemory] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        body = str(item.get("text") or "").strip()
        if len(body) < 15:
            continue
        safe, _ = sanitize_for_storage(body)
        if not safe:
            continue
        memory_type = str(item.get("memory_type") or "fact")
        try:
            confidence = float(item.get("confidence", 0.6))
        except (TypeError, ValueError):
            confidence = 0.6
        out.append(
            ExtractedMemory(
                text=safe,
                memory_type=memory_type,
                confidence=max(0.0, min(confidence, 1.0)),
                source="llm_extractor",
            )
        )
    return out


def build_llm_extraction_prompt(messages: list[dict[str, str]]) -> str:
    lines = ["Extract durable memories from this conversation:", ""]
    for msg in messages[-12:]:
        role = str(msg.get("role") or "user").upper()
        content = str(msg.get("content") or "").strip()
        if content:
            lines.append(f"{role}: {content[:2000]}")
    lines.append("")
    lines.append(_EXTRACTION_JSON_SCHEMA)
    return "\n".join(lines)


__all__ = [
    "ExtractedMemory",
    "_SYSTEM_PROMPT",
    "build_llm_extraction_prompt",
    "extract_with_rules",
    "parse_llm_extraction",
]
