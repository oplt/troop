from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Literal

SettingType = Literal["bool", "int", "json", "string"]


@dataclass(frozen=True)
class SettingSpec:
    key: str
    value_type: SettingType
    default: Any
    description: str


def _positive_int(value: Any) -> None:
    if int(value) <= 0:
        raise ValueError("must be greater than zero")


def _fraction_0_1(value: Any) -> None:
    num = float(value)
    if num < 0 or num > 1:
        raise ValueError("must be between 0 and 1")


CATALOG: dict[str, SettingSpec] = {
    "feature.hierarchy_builder.enabled": SettingSpec(
        key="feature.hierarchy_builder.enabled",
        value_type="bool",
        default=True,
        description="Toggle hierarchy builder surface availability.",
    ),
    "ui.max_recent_runs": SettingSpec(
        key="ui.max_recent_runs",
        value_type="int",
        default=50,
        description="Maximum number of recent runs shown in admin widgets.",
    ),
    "orchestration.max_parallel_tasks": SettingSpec(
        key="orchestration.max_parallel_tasks",
        value_type="int",
        default=4,
        description="Upper bound for concurrent orchestration tasks per project.",
    ),
    "orchestration.default_run_timeout_seconds": SettingSpec(
        key="orchestration.default_run_timeout_seconds",
        value_type="int",
        default=900,
        description="Default execution timeout in seconds for orchestration runs.",
    ),
    "orchestration.routing.defaults": SettingSpec(
        key="orchestration.routing.defaults",
        value_type="json",
        default={"mode": "capability_based", "fallback": "manager"},
        description="Default routing policy payload applied by orchestration services.",
    ),
    "github.sync.default_poll_minutes": SettingSpec(
        key="github.sync.default_poll_minutes",
        value_type="int",
        default=15,
        description="Default poll cadence (minutes) for background GitHub sync.",
    ),
    "limits.export.max_rows": SettingSpec(
        key="limits.export.max_rows",
        value_type="int",
        default=10000,
        description="Maximum rows allowed in a single export action.",
    ),
    "observability.run_trace_sample_rate": SettingSpec(
        key="observability.run_trace_sample_rate",
        value_type="string",
        default="0.2",
        description="Trace sampling rate override for runtime diagnostics.",
    ),
}


VALIDATORS: dict[str, list] = {
    "ui.max_recent_runs": [_positive_int],
    "orchestration.max_parallel_tasks": [_positive_int],
    "orchestration.default_run_timeout_seconds": [_positive_int],
    "github.sync.default_poll_minutes": [_positive_int],
    "limits.export.max_rows": [_positive_int],
    "observability.run_trace_sample_rate": [_fraction_0_1],
}


def list_catalog() -> list[SettingSpec]:
    return [CATALOG[key] for key in sorted(CATALOG)]


def get_spec(key: str) -> SettingSpec | None:
    return CATALOG.get(key)


def serialize_value(value: Any, value_type: SettingType) -> str:
    if value_type == "bool":
        return "true" if bool(value) else "false"
    if value_type == "int":
        return str(int(value))
    if value_type == "json":
        return json.dumps(value, separators=(",", ":"), sort_keys=True)
    return str(value)


def parse_value(raw: str, value_type: SettingType) -> Any:
    if value_type == "bool":
        normalized = raw.strip().lower()
        if normalized in {"true", "1", "yes", "on"}:
            return True
        if normalized in {"false", "0", "no", "off"}:
            return False
        raise ValueError("boolean value must be true/false")
    if value_type == "int":
        return int(raw.strip())
    if value_type == "json":
        parsed = json.loads(raw.strip() or "{}")
        if not isinstance(parsed, (dict, list)):
            raise ValueError("json value must decode to object or list")
        return parsed
    return raw


def normalize_value_for_key(key: str, raw: str) -> str:
    spec = get_spec(key)
    if spec is None:
        raise ValueError(f"Unknown parameter key: {key}")
    parsed = parse_value(raw, spec.value_type)
    for validator in VALIDATORS.get(key, []):
        validator(parsed)
    return serialize_value(parsed, spec.value_type)
