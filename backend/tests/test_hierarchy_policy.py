from backend.modules.orchestration.hierarchy_policy import (
    apply_policy_to_execution,
    policy_from_execution,
    validate_hierarchy_policy,
)


def test_policy_migrates_legacy_execution_and_graph_layout():
    execution = {
        "manager_agent_id": "manager",
        "reviewer_agent_ids": ["reviewer"],
        "routing_mode": "cost_aware",
        "team_graph_layout": {
            "edges": [
                {"source": "manager", "target": "specialist", "data": {"semantic": "delegates_to"}},
                {"source": "specialist", "target": "reviewer", "data": {"semantic": "collaborates_with"}},
            ]
        },
    }

    policy = policy_from_execution(execution)

    assert policy["manager_agent_id"] == "manager"
    assert policy["routing_mode"] == "cost_aware"
    assert {edge["relationship"] for edge in policy["edges"]} == {"delegates_to", "collaborates_with"}


def test_policy_rejects_invalid_membership_and_delegation_cycles():
    policy = {
        "manager_agent_id": "manager",
        "edges": [
            {"source_agent_id": "manager", "target_agent_id": "lead", "relationship": "delegates_to"},
            {"source_agent_id": "lead", "target_agent_id": "manager", "relationship": "delegates_to"},
        ],
        "reviewer_agent_ids": ["missing"],
        "blocked_handoff": {"target_agent_id": "missing"},
    }

    errors = validate_hierarchy_policy(
        policy,
        {"manager", "lead"},
        {"manager": "manager", "lead": "team_lead"},
    )

    assert any("cycle" in error for error in errors)
    assert any("reviewer_agent_ids" in error for error in errors)
    assert any("blocked handoff" in error for error in errors)


def test_apply_policy_keeps_runtime_compatibility_fields_in_sync():
    execution = apply_policy_to_execution(
        {},
        {
            "manager_agent_id": "manager",
            "reviewer_agent_ids": ["reviewer"],
            "routing_mode": "model_availability",
            "default_execution_mode": "debate",
            "blocked_handoff": {"mode": "configured_agent", "target_agent_id": "lead"},
        },
    )

    assert execution["manager_agent_id"] == "manager"
    assert execution["reviewer_agent_ids"] == ["reviewer"]
    assert execution["routing_mode"] == "model_availability"
    assert execution["default_run_mode"] == "debate"
    assert execution["blocked_handoff"]["target_agent_id"] == "lead"


def test_policy_requires_a_reviewer_role_and_reviewer_chain():
    errors = validate_hierarchy_policy(
        {"manager_agent_id": "manager", "reviewer_agent_ids": []},
        {"manager", "worker"},
        {"manager": "manager", "worker": "specialist"},
    )

    assert "Project must include at least one reviewer role" in errors
    assert "At least one reviewer agent must be configured in the reviewer chain" in errors


def test_policy_accepts_project_membership_reviewer_role():
    errors = validate_hierarchy_policy(
        {"manager_agent_id": "manager", "reviewer_agent_ids": ["reviewer"]},
        {"manager", "reviewer"},
        {"manager": "manager", "reviewer": "reviewer"},
    )

    assert errors == []
