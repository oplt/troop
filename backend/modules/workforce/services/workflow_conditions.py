"""Deterministic workflow condition evaluation — no Python eval."""

from __future__ import annotations

from typing import Any


def resolve_value(expr: Any, vars_: dict[str, Any]) -> Any:
    """Resolve a literal or ``{"var": "path.to.key"}`` reference."""
    if isinstance(expr, dict) and "var" in expr:
        path = str(expr["var"])
        cur: Any = vars_
        for part in path.split("."):
            if not isinstance(cur, dict):
                return None
            cur = cur.get(part)
        return cur
    return expr


def evaluate_condition(condition: dict[str, Any] | None, vars_: dict[str, Any]) -> bool:
    """Evaluate a constrained condition object against workflow vars."""
    if not condition or not isinstance(condition, dict):
        return False

    operator = str(condition.get("operator") or "").strip().lower()
    if not operator:
        return False

    left = resolve_value(condition.get("left"), vars_)
    right = resolve_value(condition.get("right"), vars_)

    if operator == "truthy":
        return bool(left)
    if operator == "falsy":
        return not bool(left)
    if operator == "eq":
        return left == right
    if operator == "neq":
        return left != right
    if operator == "gt":
        return left is not None and right is not None and left > right
    if operator == "gte":
        return left is not None and right is not None and left >= right
    if operator == "lt":
        return left is not None and right is not None and left < right
    if operator == "lte":
        return left is not None and right is not None and left <= right
    if operator == "in":
        if isinstance(right, (list, tuple, set, frozenset)):
            return left in right
        return False
    return False


def condition_from_config(config: dict[str, Any]) -> dict[str, Any] | None:
    """Extract a condition object from node config."""
    if not isinstance(config, dict):
        return None
    if isinstance(config.get("condition"), dict):
        return dict(config["condition"])
    if config.get("operator"):
        return dict(config)
    return None
