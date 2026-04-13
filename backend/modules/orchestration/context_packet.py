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


@dataclass
class ContextPacket:
    schema_version: str = CONTEXT_PACKET_SCHEMA_VERSION
    sections: dict[str, str] = field(default_factory=dict)

    def combined_user_prompt(self, max_chars: int = 12000) -> str:
        parts = [s.strip() for s in self.sections.values() if s and str(s).strip()]
        text = "\n\n".join(parts)
        return text[:max_chars]

    def telemetry(self) -> dict[str, Any]:
        chars = {k: len(v) for k, v in self.sections.items()}
        return {
            "schema_version": self.schema_version,
            "section_keys": list(self.sections),
            "section_chars": chars,
            "total_chars": sum(chars.values()),
        }


def log_context_packet_telemetry(packet: ContextPacket, *, run_id: str) -> None:
    payload = packet.telemetry()
    logger.info(
        "context_packet_built run_id=%s total_chars=%s keys=%s",
        run_id,
        payload["total_chars"],
        ",".join(payload["section_keys"]),
    )
