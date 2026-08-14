"""Optional qualitative model-as-judge for evaluation runs (EVAL-001B)."""

from __future__ import annotations

from typing import Any

JUDGE_VERSION_ID = "local-heuristic-v1"


def run_qualitative_judge(
    *,
    output_text: str | None,
    output_json: dict | None,
    rubric: dict[str, Any] | None,
) -> tuple[float | None, str | None, str | None]:
    """Score qualitative dimensions only when an explicit rubric is provided."""
    if not rubric:
        return None, None, None

    criteria = rubric.get("criteria")
    if not isinstance(criteria, list) or not criteria:
        return None, None, None

    haystack = (output_text or "").lower()
    if output_json:
        haystack += " " + str(output_json).lower()

    hits = 0
    for item in criteria:
        if not isinstance(item, dict):
            continue
        keyword = str(item.get("keyword") or item.get("contains") or "").strip().lower()
        if keyword and keyword in haystack:
            hits += 1

    score = round(hits / len(criteria), 4) if criteria else 0.0
    notes = f"Qualitative judge {JUDGE_VERSION_ID}: {hits}/{len(criteria)} rubric criteria matched."
    return score, notes, JUDGE_VERSION_ID
