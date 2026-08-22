from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime

from backend.modules.memory.context_retrieval_planner import ContextCandidate
from backend.modules.memory.promotion_rules import PromotionEvaluation


@dataclass(frozen=True, slots=True)
class MemoryRegressionReport:
    retrieval_precision: float
    stale_memory_rate: float
    contradicted_memory_rate: float
    scope_leakage_rate: float
    unsupported_promotion_rate: float

    @property
    def passed(self) -> bool:
        return (
            self.stale_memory_rate == 0
            and self.contradicted_memory_rate == 0
            and self.scope_leakage_rate == 0
            and self.unsupported_promotion_rate == 0
        )


def evaluate_memory_regression(
    candidates: list[ContextCandidate],
    *,
    useful_source_ids: set[str],
    owner_id: str,
    project_id: str | None,
    promotion_results: list[tuple[PromotionEvaluation, bool]] | None = None,
    now: datetime | None = None,
) -> MemoryRegressionReport:
    """Measure usefulness, stale/conflicting injection, leakage, and promotion safety."""
    current_time = now or datetime.now(UTC)
    total = max(len(candidates), 1)
    useful = sum(item.source_id in useful_source_ids for item in candidates)
    stale = 0
    scope_leaks = 0
    canonical_counts: dict[str, int] = {}
    for item in candidates:
        valid_until = item.valid_until
        if valid_until is not None and valid_until.tzinfo is None:
            valid_until = valid_until.replace(tzinfo=UTC)
        if item.status != "current" or (valid_until is not None and valid_until <= current_time):
            stale += 1
        provenance = item.provenance
        if (
            provenance.get("owner_id")
            and str(provenance["owner_id"]) != owner_id
            or (
                item.scope in {"task", "project", "agent"}
                and provenance.get("project_id")
                and str(provenance["project_id"]) != str(project_id or "")
            )
        ):
            scope_leaks += 1
        if item.canonical_key:
            canonical_counts[item.canonical_key] = canonical_counts.get(item.canonical_key, 0) + 1
    contradicted = sum(count - 1 for count in canonical_counts.values() if count > 1)
    promotions = promotion_results or []
    automatic = [supported for result, supported in promotions if result.verdict == "auto"]
    unsupported = sum(not supported for supported in automatic)
    return MemoryRegressionReport(
        retrieval_precision=useful / total,
        stale_memory_rate=stale / total,
        contradicted_memory_rate=contradicted / total,
        scope_leakage_rate=scope_leaks / total,
        unsupported_promotion_rate=unsupported / max(len(automatic), 1),
    )


__all__ = ["MemoryRegressionReport", "evaluate_memory_regression"]
