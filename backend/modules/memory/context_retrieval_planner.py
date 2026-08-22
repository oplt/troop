from __future__ import annotations

import asyncio
import re
from collections import Counter
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Literal

from backend.modules.orchestration.context_packet import count_text_tokens

ContextKind = Literal[
    "working",
    "episodic",
    "semantic_memory",
    "company",
    "procedural",
    "rag",
    "agent_memory",
]


@dataclass(frozen=True, slots=True)
class ContextCandidate:
    kind: ContextKind
    scope: str
    content: str
    relevance: float
    authority: float
    confidence: float
    tokens: int
    provenance: dict[str, Any] = field(default_factory=dict)
    source_id: str = ""
    canonical_key: str | None = None
    status: str = "current"
    valid_from: datetime | None = None
    valid_until: datetime | None = None


ContextLoader = Callable[[], Awaitable[list[ContextCandidate]]]
_TOKENS = re.compile(r"[a-z0-9_./:-]+", re.IGNORECASE)


class ContextRetrievalPlanner:
    """Load and select one governed context set across all memory layers."""

    def __init__(
        self,
        *,
        owner_id: str,
        project_id: str | None,
        company_id: str | None = None,
        task_id: str | None = None,
    ) -> None:
        self.owner_id = owner_id
        self.project_id = project_id
        self.company_id = company_id
        self.task_id = task_id

    async def retrieve(
        self,
        loaders: Mapping[str, ContextLoader],
        *,
        max_tokens: int,
        max_candidates: int = 20,
        max_per_source: int = 4,
    ) -> list[ContextCandidate]:
        batches = await asyncio.gather(*(loader() for loader in loaders.values()))
        return self.select(
            [candidate for batch in batches for candidate in batch],
            max_tokens=max_tokens,
            max_candidates=max_candidates,
            max_per_source=max_per_source,
        )

    def select(
        self,
        candidates: list[ContextCandidate],
        *,
        max_tokens: int,
        max_candidates: int = 20,
        max_per_source: int = 4,
    ) -> list[ContextCandidate]:
        now = datetime.now(UTC)
        eligible = [candidate for candidate in candidates if self._is_eligible(candidate, now)]
        ranked = sorted(eligible, key=self._rank_score, reverse=True)

        # One authoritative value per canonical fact. Company policy is a hard
        # precedence boundary over lower-scope observations for the same key.
        by_canonical: dict[str, ContextCandidate] = {}
        unkeyed: list[ContextCandidate] = []
        for candidate in ranked:
            if not candidate.canonical_key:
                unkeyed.append(candidate)
                continue
            current = by_canonical.get(candidate.canonical_key)
            if current is None or self._wins_conflict(candidate, current):
                by_canonical[candidate.canonical_key] = candidate
        ranked = sorted([*by_canonical.values(), *unkeyed], key=self._rank_score, reverse=True)

        selected: list[ContextCandidate] = []
        source_counts: Counter[str] = Counter()
        used_tokens = 0
        for candidate in ranked:
            source = candidate.source_id or candidate.kind
            if source_counts[source] >= max(1, max_per_source):
                continue
            if self._near_duplicate(candidate, selected):
                continue
            if used_tokens + candidate.tokens > max_tokens:
                continue
            selected.append(candidate)
            source_counts[source] += 1
            used_tokens += candidate.tokens
            if len(selected) >= max_candidates:
                break
        return selected

    def _is_eligible(self, candidate: ContextCandidate, now: datetime) -> bool:
        if candidate.status != "current":
            return False
        if candidate.valid_until is not None:
            valid_until = candidate.valid_until
            if valid_until.tzinfo is None:
                valid_until = valid_until.replace(tzinfo=UTC)
            if valid_until <= now:
                return False
        provenance = candidate.provenance
        owner_id = provenance.get("owner_id")
        if owner_id and str(owner_id) != self.owner_id:
            return False
        project_id = provenance.get("project_id")
        if (
            candidate.scope in {"project", "task", "agent"}
            and project_id
            and str(project_id) != str(self.project_id or "")
        ):
            return False
        company_id = provenance.get("company_id")
        if (
            candidate.scope == "company"
            and company_id
            and str(company_id) != str(self.company_id or "")
        ):
            return False
        source_task_id = provenance.get("source_task_id") or provenance.get("task_id")
        if (
            candidate.scope == "task"
            and source_task_id
            and str(source_task_id) != str(self.task_id or "")
        ):
            return False
        return bool(candidate.content.strip()) and candidate.tokens > 0

    @staticmethod
    def _rank_score(candidate: ContextCandidate) -> float:
        scope_specificity = {
            "task": 1.0,
            "agent": 0.85,
            "project": 0.75,
            "company": 0.6,
            "global": 0.4,
        }.get(candidate.scope, 0.5)
        recency = 0.5
        if candidate.valid_from is not None:
            value = candidate.valid_from
            if value.tzinfo is None:
                value = value.replace(tzinfo=UTC)
            age_days = max(0.0, (datetime.now(UTC) - value).total_seconds() / 86400)
            recency = max(0.0, 1.0 - min(age_days, 365.0) / 365.0)
        return (
            0.36 * candidate.relevance
            + 0.34 * candidate.authority
            + 0.14 * scope_specificity
            + 0.11 * candidate.confidence
            + 0.05 * recency
        )

    @staticmethod
    def _wins_conflict(candidate: ContextCandidate, current: ContextCandidate) -> bool:
        candidate_is_company_policy = (
            candidate.scope == "company" and candidate.provenance.get("entry_type") == "policy"
        )
        current_is_company_policy = (
            current.scope == "company" and current.provenance.get("entry_type") == "policy"
        )
        if candidate_is_company_policy != current_is_company_policy:
            return candidate_is_company_policy
        return ContextRetrievalPlanner._rank_score(candidate) > ContextRetrievalPlanner._rank_score(
            current
        )

    @staticmethod
    def _near_duplicate(
        candidate: ContextCandidate,
        selected: list[ContextCandidate],
        *,
        threshold: float = 0.9,
    ) -> bool:
        tokens = {token.lower() for token in _TOKENS.findall(candidate.content)}
        for item in selected:
            other = {token.lower() for token in _TOKENS.findall(item.content)}
            similarity = len(tokens & other) / max(len(tokens | other), 1)
            if similarity >= threshold:
                return True
        return False

    @staticmethod
    def candidate(
        *,
        kind: ContextKind,
        scope: str,
        content: str,
        relevance: float,
        authority: float,
        confidence: float = 0.5,
        provenance: dict[str, Any] | None = None,
        source_id: str = "",
        canonical_key: str | None = None,
        status: str = "current",
        valid_from: datetime | None = None,
        valid_until: datetime | None = None,
    ) -> ContextCandidate:
        return ContextCandidate(
            kind=kind,
            scope=scope,
            content=content,
            relevance=max(0.0, min(1.0, relevance)),
            authority=max(0.0, min(1.0, authority)),
            confidence=max(0.0, min(1.0, confidence)),
            tokens=count_text_tokens(content),
            provenance=dict(provenance or {}),
            source_id=source_id,
            canonical_key=canonical_key,
            status=status,
            valid_from=valid_from,
            valid_until=valid_until,
        )


__all__ = ["ContextCandidate", "ContextRetrievalPlanner"]
