"""Layer 6 — context packet assembly (Phase 6).

Versioned, sectioned user-context string for orchestration runs. Replaces ad-hoc string
concatenation with explicit section keys for telemetry and future token budgeting.
"""

from __future__ import annotations

import hashlib
import logging
import re
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)

CONTEXT_PACKET_SCHEMA_VERSION = "1.0"

# High-signal sections first; episodic / knowledge trimmed first when over global budget.
CONTEXT_SECTION_KEYS_IN_ORDER: tuple[str, ...] = (
    "prefix",
    "task_title",
    "task_description",
    "acceptance",
    "working_memory",
    "scratchpad",
    "shared_blackboard",
    "private_scratchpad",
    "semantic_memory",
    "procedural_snippets",
    "project_name",
    "project_goals",
    "agent_label",
    "agent_preferences",
    "agent_memory",
    "company_brief",
    "episodic_recall",
    "deep_recall",
    "knowledge",
    "comments",
    "artifacts",
    "previous_run",
    "replay",
    "input_payload",
)

# Sections that often overlap (semantic + RAG + memory layer); dedupe before prompt build.
_OVERLAPPING_CONTEXT_KEYS: frozenset[str] = frozenset(
    {
        "semantic_memory",
        "relevant_memory_context",
        "deep_recall",
        "knowledge",
        "episodic_recall",
    }
)


def _section_body_for_dedupe(text: str) -> str:
    stripped = (text or "").strip()
    if not stripped:
        return ""
    lines = stripped.splitlines()
    if lines and ":" in lines[0]:
        body = "\n".join(lines[1:]).strip() or lines[0].split(":", 1)[-1].strip()
    else:
        body = stripped
    return re.sub(r"\s+", " ", body.lower()).strip()


def _section_content_hash(text: str) -> str:
    body = _section_body_for_dedupe(text)
    return hashlib.sha256(body.encode("utf-8")).hexdigest()


def dedupe_context_sections(sections: dict[str, str]) -> dict[str, str]:
    """Drop duplicate memory/RAG sections that share identical normalized content."""
    seen_hashes: set[str] = set()
    out: dict[str, str] = {}

    def maybe_add(key: str, raw: str) -> None:
        stripped = (raw or "").strip()
        if not stripped:
            return
        if key in _OVERLAPPING_CONTEXT_KEYS:
            digest = _section_content_hash(stripped)
            if digest in seen_hashes:
                return
            seen_hashes.add(digest)
        out[key] = raw

    for key in CONTEXT_SECTION_KEYS_IN_ORDER:
        raw = sections.get(key)
        if raw:
            maybe_add(key, raw)
    for key, raw in sections.items():
        if key in out or key in CONTEXT_SECTION_KEYS_IN_ORDER:
            continue
        if raw:
            maybe_add(key, raw)
    return out


DEFAULT_SECTION_TOKEN_BUDGETS: dict[str, int] = {
    "prefix": 200,
    "task_title": 120,
    "task_description": 900,
    "acceptance": 400,
    "working_memory": 900,
    "scratchpad": 500,
    "shared_blackboard": 600,
    "private_scratchpad": 600,
    "semantic_memory": 800,
    "procedural_snippets": 700,
    "project_name": 80,
    "project_goals": 700,
    "agent_label": 80,
    "agent_preferences": 400,
    "agent_memory": 500,
    "company_brief": 200,
    "episodic_recall": 500,
    "deep_recall": 900,
    "knowledge": 600,
    "comments": 400,
    "artifacts": 400,
    "previous_run": 400,
    "replay": 1200,
    "input_payload": 1200,
}

DEFAULT_SECTION_PRIORITY_SCORES: dict[str, float] = {
    "prefix": 1.0,
    "task_title": 1.0,
    "task_description": 0.95,
    "acceptance": 0.98,
    "working_memory": 0.9,
    "scratchpad": 0.75,
    "shared_blackboard": 0.8,
    "private_scratchpad": 0.7,
    "semantic_memory": 0.72,
    "procedural_snippets": 0.68,
    "project_name": 0.55,
    "project_goals": 0.62,
    "agent_label": 0.5,
    "agent_preferences": 0.54,
    "agent_memory": 0.58,
    "company_brief": 0.45,
    "episodic_recall": 0.42,
    "deep_recall": 0.5,
    "knowledge": 0.65,
    "comments": 0.38,
    "artifacts": 0.36,
    "previous_run": 0.34,
    "replay": 0.32,
    "input_payload": 0.28,
}

_tiktoken_encoder: Any = None
_tiktoken_attempted: bool = False


def _get_token_encoder() -> Any:
    global _tiktoken_encoder, _tiktoken_attempted
    if _tiktoken_attempted:
        return _tiktoken_encoder
    _tiktoken_attempted = True
    try:
        import tiktoken

        _tiktoken_encoder = tiktoken.get_encoding("cl100k_base")
    except Exception as exc:  # pragma: no cover - optional dependency path
        logger.warning("tiktoken unavailable; using char/4 token heuristic: %s", exc)
        _tiktoken_encoder = None
    return _tiktoken_encoder


def count_text_tokens(text: str, enc: Any = None) -> int:
    if not text:
        return 0
    encoder = enc if enc is not None else _get_token_encoder()
    if encoder is None:
        return max(1, len(text) // 4)
    return len(encoder.encode(text))


def clip_text_to_token_budget(text: str, max_tokens: int, enc: Any = None) -> str:
    if max_tokens <= 0 or not text:
        return ""
    encoder = enc if enc is not None else _get_token_encoder()
    if encoder is None:
        return text[: max_tokens * 4]
    tokens = encoder.encode(text)
    if len(tokens) <= max_tokens:
        return text
    return encoder.decode(tokens[:max_tokens])


@dataclass
class ContextPacket:
    schema_version: str = CONTEXT_PACKET_SCHEMA_VERSION
    sections: dict[str, str] = field(default_factory=dict)

    def combined_user_prompt(
        self,
        max_chars: int = 12000,
        *,
        max_tokens: int | None = None,
        section_token_budgets: dict[str, int] | None = None,
        section_priority_scores: dict[str, float] | None = None,
    ) -> str:
        """Join sections with per-section token caps, then optional global token cap.

        When ``max_tokens`` is None, preserves legacy behavior: join all sections and
        truncate to ``max_chars`` only.
        """
        enc = _get_token_encoder()
        budgets = {**DEFAULT_SECTION_TOKEN_BUDGETS, **(section_token_budgets or {})}
        scores = {**DEFAULT_SECTION_PRIORITY_SCORES, **(section_priority_scores or {})}
        pieces: list[str] = []
        if max_tokens is None:
            for key in CONTEXT_SECTION_KEYS_IN_ORDER:
                raw = (self.sections.get(key) or "").strip()
                if raw:
                    pieces.append(raw)
            for key, raw in self.sections.items():
                if key in CONTEXT_SECTION_KEYS_IN_ORDER:
                    continue
                raw = (raw or "").strip()
                if raw:
                    pieces.append(raw)
            text = "\n\n".join(pieces)
            return text[:max_chars]

        candidates: list[tuple[str, int, float, str, int]] = []
        order = 0
        for key in CONTEXT_SECTION_KEYS_IN_ORDER:
            raw = (self.sections.get(key) or "").strip()
            if not raw:
                continue
            cap = max(0, budgets.get(key, 400))
            clipped = clip_text_to_token_budget(raw, cap, enc)
            t = count_text_tokens(clipped, enc)
            if clipped:
                candidates.append((key, order, float(scores.get(key, 0.3)), clipped, t))
            order += 1

        for key, raw in self.sections.items():
            if key in CONTEXT_SECTION_KEYS_IN_ORDER:
                continue
            raw = (raw or "").strip()
            if not raw:
                continue
            cap = max(0, budgets.get(key, 400))
            clipped = clip_text_to_token_budget(raw, cap, enc)
            t = count_text_tokens(clipped, enc)
            if clipped:
                candidates.append((key, order, float(scores.get(key, 0.3)), clipped, t))
            order += 1

        used = 0
        selected: list[tuple[int, str]] = []
        for _key, source_order, _score, clipped, t in sorted(
            candidates,
            key=lambda item: (-item[2], item[1]),
        ):
            if used + t > max_tokens:
                allow = max(0, max_tokens - used)
                clipped = clip_text_to_token_budget(clipped, allow, enc)
                t = count_text_tokens(clipped, enc)
            if clipped:
                selected.append((source_order, clipped))
            used += t
            if used >= max_tokens:
                break

        pieces = [piece for _source_order, piece in sorted(selected, key=lambda item: item[0])]
        text = "\n\n".join(pieces)
        if len(text) > max_chars:
            text = text[:max_chars]
        return text

    def telemetry(self) -> dict[str, Any]:
        enc = _get_token_encoder()
        chars = {k: len(v) for k, v in self.sections.items()}
        tokens = {k: count_text_tokens(v, enc) for k, v in self.sections.items()}
        return {
            "schema_version": self.schema_version,
            "section_keys": list(self.sections),
            "section_chars": chars,
            "section_tokens": tokens,
            "total_chars": sum(chars.values()),
            "total_tokens": sum(tokens.values()),
        }


def log_context_packet_telemetry(packet: ContextPacket, *, run_id: str) -> None:
    from backend.modules.memory.metrics import record_context_packet_histograms

    record_context_packet_histograms(packet.sections)
    payload = packet.telemetry()
    logger.info(
        "context_packet_built run_id=%s total_chars=%s total_tokens=%s keys=%s",
        run_id,
        payload["total_chars"],
        payload.get("total_tokens"),
        ",".join(payload["section_keys"]),
    )
