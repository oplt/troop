from __future__ import annotations

from backend.modules.orchestration.hitl_policy import (
    MANDATORY_APPROVAL_GATES,
    action_requires_approval,
    normalize_approval_gates,
    normalize_autonomy_level,
    normalize_hitl_settings,
    redact_approval_payload,
)


def test_protected_actions_remain_gated_in_autonomous_mode():
    execution = {"autonomy_level": "autonomous", "approval_gates": []}
    assert action_requires_approval(execution, "open_pr")
    assert action_requires_approval(execution, "run_tool")
    assert not action_requires_approval(execution, "read_project")


def test_operating_modes_use_three_canonical_values():
    assert normalize_autonomy_level("semi_autonomous") == "semi-autonomous"
    assert normalize_autonomy_level("supervised") == "semi-autonomous"
    assert normalize_autonomy_level("unknown") == "assisted"


def test_gate_normalization_cannot_remove_protected_actions():
    gates = normalize_approval_gates([])

    assert set(gates) == MANDATORY_APPROVAL_GATES


def test_hitl_settings_reject_unknown_security_modes():
    settings = normalize_hitl_settings({"sandbox_mode": "unsafe", "secret_scope": "all_secrets"})

    assert settings["sandbox_mode"] == "allow_host_fallback"
    assert settings["secret_scope"] == "project_default"


def test_approval_payload_redacts_nested_credentials_and_bounds_text():
    payload = redact_approval_payload(
        {
            "tool": "github_comment",
            "arguments": {"token": "do-not-show", "body": "x" * 5000},
        }
    )

    assert payload["arguments"]["token"] == "[redacted]"
    assert len(payload["arguments"]["body"]) == 4001
