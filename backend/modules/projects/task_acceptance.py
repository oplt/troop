"""Pure task acceptance criteria parsing and output matching helpers."""

from __future__ import annotations

import json
import math
import re
from typing import Any


def task_output_text(
    *,
    result_summary: str | None,
    result_payload_json: dict[str, Any] | None,
) -> str:
    payload = result_payload_json or {}
    summary = result_summary or ""
    if not summary and isinstance(payload, dict):
        summary = str(payload.get("summary") or payload.get("final_output") or "")
    return "\n".join(
        chunk
        for chunk in [
            str(summary).strip(),
            json.dumps(payload, default=str) if payload else "",
        ]
        if chunk
    )


def acceptance_criteria_items(text: str) -> list[str]:
    items: list[str] = []
    for raw_line in str(text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        normalized = re.sub(r"^[-*]\s+", "", line)
        normalized = re.sub(r"^\d+\.\s+", "", normalized)
        if normalized:
            items.append(normalized)
    if not items and str(text or "").strip():
        items.append(str(text).strip())
    return items


def acceptance_evidence_excerpt(item: str, output_text: str) -> str:
    lowered = output_text.lower()
    for token in re.findall(r"[a-z0-9]+", item.lower()):
        if len(token) <= 2:
            continue
        index = lowered.find(token)
        if index >= 0:
            start = max(0, index - 40)
            end = min(len(output_text), index + 120)
            return output_text[start:end].strip()
    return output_text[:160].strip()


def acceptance_item_check(item: str, output_text: str) -> dict[str, Any]:
    required_tokens = [token for token in re.findall(r"[a-z0-9]+", item.lower()) if len(token) > 2]
    if not required_tokens:
        return {"item": item, "passed": True, "evidence_excerpt": ""}
    output_tokens = set(re.findall(r"[a-z0-9]+", output_text.lower()))
    overlap = sum(1 for token in required_tokens if token in output_tokens)
    passed = overlap >= max(1, math.ceil(len(required_tokens) * 0.5))
    return {
        "item": item,
        "passed": passed,
        "evidence_excerpt": acceptance_evidence_excerpt(item, output_text) if passed else "",
    }


def acceptance_item_matches_output(item: str, output_text: str) -> bool:
    return acceptance_item_check(item, output_text)["passed"]
