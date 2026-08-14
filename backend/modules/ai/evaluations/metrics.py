"""Per-case evaluation metrics (EVAL-001B)."""

from __future__ import annotations

import json
from typing import Any


def _schema_valid(response_format: str, output_json: dict | None, output_text: str | None) -> bool:
    if str(response_format or "text").lower() != "json":
        return True
    if isinstance(output_json, dict):
        return True
    if output_text:
        try:
            parsed = json.loads(output_text)
            return isinstance(parsed, dict)
        except json.JSONDecodeError:
            return False
    return False


def _tool_plan_valid(case, output_json: dict | None, output_text: str | None) -> bool | None:
    provenance = dict(getattr(case, "provenance_json", None) or {})
    expected_tools = provenance.get("expected_tools")
    if not isinstance(expected_tools, list) or not expected_tools:
        snapshot = dict(getattr(case, "input_snapshot_json", None) or {})
        selected = snapshot.get("selected_span")
        if isinstance(selected, dict):
            tool = (selected.get("safe_payload") or {}).get("tool")
            if tool:
                expected_tools = [str(tool)]
    if not expected_tools:
        return None
    haystack = json.dumps(output_json or {}, sort_keys=True).lower()
    if output_text:
        haystack += " " + output_text.lower()
    return all(str(tool).lower() in haystack for tool in expected_tools)


def build_case_metrics(
    *,
    case,
    ai_run,
    passed: bool,
    response_format: str,
    qualitative_score: float | None = None,
) -> dict[str, Any]:
    correction = getattr(case, "correction_json", None)
    provenance = dict(getattr(case, "provenance_json", None) or {})
    return {
        "task_success": bool(passed),
        "schema_validity": _schema_valid(
            response_format,
            getattr(ai_run, "output_json", None),
            getattr(ai_run, "output_text", None),
        ),
        "tool_plan_valid": _tool_plan_valid(
            case,
            getattr(ai_run, "output_json", None),
            getattr(ai_run, "output_text", None),
        ),
        "human_correction_case": bool(correction),
        "human_edit_or_reject": bool(correction),
        "latency_ms": int(getattr(ai_run, "latency_ms", 0) or 0),
        "input_tokens": int(getattr(ai_run, "input_tokens", 0) or 0),
        "output_tokens": int(getattr(ai_run, "output_tokens", 0) or 0),
        "total_tokens": int(getattr(ai_run, "total_tokens", 0) or 0),
        "estimated_cost_micros": int(getattr(ai_run, "estimated_cost_micros", 0) or 0),
        "qualitative_score": qualitative_score,
        "source_provenance": {
            "workflow_version_id": provenance.get("workflow_version_id"),
            "prompt_version_id": provenance.get("prompt_version_id"),
            "model_name": provenance.get("model_name"),
        },
    }


def aggregate_metrics(item_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    if not item_metrics:
        return {
            "task_success_rate": 0.0,
            "schema_validity_rate": 0.0,
            "tool_plan_valid_rate": None,
            "human_correction_cases": 0,
            "avg_latency_ms": 0.0,
            "total_tokens": 0,
            "total_cost_micros": 0,
            "avg_qualitative_score": None,
        }

    total = len(item_metrics)
    tool_plan_values = [
        item["tool_plan_valid"] for item in item_metrics if item.get("tool_plan_valid") is not None
    ]
    qualitative_values = [
        float(item["qualitative_score"])
        for item in item_metrics
        if item.get("qualitative_score") is not None
    ]
    return {
        "task_success_rate": round(
            sum(1 for item in item_metrics if item.get("task_success")) / total,
            4,
        ),
        "schema_validity_rate": round(
            sum(1 for item in item_metrics if item.get("schema_validity")) / total,
            4,
        ),
        "tool_plan_valid_rate": (
            round(sum(1 for value in tool_plan_values if value) / len(tool_plan_values), 4)
            if tool_plan_values
            else None
        ),
        "human_correction_cases": sum(
            1 for item in item_metrics if item.get("human_correction_case")
        ),
        "avg_latency_ms": round(
            sum(int(item.get("latency_ms") or 0) for item in item_metrics) / total,
            2,
        ),
        "total_tokens": sum(int(item.get("total_tokens") or 0) for item in item_metrics),
        "total_cost_micros": sum(
            int(item.get("estimated_cost_micros") or 0) for item in item_metrics
        ),
        "avg_qualitative_score": (
            round(sum(qualitative_values) / len(qualitative_values), 4)
            if qualitative_values
            else None
        ),
    }
