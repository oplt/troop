import unittest
import hmac
import hashlib
import asyncio
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi import HTTPException

from backend.modules.orchestration.markdown import parse_agent_markdown
from backend.modules.orchestration.providers import ProviderExecutionResult
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret
from backend.modules.orchestration.service import OrchestrationService, _chunk_text, _cosine_similarity
from backend.modules.orchestration.tools import OrchestrationToolbox

VALID_AGENT_MARKDOWN = """---
name: Backend Engineer
role: specialist
version: 1
parent_template: backend-specialist
model: gpt-4.1-mini
fallback_model: gpt-4.1
capabilities:
  - coding
tools:
  - github
skills:
  - backend-refactor
tags:
  - api
budget:
  token_budget: 50000
  time_budget_seconds: 600
  retry_budget: 2
memory_policy: project-only
permissions: code-write
task_filters:
  - backend
  - ^bug:
output_schema: patch_proposal
escalation_path: tech-lead
---
# Mission
Build and improve backend APIs.

# Rules
Be precise and explain tradeoffs briefly.

# Output Contract
Return a concise implementation summary.
"""


class AgentMarkdownTests(unittest.TestCase):
    def test_parse_valid_agent_markdown(self) -> None:
        normalized, errors = parse_agent_markdown(VALID_AGENT_MARKDOWN)
        self.assertEqual(errors, [])
        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["slug"], "backend-engineer")
        self.assertEqual(normalized["capabilities"], ["coding"])
        self.assertEqual(normalized["allowed_tools"], ["github"])
        self.assertEqual(normalized["skills"], ["backend-refactor"])
        self.assertEqual(normalized["parent_template_slug"], "backend-specialist")
        self.assertEqual(normalized["memory_policy"]["scope"], "project-only")
        self.assertEqual(normalized["model_policy"]["fallback_model"], "gpt-4.1")
        self.assertEqual(normalized["model_policy"]["permissions"], "code-write")
        self.assertEqual(normalized["output_schema"]["format"], "patch_proposal")

    def test_parse_invalid_agent_markdown_requires_sections(self) -> None:
        normalized, errors = parse_agent_markdown("---\nname: Incomplete\n---\n# Mission\nx\n")
        self.assertIsNone(normalized)
        self.assertTrue(any("Rules" in error for error in errors))
        self.assertTrue(any("Output Contract" in error for error in errors))


class SecretHandlingTests(unittest.TestCase):
    def test_encrypt_and_decrypt_secret(self) -> None:
        encrypted = encrypt_secret("secret-token")
        self.assertNotEqual(encrypted, "secret-token")
        self.assertEqual(decrypt_secret(encrypted), "secret-token")


class HierarchyTests(unittest.TestCase):
    def test_direct_report_is_allowed(self) -> None:
        service = object.__new__(OrchestrationService)
        manager = SimpleNamespace(id="manager", parent_agent_id=None)
        worker = SimpleNamespace(id="worker", parent_agent_id="manager")
        self.assertTrue(service._is_agent_descendant(manager, worker))

    def test_unrelated_agent_is_not_allowed(self) -> None:
        service = object.__new__(OrchestrationService)
        manager = SimpleNamespace(id="manager", parent_agent_id=None)
        worker = SimpleNamespace(id="worker", parent_agent_id="someone-else")
        self.assertFalse(service._is_agent_descendant(manager, worker))


class TaskStateMachineTests(unittest.TestCase):
    def test_valid_transition_updates_task_status(self) -> None:
        service = object.__new__(OrchestrationService)
        task = SimpleNamespace(status="queued", updated_at=None, id="task-1")
        import asyncio

        asyncio.run(service._transition_task_status(task, "planned"))
        self.assertEqual(task.status, "planned")

    def test_invalid_transition_raises_http_error(self) -> None:
        service = object.__new__(OrchestrationService)
        task = SimpleNamespace(status="backlog", updated_at=None, id="task-1")
        import asyncio

        with self.assertRaises(HTTPException):
            asyncio.run(service._transition_task_status(task, "completed"))


class RoutingTests(unittest.TestCase):
    def test_capability_based_subtask_assignment_prefers_matching_agent(self) -> None:
        service = object.__new__(OrchestrationService)
        service.repo = SimpleNamespace(
            count_active_runs_by_worker=lambda project_id, agent_ids: __import__("asyncio").sleep(0, result={"a1": 2, "a2": 0})
        )
        backend_agent = SimpleNamespace(id="a1", name="Backend", capabilities_json=["coding", "api_design"])
        review_agent = SimpleNamespace(id="a2", name="Reviewer", capabilities_json=["review", "security"])
        import asyncio

        routed = asyncio.run(service._route_sub_tasks_to_agents(
            "project-1",
            [
                {
                    "title": "Implement API",
                    "required_tools": ["coding"],
                    "required_capabilities": ["api_design"],
                    "parallelizable": True,
                }
            ],
            [backend_agent, review_agent],
        ))
        self.assertEqual(routed[0]["assigned_agent_id"], "a1")

    def test_review_payload_falls_back_to_rework_when_not_approved(self) -> None:
        service = object.__new__(OrchestrationService)
        payload = service._coerce_review_payload("This needs rework before approval.")
        self.assertEqual(payload["decision"], "rework")

    def test_normalize_policy_routing_includes_defaults(self) -> None:
        service = object.__new__(OrchestrationService)
        policy = service._normalize_policy_routing({"cheap_model_slug": "gpt-4.1-mini"})
        self.assertEqual(policy["cheap_model_slug"], "gpt-4.1-mini")
        self.assertIn("rules", policy)

    def test_matches_policy_rule_contains(self) -> None:
        service = object.__new__(OrchestrationService)
        self.assertTrue(service._matches_policy_rule(["triage", "bug"], "contains", "triage"))
        self.assertFalse(service._matches_policy_rule(["bug"], "contains", "triage"))


class BrainstormHelperTests(unittest.TestCase):
    def test_brainstorm_stop_conditions_are_normalized(self) -> None:
        service = object.__new__(OrchestrationService)
        payload = service._normalize_brainstorm_stop_conditions(
            {"mode": "root_cause", "output_type": "risk_register", "max_cost_usd": 5}
        )
        self.assertEqual(payload["mode"], "root_cause")
        self.assertEqual(payload["output_type"], "risk_register")
        self.assertEqual(payload["max_cost_usd"], 5.0)
        self.assertIn("max_repetition_score", payload)

    def test_message_similarity_detects_loops(self) -> None:
        service = object.__new__(OrchestrationService)
        high = service._message_similarity(
            "Investigate database lock contention and rollback storms.",
            "Investigate database contention, lock storms, and rollbacks.",
        )
        low = service._message_similarity(
            "Propose a backend migration plan.",
            "Review the incident timeline and restore service.",
        )
        self.assertGreater(high, low)
        self.assertGreater(high, 0.3)


class GithubHelperTests(unittest.TestCase):
    def test_branch_name_uses_project_template(self) -> None:
        service = object.__new__(OrchestrationService)
        project = SimpleNamespace(settings_json={"github": {"branch_prefix": "troop/{task_id}-{slug}"}})
        task = SimpleNamespace(id="task-123", title="Fix flaky webhook sync")
        branch = service._github_branch_name_for_task(project, task)
        self.assertEqual(branch, "troop/task-123-fix-flaky-webhook-sync")

    def test_webhook_signature_validation(self) -> None:
        from backend.core.config import settings

        service = object.__new__(OrchestrationService)
        body = b'{"action":"opened"}'
        previous = settings.GITHUB_APP_WEBHOOK_SECRET
        settings.GITHUB_APP_WEBHOOK_SECRET = previous or "test-webhook-secret"
        signature = "sha256=" + hmac.new(
            settings.GITHUB_APP_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        try:
            self.assertTrue(service.validate_github_webhook_signature(body, signature))
        finally:
            settings.GITHUB_APP_WEBHOOK_SECRET = previous


class ProviderHelperTests(unittest.TestCase):
    def test_estimate_cost_prefers_model_capability_matrix(self) -> None:
        service = object.__new__(OrchestrationService)
        service._cached_model_capabilities = [
            SimpleNamespace(
                model_slug="gpt-4.1-mini",
                provider_type="openai",
                cost_per_1k_input=0.5,
                cost_per_1k_output=1.5,
            )
        ]
        provider = SimpleNamespace(provider_type="openai", metadata_json={})
        micros = service._estimate_cost_micros(provider, 1000, 1000, model_name="gpt-4.1-mini")
        self.assertEqual(micros, 2_000_000)

    def test_execute_with_routing_skips_unhealthy_primary_and_uses_fallback(self) -> None:
        service = object.__new__(OrchestrationService)
        service.repo = SimpleNamespace(
            list_model_capabilities=lambda provider_type=None, active_only=True: asyncio.sleep(
                0,
                result=[
                    SimpleNamespace(model_slug="primary", provider_type="openai"),
                    SimpleNamespace(model_slug="fallback", provider_type="openai"),
                ],
            )
        )
        service.db = SimpleNamespace(get=lambda *args, **kwargs: asyncio.sleep(0, result=None))
        service._emit_run_event = lambda *args, **kwargs: asyncio.sleep(0)
        service._apply_result_metrics = lambda *args, **kwargs: asyncio.sleep(0)
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider_type="openai",
            default_model="primary",
            fallback_model="fallback",
            is_healthy=False,
            metadata_json={},
        )
        agent = SimpleNamespace(model_policy_json={"model": "primary", "fallback_model": "fallback"})
        run = SimpleNamespace(
            task_id=None,
            project_id="project-1",
            input_payload_json={},
            model_name=None,
            provider_config_id=None,
        )
        import backend.modules.orchestration.service as service_module

        previous = service_module.execute_prompt
        service_module.execute_prompt = lambda provider, **kwargs: asyncio.sleep(
            0,
            result=ProviderExecutionResult(
                model_name=kwargs.get("model_name") or "fallback",
                output_text="ok",
                output_json=None,
                input_tokens=10,
                output_tokens=5,
                latency_ms=12,
            ),
        )
        try:
            _, result = asyncio.run(
                service._execute_with_routing(
                    run,
                    provider=provider,
                    agent=agent,
                    system_prompt="system",
                    user_prompt="prompt",
                    append_metrics=False,
                    purpose="unit test",
                )
            )
        finally:
            service_module.execute_prompt = previous
        self.assertEqual(result.model_name, "fallback")
        self.assertEqual(run.model_name, "fallback")


class MemoryHelperTests(unittest.TestCase):
    def test_chunk_text_splits_large_input(self) -> None:
        chunks = _chunk_text("a" * 2500, chunk_size=1000, overlap=100)
        self.assertGreaterEqual(len(chunks), 3)
        self.assertLessEqual(max(len(chunk) for chunk in chunks), 1000)

    def test_cosine_similarity_is_high_for_matching_vectors(self) -> None:
        score = _cosine_similarity([1.0, 0.0, 0.0], [0.9, 0.1, 0.0])
        self.assertGreater(score, 0.9)

    def test_merge_memory_settings_preserves_unknown_keys_and_overrides(self) -> None:
        from backend.modules.orchestration.memory_settings import DEFAULT_MEMORY_SETTINGS, merge_memory_settings

        merged = merge_memory_settings({"memory": {"second_stage_rag": True, "episodic_retrieval_depth": 12}})
        self.assertTrue(merged["second_stage_rag"])
        self.assertEqual(merged["episodic_retrieval_depth"], 12)
        self.assertEqual(merged["auto_promote_decisions"], DEFAULT_MEMORY_SETTINGS["auto_promote_decisions"])


class ToolboxTests(unittest.TestCase):
    def test_filesystem_read_write_is_scoped_to_project_root(self) -> None:
        with TemporaryDirectory() as tmpdir:
            toolbox = OrchestrationToolbox(
                db=None,
                repo=None,
                project=SimpleNamespace(settings_json={"workspace_root": tmpdir}),
                task=None,
                run=SimpleNamespace(id="run-1", task_id=None),
            )
            import asyncio

            write_result = asyncio.run(
                toolbox.execute(
                    {
                        "tool": "fs_write",
                        "arguments": {"path": "notes/output.txt", "content": "hello world"},
                    }
                )
            )
            self.assertEqual(write_result["bytes_written"], len("hello world".encode("utf-8")))
            self.assertTrue(Path(write_result["absolute_path"]).exists())

            read_result = asyncio.run(
                toolbox.execute({"tool": "fs_read", "arguments": {"path": "notes/output.txt"}})
            )
            self.assertEqual(read_result["content"], "hello world")


class HierarchyPolicyTests(unittest.TestCase):
    def test_delegation_whitelist_requires_slug_or_id(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        mgr = SimpleNamespace(
            id="m1",
            slug="mgr",
            parent_agent_id=None,
            model_policy_json={"delegation_rules": {"allowed_delegate_to": ["only-a"]}},
        )
        ok = SimpleNamespace(id="w1", slug="only-a", parent_agent_id="m1", model_policy_json={})
        bad = SimpleNamespace(id="w2", slug="other", parent_agent_id="m1", model_policy_json={})
        self.assertTrue(svc._delegation_edge_allowed(mgr, ok))
        self.assertFalse(svc._delegation_edge_allowed(mgr, bad))

    def test_brainstorm_rules_symmetric(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        a = SimpleNamespace(
            id="a",
            slug="alice",
            model_policy_json={"delegation_rules": {"allowed_brainstorm_with": ["bob"]}},
        )
        b = SimpleNamespace(
            id="b",
            slug="bob",
            model_policy_json={"delegation_rules": {"allowed_brainstorm_with": ["alice"]}},
        )
        self.assertTrue(svc._brainstorm_pair_allowed(a, b))
        b_one_way = SimpleNamespace(
            id="b",
            slug="bob",
            model_policy_json={"delegation_rules": {"allowed_brainstorm_with": ["carl"]}},
        )
        self.assertFalse(svc._brainstorm_pair_allowed(a, b_one_way))


class SlaDeadlineTests(unittest.TestCase):
    def test_effective_deadline_is_earlier_of_due_date_and_response_sla(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        base = datetime(2026, 1, 1, 12, 0, tzinfo=UTC)
        task = SimpleNamespace(
            due_date=base + timedelta(days=2),
            response_sla_hours=12,
            created_at=base,
        )
        deadline = svc._task_effective_sla_deadline(task)
        self.assertEqual(deadline, base + timedelta(hours=12))


class BrainstormConsensusMetricsTests(unittest.TestCase):
    def test_soft_consensus_match_on_similar_positions(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        base = "recommendation ship postgres read replicas for production datastore"
        texts = [base, f"{base} confirmed", f"yes {base}"]
        metrics = svc._brainstorm_consensus_metrics_from_contents(texts, soft_thr=0.72, conflict_thr=0.38)
        self.assertTrue(metrics["soft_consensus_match"])
        self.assertEqual(metrics["consensus_kind"], "soft")

    def test_hard_consensus_when_identical_excerpt(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        line = "ship the dark-mode toggle behind a feature flag this week"
        metrics = svc._brainstorm_consensus_metrics_from_contents([line, line], soft_thr=0.72, conflict_thr=0.38)
        self.assertEqual(metrics["consensus_kind"], "hard")

    def test_conflict_signal_on_divergent_positions(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        texts = [
            "baking apple pies for the fundraiser",
            "quantum chromodynamics on curved spacetime",
            "motorcycle chain tension maintenance checklist",
        ]
        metrics = svc._brainstorm_consensus_metrics_from_contents(texts, soft_thr=0.72, conflict_thr=0.38)
        self.assertTrue(metrics.get("conflict_signal"))


class WorkingMemoryHelpersTests(unittest.TestCase):
    def test_merge_working_memory_respects_limits(self) -> None:
        from backend.modules.orchestration.working_memory import merge_working_memory_patch

        base = merge_working_memory_patch(
            None,
            {"objective": "x" * 50, "artifact_refs": ["a", "b"]},
        )
        self.assertIn("objective", base)
        merged = merge_working_memory_patch(base, {"temp_notes": "hello"})
        self.assertEqual(merged["temp_notes"], "hello")

    def test_procedural_snippets_truncates(self) -> None:
        from backend.modules.orchestration.procedural_context import build_procedural_snippets

        agent = SimpleNamespace(
            mission_markdown="m" * 2000,
            rules_markdown="r" * 2000,
            output_contract_markdown="c" * 2000,
        )
        task = SimpleNamespace(task_type="bug", labels_json=["api"])
        out = build_procedural_snippets(agent, task, max_chars=400)
        self.assertLessEqual(len(out), 400)


class ExecutionStateHelpersTests(unittest.TestCase):
    def test_checkpoint_excerpt_truncates_and_selects_keys(self) -> None:
        from backend.modules.orchestration.execution_state import checkpoint_excerpt

        long = "x" * 600
        out = checkpoint_excerpt(
            {"next_step": "go", "noise": 1, "scratchpad": long},
            max_str=100,
        )
        self.assertEqual(out["next_step"], "go")
        self.assertNotIn("noise", out)
        self.assertTrue(str(out["scratchpad"]).endswith("…"))
        self.assertEqual(len(out["scratchpad"]), 101)

    def test_extract_execution_metadata_views(self) -> None:
        from backend.modules.orchestration.execution_state import extract_execution_metadata_views

        views = extract_execution_metadata_views(
            {
                "suggested_handoff": "do x",
                "sla_deadline": "soon",
                "other": 1,
                "execution_memory": {"last_run_id": "r1", "since_last_run_unified_diff": "a"},
            }
        )
        self.assertIn("suggested_handoff", views["handoff_and_sla_hints"])
        self.assertIn("other", views["other_metadata_keys"])
        assert views["execution_memory_ref"] is not None
        self.assertEqual(views["execution_memory_ref"]["last_run_id"], "r1")
        self.assertTrue(views["execution_memory_ref"]["has_diff"])


if __name__ == "__main__":
    unittest.main()
