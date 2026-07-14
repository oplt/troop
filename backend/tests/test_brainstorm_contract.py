from backend.modules.orchestration.services.brainstorm_service import OrchestrationBrainstormServiceMixin


def test_brainstorm_guardrails_normalize_modes_outputs_and_thresholds() -> None:
    service = OrchestrationBrainstormServiceMixin()

    guardrails = service._normalize_brainstorm_stop_conditions(
        {
            "mode": "root cause analysis",
            "output_type": "issue reply",
            "max_cost_usd": 25,
            "max_repetition_score": 0.8,
            "stop_conditions": {
                "soft_consensus_min_similarity": 0.75,
                "conflict_pairwise_max_similarity": 0.3,
                "conflict_requires_moderation": False,
            },
        }
    )

    assert guardrails["mode"] == "root_cause"
    assert guardrails["output_type"] == "issue_reply_draft"
    assert guardrails["max_cost_usd"] == 25.0
    assert guardrails["max_repetition_score"] == 0.8
    assert guardrails["soft_consensus_min_similarity"] == 0.75
    assert guardrails["conflict_pairwise_max_similarity"] == 0.3
    assert guardrails["conflict_requires_moderation"] is False


def test_brainstorm_metrics_detect_conflicting_positions_and_repetition() -> None:
    service = OrchestrationBrainstormServiceMixin()

    metrics = service._brainstorm_consensus_metrics_from_contents(
        [
            "Choose a queue-backed worker for reliable retries.",
            "Choose a synchronous request path for lower latency.",
            "Keep the request path simple and avoid background workers.",
        ],
        soft_thr=0.72,
        conflict_thr=0.38,
    )

    assert metrics["conflict_signal"] is True
    assert metrics["consensus_kind"] == "none"
    assert metrics["pairwise_min_similarity"] is not None
