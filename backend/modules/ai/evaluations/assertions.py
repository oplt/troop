"""Deterministic evaluation assertions (EVAL-001A)."""

from __future__ import annotations

from typing import Any


def _path_get(value: Any, path: str) -> Any:
    current = value
    for part in str(path or "").split("."):
        if not part:
            continue
        if not isinstance(current, dict):
            return None
        current = current.get(part)
    return current


def normalize_assertions(raw: Any) -> dict[str, Any] | None:
    if raw is None:
        return None
    if not isinstance(raw, dict):
        return None
    rules = raw.get("rules")
    if not isinstance(rules, list) or not rules:
        return None
    cleaned: list[dict[str, Any]] = []
    for rule in rules:
        if not isinstance(rule, dict):
            continue
        rule_type = str(rule.get("type") or "").strip()
        if not rule_type:
            continue
        cleaned.append(dict(rule))
    if not cleaned:
        return None
    return {
        "mode": str(raw.get("mode") or "deterministic"),
        "rules": cleaned,
    }


def derive_assertions_from_expected(expected_output_json: dict[str, Any]) -> dict[str, Any]:
    return {
        "mode": "deterministic",
        "rules": [{"type": "json_equals", "value": expected_output_json}],
    }


def evaluate_assertions(
    *,
    output_text: str | None,
    output_json: dict | None,
    assertions: dict[str, Any] | None,
) -> tuple[float, bool, str]:
    normalized = normalize_assertions(assertions)
    if normalized is None:
        return 0.0, False, "No deterministic assertions defined"

    failures: list[str] = []
    for index, rule in enumerate(normalized["rules"], start=1):
        rule_type = str(rule.get("type") or "")
        if rule_type == "json_equals":
            expected = rule.get("value")
            passed = output_json == expected
            if not passed:
                failures.append(f"rule {index}: json_equals mismatch")
        elif rule_type == "json_path_equals":
            actual = _path_get(output_json, str(rule.get("path") or ""))
            if actual != rule.get("value"):
                failures.append(f"rule {index}: json_path_equals {rule.get('path')!r}")
        elif rule_type == "json_path_contains":
            actual = _path_get(output_json, str(rule.get("path") or ""))
            needle = str(rule.get("value") or "")
            if isinstance(actual, str):
                if needle.lower() not in actual.lower():
                    failures.append(f"rule {index}: json_path_contains {rule.get('path')!r}")
            elif isinstance(actual, list):
                if needle not in [str(item) for item in actual]:
                    failures.append(f"rule {index}: json_path_contains list {rule.get('path')!r}")
            else:
                failures.append(f"rule {index}: json_path_contains unsupported type")
        elif rule_type == "text_equals":
            expected = str(rule.get("value") or "").strip()
            actual = (output_text or "").strip()
            if expected.lower() != actual.lower():
                failures.append(f"rule {index}: text_equals mismatch")
        elif rule_type == "text_contains":
            needle = str(rule.get("value") or "").strip().lower()
            actual = (output_text or "").strip().lower()
            if needle not in actual:
                failures.append(f"rule {index}: text_contains missing substring")
        else:
            failures.append(f"rule {index}: unsupported type {rule_type!r}")

    if failures:
        return 0.0, False, "; ".join(failures)
    return 1.0, True, f"All {len(normalized['rules'])} deterministic assertions passed"
