"""Layer 6 — context packet assembly (Phase 6).

Versioned, sectioned user-context string for orchestration runs. Replaces ad-hoc string
concatenation with explicit section keys for telemetry and future token budgeting.
"""

from __future__ import annotations

import logging
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
    ) -> str:
        """Join sections with per-section token caps, then optional global token cap.

        When ``max_tokens`` is None, preserves legacy behavior: join all sections and
        truncate to ``max_chars`` only.
        """
        enc = _get_token_encoder()
        budgets = {**DEFAULT_SECTION_TOKEN_BUDGETS, **(section_token_budgets or {})}
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

        used = 0
        for key in CONTEXT_SECTION_KEYS_IN_ORDER:
            raw = (self.sections.get(key) or "").strip()
            if not raw:
                continue
            cap = max(0, budgets.get(key, 400))
            clipped = clip_text_to_token_budget(raw, cap, enc)
            t = count_text_tokens(clipped, enc)
            if used + t > max_tokens:
                allow = max(0, max_tokens - used)
                clipped = clip_text_to_token_budget(clipped, allow, enc)
                t = count_text_tokens(clipped, enc)
            if clipped:
                pieces.append(clipped)
            used += t
            if used >= max_tokens:
                break

        for key, raw in self.sections.items():
            if key in CONTEXT_SECTION_KEYS_IN_ORDER:
                continue
            raw = (raw or "").strip()
            if not raw:
                continue
            cap = max(0, budgets.get(key, 400))
            clipped = clip_text_to_token_budget(raw, cap, enc)
            t = count_text_tokens(clipped, enc)
            if used + t > max_tokens:
                allow = max(0, max_tokens - used)
                clipped = clip_text_to_token_budget(clipped, allow, enc)
                t = count_text_tokens(clipped, enc)
            if clipped:
                pieces.append(clipped)
            used += t
            if used >= max_tokens:
                break

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
