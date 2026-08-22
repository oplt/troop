"""Memory promotion rules engine (T2.2).

Encodes the rules from memory.txt for deciding whether a candidate entry
should auto-promote, be suggested for approval, or be dropped.

Project-level promotion (memory.txt):
  * affects architecture / changes decision
  * establishes reusable fix
  * introduces dependency rule
  * explains recurring failure

Company-level promotion (memory.txt, stricter):
  * reusable across projects
  * policy-level
  * standard-setting
  * changes how agents behave
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any, Final, Literal

Verdict = Literal["auto", "suggest", "skip"]


@dataclass
class PromotionCandidate:
    entry_type: str
    title: str
    body: str
    metadata: dict[str, Any] = field(default_factory=dict)
    scope: str = "project"  # "project" | "company"
    source: str = "classifier"
    source_agent_id: str | None = None
    source_task_id: str | None = None
    source_run_id: str | None = None


@dataclass
class PromotionEvaluation:
    verdict: Verdict
    score: float  # 0..1
    matched_rules: list[str] = field(default_factory=list)
    rationale: str = ""


# Regex patterns matched against title + body (case-insensitive) to
# accumulate promotion score.
_PROJECT_RULE_PATTERNS: Final[list[tuple[str, str, float]]] = [
    (
        "architecture_shift",
        r"\b(architect|design decision|rearchitect|refactor pattern|module boundary)\b",
        0.35,
    ),
    ("decision_change", r"\b(decided|chose|picked|will use|dropping|deprecat)\b", 0.2),
    (
        "reusable_fix",
        r"\b(fix pattern|recurring bug|generalized fix|works everywhere|repeats in)\b",
        0.25,
    ),
    ("dependency_rule", r"\b(version ?pin|upgrade|downgrade|package (lock|bump|restrict))\b", 0.25),
    (
        "recurring_failure",
        r"\b(keeps failing|kept failing|repeats|flaky|regressed|again broken)\b",
        0.25,
    ),
    ("explicit_adr", r"\b(adr|architecture decision record)\b", 0.4),
    ("policy_keyword", r"\b(must|never|always|policy)\b", 0.1),
    ("api_contract", r"\b(contract|invariant|schema (locked|frozen))\b", 0.2),
]

_COMPANY_RULE_PATTERNS: Final[list[tuple[str, str, float]]] = [
    (
        "cross_project",
        r"\b(cross-project|all projects|company[- ]wide|org[- ]wide|everyone must)\b",
        0.45,
    ),
    ("coding_standard", r"\b(coding standard|style guide|convention|naming convention)\b", 0.35),
    ("security_policy", r"\b(security (policy|rule)|compliance|gdpr|soc2|pii)\b", 0.4),
    ("deploy_rule", r"\b(deploy(ment)? (rule|policy|freeze)|release process)\b", 0.3),
    ("tool_mandate", r"\b(must use|standard tool|approved (library|framework))\b", 0.3),
    ("glossary_term", r"\b(glossary|definition|canonical name)\b", 0.2),
]

# Entry types inherently qualify for project-level promotion.
_AUTO_PROJECT_TYPES: Final[set[str]] = {"adr", "decision", "dependency_rule", "runbook"}
# Company scope auto-types.
_AUTO_COMPANY_TYPES: Final[set[str]] = {"policy", "convention", "glossary"}

_AUTO_THRESHOLD: Final[float] = 0.6
_SUGGEST_THRESHOLD: Final[float] = 0.25

_NEVER_PROMOTE_SOURCES: Final[set[str]] = {
    "transient_log",
    "speculative_reasoning",
    "failed_attempt",
    "temporary_tool_error",
}
_HUMAN_REVIEW_PATTERN: Final[re.Pattern[str]] = re.compile(
    r"\b(company policy|security rule|security policy|legal|compliance|gdpr|soc2|pii|cross-project)\b",
    re.IGNORECASE,
)


def _score_body(text: str, patterns: list[tuple[str, str, float]]) -> tuple[float, list[str]]:
    if not text:
        return 0.0, []
    lower = text.lower()
    matched: list[str] = []
    total = 0.0
    for name, pat, weight in patterns:
        try:
            if re.search(pat, lower):
                matched.append(name)
                total += weight
        except re.error:
            continue
    return min(total, 1.0), matched


def _type_bonus(entry_type: str, auto_types: set[str]) -> float:
    return 0.5 if entry_type in auto_types else 0.0


def _length_penalty(body: str) -> float:
    """Very short bodies are less valuable. Penalty is subtracted."""
    n = len(body or "")
    if n < 40:
        return 0.25
    if n < 120:
        return 0.1
    return 0.0


def evaluate_project_promotion(candidate: PromotionCandidate) -> PromotionEvaluation:
    if candidate.source in _NEVER_PROMOTE_SOURCES or candidate.metadata.get("transient"):
        return PromotionEvaluation(
            verdict="skip",
            score=0.0,
            matched_rules=["never_promote_transient"],
            rationale="Transient, speculative, failed, and temporary-error observations are not durable memory.",
        )

    text_score, matched = _score_body(
        f"{candidate.title}\n{candidate.body}", _PROJECT_RULE_PATTERNS
    )
    bonus = _type_bonus(candidate.entry_type, _AUTO_PROJECT_TYPES)
    penalty = _length_penalty(candidate.body)
    score = max(0.0, min(1.0, text_score + bonus - penalty))
    if bonus:
        matched.append(f"type:{candidate.entry_type}")

    stable_source_score = 0.9 if candidate.source == "project_decision" else None
    if candidate.source == "task_close" and candidate.metadata.get("stable_task_outcome"):
        stable_source_score = 0.75
    if candidate.source == "agent_memory" and candidate.metadata.get("approved"):
        stable_source_score = 0.8
    if candidate.entry_type == "constraint" and candidate.metadata.get("verified"):
        stable_source_score = max(stable_source_score or 0.0, 0.85)
        matched.append("verified_constraint")
    if stable_source_score is not None:
        score = max(score, stable_source_score)
        matched.append(f"stable_source:{candidate.source}")

    requires_human = candidate.source not in {"project_decision"} and (
        candidate.entry_type in {"policy", "security", "legal"}
        or _HUMAN_REVIEW_PATTERN.search(f"{candidate.title}\n{candidate.body}") is not None
    )
    if requires_human:
        verdict = "suggest"
        matched.append("human_review_required")
    elif score >= _AUTO_THRESHOLD:
        verdict: Verdict = "auto"
    elif score >= _SUGGEST_THRESHOLD:
        verdict = "suggest"
    else:
        verdict = "skip"

    return PromotionEvaluation(
        verdict=verdict,
        score=round(score, 3),
        matched_rules=matched,
        rationale=(
            f"score={score:.2f} (text={text_score:.2f} bonus={bonus:.2f} penalty={penalty:.2f}); "
            f"matched={matched or ['-']}"
        ),
    )


def evaluate_company_promotion(candidate: PromotionCandidate) -> PromotionEvaluation:
    if candidate.source in _NEVER_PROMOTE_SOURCES or candidate.metadata.get("transient"):
        return PromotionEvaluation(
            verdict="skip",
            score=0.0,
            matched_rules=["never_promote_transient"],
            rationale="Transient, speculative, failed, and temporary-error observations are not durable memory.",
        )
    text_score, matched = _score_body(
        f"{candidate.title}\n{candidate.body}", _COMPANY_RULE_PATTERNS
    )
    bonus = _type_bonus(candidate.entry_type, _AUTO_COMPANY_TYPES)
    penalty = _length_penalty(candidate.body)
    # Company bar is stricter: require matched rules or type bonus.
    score = max(0.0, min(1.0, text_score + bonus - penalty))
    if bonus:
        matched.append(f"type:{candidate.entry_type}")

    # Company scope is always a human-reviewed promotion boundary. A high
    # score affects priority, never approval bypass.
    verdict = "suggest" if score >= 0.4 else "skip"

    return PromotionEvaluation(
        verdict=verdict,
        score=round(score, 3),
        matched_rules=matched,
        rationale=(
            f"company-score={score:.2f} text={text_score:.2f} bonus={bonus:.2f} penalty={penalty:.2f}; "
            f"matched={matched or ['-']}"
        ),
    )


def evaluate(candidate: PromotionCandidate) -> PromotionEvaluation:
    if candidate.scope == "company":
        return evaluate_company_promotion(candidate)
    return evaluate_project_promotion(candidate)


__all__ = [
    "PromotionCandidate",
    "PromotionEvaluation",
    "evaluate",
    "evaluate_company_promotion",
    "evaluate_project_promotion",
]
