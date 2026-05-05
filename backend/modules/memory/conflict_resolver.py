"""Memory conflict resolver service (T2.3).

Responsibilities:
  - Pre-write semantic dedup via embedding cosine similarity.
  - Pre-write contradiction detection (heuristic, LLM-free MVP).
  - Classify candidates as: duplicate / contradicts / unique.
  - Produce actionable conflict reports that the service layer converts
    into approval requests when promotion gating is enabled.
"""

from __future__ import annotations

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Any, Literal

from backend.modules.memory.models import SemanticMemoryEntry

ConflictKind = Literal["duplicate", "contradicts", "unique"]

_NEG_PATTERN = re.compile(
    r"\b(never|don'?t|do not|cannot|must not|shouldn'?t|should not|no longer|stop|remove|avoid)\b",
    re.IGNORECASE,
)
_DIRECTIVE_PATTERN = re.compile(
    r"\b(always|must|require[ds]?|mandated|prefer|default to|use)\b", re.IGNORECASE
)
_VERSION_PATTERN = re.compile(r"\bv?(\d+\.\d+(\.\d+)?)\b")

_DUP_THRESHOLD = 0.92
_SIM_CONTRA_THRESHOLD = 0.75


@dataclass
class ConflictHit:
    kind: ConflictKind
    similarity: float
    entry_id: str
    entry_title: str
    reason: str = ""


@dataclass
class ConflictReport:
    duplicates: list[ConflictHit] = field(default_factory=list)
    contradictions: list[ConflictHit] = field(default_factory=list)

    @property
    def has_any(self) -> bool:
        return bool(self.duplicates or self.contradictions)

    @property
    def best_duplicate(self) -> ConflictHit | None:
        if not self.duplicates:
            return None
        return max(self.duplicates, key=lambda h: h.similarity)


def _cosine(a: Iterable[float] | None, b: Iterable[float] | None) -> float:
    if a is None or b is None:
        return 0.0
    va = list(a)
    vb = list(b)
    if not va or not vb or len(va) != len(vb):
        return 0.0
    dot = sum(x * y for x, y in zip(va, vb))
    na = math.sqrt(sum(x * x for x in va))
    nb = math.sqrt(sum(y * y for y in vb))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def _normalize_text(s: str) -> str:
    return re.sub(r"\s+", " ", (s or "").strip().lower())


def _polarity_clash(a: str, b: str) -> bool:
    """Detects whether one text negates a directive the other asserts."""
    a_neg = bool(_NEG_PATTERN.search(a))
    b_neg = bool(_NEG_PATTERN.search(b))
    a_dir = bool(_DIRECTIVE_PATTERN.search(a))
    b_dir = bool(_DIRECTIVE_PATTERN.search(b))
    if a_neg and b_dir and not b_neg:
        return True
    if b_neg and a_dir and not a_neg:
        return True
    return False


def _version_clash(a: str, b: str) -> bool:
    """Detects conflicting version pins ("use v1.2" vs "use v2.0")."""
    av = {m.group(1) for m in _VERSION_PATTERN.finditer(a)}
    bv = {m.group(1) for m in _VERSION_PATTERN.finditer(b)}
    if not av or not bv:
        return False
    return bool(av.isdisjoint(bv))


def detect(
    candidate_embedding: list[float] | None,
    candidate_title: str,
    candidate_body: str,
    candidate_entry_type: str,
    existing: Iterable[SemanticMemoryEntry],
    *,
    ignore_entry_id: str | None = None,
) -> ConflictReport:
    cand_txt = _normalize_text(f"{candidate_title}\n{candidate_body}")
    report = ConflictReport()
    for row in existing:
        if ignore_entry_id and row.id == ignore_entry_id:
            continue
        if row.entry_type != candidate_entry_type:
            # Only compare within the same typed bucket.
            continue
        row_txt = _normalize_text(f"{row.title}\n{row.body}")
        sim = _cosine(candidate_embedding, row.embedding_vector)
        # If embeddings missing on either side, fall back to token-set ratio.
        if sim <= 0.0:
            sim = _token_jaccard(cand_txt, row_txt)
        if sim >= _DUP_THRESHOLD:
            report.duplicates.append(
                ConflictHit(
                    kind="duplicate",
                    similarity=round(sim, 3),
                    entry_id=row.id,
                    entry_title=row.title,
                    reason="cosine>=0.92 (near-duplicate)",
                )
            )
        elif sim >= _SIM_CONTRA_THRESHOLD:
            if _polarity_clash(cand_txt, row_txt) or _version_clash(cand_txt, row_txt):
                report.contradictions.append(
                    ConflictHit(
                        kind="contradicts",
                        similarity=round(sim, 3),
                        entry_id=row.id,
                        entry_title=row.title,
                        reason="polarity or version clash at sim>=0.75",
                    )
                )
    return report


def _token_jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"[a-z0-9]+", a))
    tb = set(re.findall(r"[a-z0-9]+", b))
    if not ta or not tb:
        return 0.0
    inter = ta & tb
    union = ta | tb
    if not union:
        return 0.0
    return len(inter) / len(union)


def summarize(report: ConflictReport) -> dict[str, Any]:
    return {
        "duplicates": [h.__dict__ for h in report.duplicates],
        "contradictions": [h.__dict__ for h in report.contradictions],
        "has_conflict": report.has_any,
    }


__all__ = [
    "ConflictHit",
    "ConflictReport",
    "detect",
    "summarize",
]
