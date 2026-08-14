"""Shared policy rules for human-in-the-loop execution controls."""

from __future__ import annotations

from typing import Any

VALID_AUTONOMY_LEVELS = frozenset(
    {"autonomous", "semi-autonomous", "semi_autonomous", "assisted", "supervised"}
)
AUTONOMY_LEVEL_ALIASES = {
    "semi_autonomous": "semi-autonomous",
    "supervised": "semi-autonomous",
}
VALID_SECRET_SCOPES = frozenset({"project_default", "repo_scoped", "agent_scoped", "deny_external"})
VALID_SANDBOX_MODES = frozenset({"allow_host_fallback", "docker_required"})

DEFAULT_APPROVAL_GATES = (
    "post_to_github",
    "open_pr",
    "mark_complete",
    "change_task_ownership",
    "write_memory",
    "use_expensive_model",
    "run_tool",
)

# These actions can mutate external systems, shared state, ownership, or spend. They are
# protected even when a project enables autonomous handling of low-risk work.
MANDATORY_APPROVAL_GATES = frozenset(DEFAULT_APPROVAL_GATES)

_SENSITIVE_PAYLOAD_KEYS = frozenset(
    {
        "access_token",
        "api_key",
        "authorization",
        "cookie",
        "encrypted_token",
        "password",
        "private_key",
        "secret",
        "token",
    }
)


def normalize_approval_gates(value: Any) -> list[str]:
    requested = value if isinstance(value, (list, tuple, set)) else DEFAULT_APPROVAL_GATES
    selected = {
        str(item).strip() for item in requested if str(item).strip() in MANDATORY_APPROVAL_GATES
    }
    return [
        gate
        for gate in DEFAULT_APPROVAL_GATES
        if gate in selected or gate in MANDATORY_APPROVAL_GATES
    ]


def normalize_autonomy_level(value: Any) -> str:
    candidate = str(value or "assisted").strip().lower()
    if candidate == "autonomous":
        return "autonomous"
    if candidate in {"semi-autonomous", "semi_autonomous", "supervised"}:
        return AUTONOMY_LEVEL_ALIASES.get(candidate, candidate)
    return "assisted"


def action_requires_approval(execution_settings: dict[str, Any] | None, action_type: str) -> bool:
    settings = dict(execution_settings or {})
    if action_type in MANDATORY_APPROVAL_GATES:
        return True
    if normalize_autonomy_level(settings.get("autonomy_level")) == "autonomous":
        return False
    return action_type in normalize_approval_gates(settings.get("approval_gates"))


def normalize_hitl_settings(raw: dict[str, Any] | None) -> dict[str, Any]:
    settings = dict(raw or {})
    secret_scope = str(settings.get("secret_scope") or "project_default")
    sandbox_mode = str(settings.get("sandbox_mode") or "allow_host_fallback")
    settings["secret_scope"] = (
        secret_scope if secret_scope in VALID_SECRET_SCOPES else "project_default"
    )
    settings["sandbox_mode"] = (
        sandbox_mode if sandbox_mode in VALID_SANDBOX_MODES else "allow_host_fallback"
    )
    settings["sandbox_note"] = str(settings.get("sandbox_note") or "")[:2000]
    approval_sla = dict(settings.get("approval_sla") or {})
    approval_sla.setdefault("enabled", True)
    approval_sla.setdefault("response_hours", 24)
    approval_sla.setdefault("warn_hours_before_due", 4)
    approval_sla.setdefault("escalate_hours_after_due", 0)
    approval_sla.setdefault("escalation_roles", ["admin", "owner"])
    settings["approval_sla"] = approval_sla
    return settings


def redact_approval_payload(value: Any, *, depth: int = 0) -> Any:
    """Return a bounded, non-secret representation for approval UI responses.

    Approval payloads are useful to operators, but tool arguments and integration
    requests can contain credentials. Redaction belongs at the response boundary;
    workers continue to use the original payload stored in the database.
    """
    if depth > 5:
        return "[truncated]"
    if isinstance(value, dict):
        output: dict[str, Any] = {}
        for key, item in value.items():
            normalized_key = str(key).lower().replace("-", "_")
            if normalized_key in _SENSITIVE_PAYLOAD_KEYS or any(
                marker in normalized_key for marker in ("secret", "token", "password", "credential")
            ):
                output[str(key)] = "[redacted]"
            else:
                output[str(key)] = redact_approval_payload(item, depth=depth + 1)
        return output
    if isinstance(value, (list, tuple)):
        return [redact_approval_payload(item, depth=depth + 1) for item in list(value)[:50]]
    if isinstance(value, str):
        return value if len(value) <= 4000 else value[:4000] + "…"
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:4000]
