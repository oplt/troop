import unittest
import hmac
import hashlib
import asyncio
from unittest.mock import patch
from datetime import UTC, datetime, timedelta
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace

from fastapi import HTTPException

from backend.modules.orchestration.execution_workflow import (
    consume_signal_queue,
    enqueue_signal,
    ensure_workflow_state,
    mark_step,
    update_query_snapshot,
    workflow_state,
)
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

    def test_parse_contract_section_json_overrides_frontmatter(self) -> None:
        markdown = """---
name: Contract Carrier
role: specialist
---
# Mission
Implement backend fixes.

# Rules
Keep the patch small.

# Output Contract
Return a patch summary.

# Contract
```json
{
  "identity": {
    "slug": "contract-carried",
    "description": "Uses a JSON contract block"
  },
  "allowed_tools": ["fs_read", "fs_write"],
  "model_policy": {
    "model": "gpt-4.1-mini",
    "permissions": "code-write",
    "escalation_path": "qa-reviewer"
  },
  "memory_policy": {
    "scope": "project-only"
  },
  "output_schema": {
    "format": "patch_proposal"
  }
}
```
"""
        normalized, errors = parse_agent_markdown(markdown)
        self.assertEqual(errors, [])
        self.assertIsNotNone(normalized)
        assert normalized is not None
        self.assertEqual(normalized["slug"], "contract-carried")
        self.assertEqual(normalized["allowed_tools"], ["fs_read", "fs_write"])
        self.assertEqual(normalized["model_policy"]["model"], "gpt-4.1-mini")
        self.assertEqual(normalized["model_policy"]["permissions"], "code-write")
        self.assertEqual(normalized["memory_policy"]["scope"], "project-only")
        self.assertEqual(normalized["output_schema"]["format"], "patch_proposal")


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

    def test_acceptance_criteria_items_are_extracted_from_markdown(self) -> None:
        service = object.__new__(OrchestrationService)
        items = service._acceptance_criteria_items(
            """
            - add API endpoint
            - return tests

            Final summary paragraph
            """
        )
        self.assertEqual(items, ["add API endpoint", "return tests", "Final summary paragraph"])

    def test_acceptance_check_uses_acceptance_criteria_not_description(self) -> None:
        service = object.__new__(OrchestrationService)
        task = SimpleNamespace(
            id="task-1",
            acceptance_criteria="- expose webhook endpoint\n- add regression test",
            description="short",
            result_payload_json={"summary": "Expose webhook endpoint with regression test coverage"},
            result_summary="Expose webhook endpoint with regression test coverage",
            status="completed",
        )
        service.repo = SimpleNamespace(list_task_dependencies_for_task=lambda task_id: asyncio.sleep(0, result=[]))
        service.get_task = lambda user, project_id, task_id: asyncio.sleep(0, result=task)
        result = asyncio.run(service.check_task_acceptance(SimpleNamespace(), "project-1", task.id))
        self.assertTrue(result["passed"])
        criteria = next(item for item in result["checks"] if item["name"] == "acceptance_criteria")
        self.assertTrue(criteria["passed"])

    def test_manual_completion_is_blocked_when_acceptance_fails(self) -> None:
        service = object.__new__(OrchestrationService)
        task = SimpleNamespace(
            id="task-1",
            project_id="project-1",
            status="needs_review",
            assigned_agent_id=None,
            reviewer_agent_id=None,
            title="Task",
            description="desc",
            acceptance_criteria="- must add tests",
            result_summary="implemented without tests",
            result_payload_json={"summary": "implemented without tests"},
            metadata_json={},
            updated_at=None,
        )
        service.get_task = lambda user, project_id, task_id: asyncio.sleep(0, result=task)
        service.repo = SimpleNamespace(
            list_task_dependencies_for_task=lambda task_id: asyncio.sleep(0, result=[]),
            get_task_by_id=lambda task_id: asyncio.sleep(0, result=None),
        )
        service.db = SimpleNamespace(commit=lambda: asyncio.sleep(0), refresh=lambda item: asyncio.sleep(0, result=None))
        with self.assertRaises(HTTPException):
            asyncio.run(
                service.update_task(
                    SimpleNamespace(),
                    "project-1",
                    task.id,
                    {"status": "completed"},
                )
            )

    def test_dependency_cycle_is_rejected(self) -> None:
        service = object.__new__(OrchestrationService)
        tasks = [
            SimpleNamespace(id="task-1", dependency_ids=[]),
            SimpleNamespace(id="task-2", dependency_ids=["task-1"]),
        ]
        service.repo = SimpleNamespace(list_tasks=lambda project_id: asyncio.sleep(0, result=tasks))
        with self.assertRaises(HTTPException):
            asyncio.run(service._validate_task_dependencies("project-1", "task-1", ["task-2"]))


class RoutingTests(unittest.TestCase):
    def test_capability_based_subtask_assignment_prefers_matching_agent(self) -> None:
        service = object.__new__(OrchestrationService)
        service.repo = SimpleNamespace(
            count_active_runs_by_worker=lambda project_id, agent_ids: __import__("asyncio").sleep(0, result={"a1": 2, "a2": 0})
        )
        service.db = SimpleNamespace(
            get=lambda model, project_id: __import__("asyncio").sleep(
                0,
                result=SimpleNamespace(settings_json={}),
            )
        )
        backend_agent = SimpleNamespace(
            id="a1",
            name="Backend",
            capabilities_json=["coding", "api_design"],
            allowed_tools_json=["code_execute"],
            provider_config_id=None,
            model_policy_json={},
            parent_agent_id=None,
            slug="backend",
        )
        review_agent = SimpleNamespace(
            id="a2",
            name="Reviewer",
            capabilities_json=["review", "security"],
            allowed_tools_json=["fs_read"],
            provider_config_id=None,
            model_policy_json={},
            parent_agent_id=None,
            slug="reviewer",
        )
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

    def test_routing_explainability_prefers_explicit_meta_fields(self) -> None:
        service = object.__new__(OrchestrationService)
        explainability = service._routing_explainability_from_payload(
            {
                "orchestration_meta": {
                    "agent_selection_reason": "Matched api_design capability.",
                    "model_selection_reason": "Project pinned cheaper model.",
                    "routing_inputs": {"priority": "high"},
                    "routing_policy_snapshot": {"routing_mode": "cost_aware"},
                    "worker_agent_id_source": "auto",
                    "model_source": "project_execution",
                }
            }
        )
        self.assertEqual(explainability["agent_selection_reason"], "Matched api_design capability.")
        self.assertEqual(explainability["model_selection_reason"], "Project pinned cheaper model.")
        self.assertEqual(explainability["routing_inputs"], {"priority": "high"})
        self.assertEqual(explainability["routing_policy_snapshot"], {"routing_mode": "cost_aware"})
        self.assertEqual(explainability["agent_source"], "auto")
        self.assertEqual(explainability["model_source"], "project_execution")


class ReplayFlowTests(unittest.TestCase):
    def test_replay_run_carries_prior_transcript_and_parent_metadata(self) -> None:
        service = object.__new__(OrchestrationService)
        created: dict[str, object] = {}
        old_run = SimpleNamespace(
            id="run-1",
            project_id="project-1",
            task_id="task-1",
            orchestrator_agent_id="mgr-1",
            worker_agent_id="worker-1",
            reviewer_agent_id="rev-1",
            provider_config_id=None,
            brainstorm_id=None,
            run_mode="single_agent",
            status="completed",
            model_name="gpt-5",
            attempt_number=1,
            retry_count=0,
            checkpoint_json={},
            input_payload_json={"orchestration_meta": {"worker_agent_id_source": "auto"}},
        )
        project = SimpleNamespace(id="project-1", owner_id="user-1")
        task = SimpleNamespace(id="task-1", status="planned", updated_at=None)

        async def create_run(**kwargs):
            created.update(kwargs)
            return SimpleNamespace(
                id="run-2",
                task_id=kwargs["task_id"],
                run_mode=kwargs["run_mode"],
                checkpoint_json=kwargs["checkpoint_json"],
                input_payload_json=kwargs["input_payload_json"],
            )

        async def db_get(model, item_id: str):
            if item_id == "project-1":
                return project
            if item_id == "task-1":
                return task
            return None

        service.get_run = lambda user, run_id: asyncio.sleep(0, result=old_run)
        service._enforce_orchestration_run_rate_limit = lambda user_id: asyncio.sleep(0)
        service._enforce_agent_token_budget = lambda **kwargs: asyncio.sleep(0)
        service._enforce_agent_cost_budget = lambda **kwargs: asyncio.sleep(0)
        service._transition_task_status = lambda *args, **kwargs: asyncio.sleep(0)
        service._emit_run_event = lambda *args, **kwargs: asyncio.sleep(0)
        service._workflow_steps_for_run = lambda run: [{"id": "queued"}, {"id": "running"}]
        service.repo = SimpleNamespace(
            list_run_events=lambda run_id: asyncio.sleep(
                0,
                result=[
                    SimpleNamespace(event_type="log", message="step one"),
                    SimpleNamespace(event_type="tool", message="step two"),
                ],
            ),
            create_run=create_run,
        )
        service.db = SimpleNamespace(
            get=db_get,
            commit=lambda: asyncio.sleep(0),
            refresh=lambda item: asyncio.sleep(0),
        )

        with patch("backend.modules.orchestration.durable_execution.submit_orchestration_run") as submit_mock:
            result = asyncio.run(
                service.replay_run(
                    SimpleNamespace(id="user-1"),
                    "run-1",
                    from_event_index=2,
                )
            )

        self.assertEqual(result.id, "run-2")
        replay = created["input_payload_json"]["orchestration_replay"]
        self.assertEqual(replay["parent_run_id"], "run-1")
        self.assertEqual(replay["from_event_index"], 2)
        self.assertIn("[log] step one", replay["prior_transcript"])
        self.assertEqual(
            created["input_payload_json"]["orchestration_meta"]["replayed_from_run_id"],
            "run-1",
        )
        submit_mock.assert_called_once_with("run-2")


class PortfolioPolicyTests(unittest.TestCase):
    def test_update_portfolio_execution_policy_updates_inheriting_projects_only(self) -> None:
        service = object.__new__(OrchestrationService)
        added: list[object] = []
        inheriting_project = SimpleNamespace(
            settings_json={
                "execution": {"routing_mode": "capability_based", "approval_policy": "manager_review", "cost_cap_usd": 250.0},
                "github": {"repo_indexing_cadence": "daily"},
                "portfolio_policy_overrides": {},
            }
        )
        override_project = SimpleNamespace(
            settings_json={
                "execution": {"routing_mode": "throughput", "approval_policy": "manager_review", "cost_cap_usd": 400.0},
                "github": {"repo_indexing_cadence": "weekly"},
                "portfolio_policy_overrides": {"routing_mode": True, "cost_cap_usd": True, "repo_indexing_cadence": True},
            }
        )

        class _Result:
            def scalar_one_or_none(self):
                return None

        service.db = SimpleNamespace(
            execute=lambda stmt: asyncio.sleep(0, result=_Result()),
            add=lambda item: added.append(item),
            commit=lambda: asyncio.sleep(0),
        )
        service.repo = SimpleNamespace(
            list_projects=lambda owner_id: asyncio.sleep(0, result=[inheriting_project, override_project])
        )

        policy = asyncio.run(
            service.update_portfolio_execution_policy(
                SimpleNamespace(id="user-1"),
                {
                    "routing_mode": "cost_aware",
                    "approval_policy": "auto_if_green",
                    "repo_indexing_cadence": "hourly",
                    "cost_cap_usd": 125,
                },
            )
        )

        self.assertEqual(policy["routing_mode"], "cost_aware")
        self.assertEqual(len(added), 1)
        self.assertEqual(inheriting_project.settings_json["execution"]["routing_mode"], "cost_aware")
        self.assertEqual(inheriting_project.settings_json["execution"]["approval_policy"], "auto_if_green")
        self.assertEqual(inheriting_project.settings_json["execution"]["cost_cap_usd"], 125.0)
        self.assertEqual(inheriting_project.settings_json["github"]["repo_indexing_cadence"], "hourly")
        self.assertEqual(override_project.settings_json["execution"]["routing_mode"], "throughput")
        self.assertEqual(override_project.settings_json["execution"]["cost_cap_usd"], 400.0)
        self.assertEqual(override_project.settings_json["github"]["repo_indexing_cadence"], "weekly")

    def test_portfolio_control_plane_reports_operator_dashboard_and_policy_visibility(self) -> None:
        service = object.__new__(OrchestrationService)
        now = datetime.now(UTC)
        project = SimpleNamespace(
            id="project-1",
            name="Alpha",
            slug="alpha",
            settings_json={
                "execution": {"routing_mode": "throughput", "approval_policy": "manager_review", "cost_cap_usd": 250.0},
                "github": {"repo_indexing_cadence": "daily"},
                "portfolio_policy_overrides": {"routing_mode": True},
            },
        )
        service.repo = SimpleNamespace(
            list_projects=lambda owner_id: asyncio.sleep(0, result=[project]),
            list_approvals=lambda owner_id: asyncio.sleep(0, result=[]),
            list_project_memberships=lambda project_id: asyncio.sleep(0, result=[SimpleNamespace(agent_id="mgr-1", is_default_manager=True, role="manager")]),
            list_tasks=lambda project_id: asyncio.sleep(0, result=[SimpleNamespace(id="task-1", title="Blocked task", status="blocked", priority="high", updated_at=now)]),
            list_runs=lambda owner_id, project_id: asyncio.sleep(0, result=[
                SimpleNamespace(id="run-1", status="queued", created_at=now - timedelta(minutes=70), started_at=None, estimated_cost_micros=2000000, token_total=100, task_id="task-1"),
                SimpleNamespace(id="run-2", status="in_progress", created_at=now - timedelta(minutes=80), started_at=now - timedelta(minutes=80), estimated_cost_micros=3000000, token_total=150, task_id="task-1"),
            ]),
            list_project_repositories=lambda project_id: asyncio.sleep(0, result=[SimpleNamespace(id="repo-1")]),
            list_sync_events=lambda owner_id, project_id: asyncio.sleep(0, result=[
                SimpleNamespace(id="sync-1", status="pending", created_at=now - timedelta(minutes=30), action="issue_comment", payload_json={"_webhook_meta": {"replay_history": [{"at": "x"}]}}),
                SimpleNamespace(id="sync-2", status="failed", created_at=now - timedelta(minutes=10), action="replay_webhook", payload_json={"_webhook_meta": {"replay_history": [{"at": "x"}]}}),
            ]),
            list_memory_ingest_jobs_for_project=lambda owner_id, project_id, limit=80: asyncio.sleep(0, result=[
                SimpleNamespace(status="running"),
                SimpleNamespace(status="failed"),
            ]),
            list_providers=lambda owner_id: asyncio.sleep(0, result=[
                SimpleNamespace(is_healthy=True),
                SimpleNamespace(is_healthy=False),
            ]),
        )
        service.db = SimpleNamespace(
            get=lambda model, item_id: asyncio.sleep(0, result=SimpleNamespace(id="mgr-1", name="Manager", slug="manager")),
        )
        service.get_portfolio_execution_policy = lambda user: asyncio.sleep(
            0,
            result={
                "routing_mode": "capability_based",
                "approval_policy": "manager_review",
                "repo_indexing_cadence": "daily",
                "cost_cap_usd": 250.0,
            },
        )

        payload = asyncio.run(service.portfolio_control_plane(SimpleNamespace(id="user-1")))
        project_row = payload["projects"][0]

        self.assertEqual(payload["execution_policy"]["routing_mode"], "capability_based")
        self.assertEqual(payload["operator_dashboard"]["queue_health"]["queued_runs"], 1)
        self.assertEqual(payload["operator_dashboard"]["stuck_runs"]["count"], 1)
        self.assertEqual(project_row["execution_policy"]["override_count"], 1)
        routing_item = next(item for item in project_row["execution_policy"]["items"] if item["key"] == "routing_mode")
        self.assertEqual(routing_item["source"], "project_override")


class SubtaskPlanningTests(unittest.TestCase):
    def test_subtask_blueprint_creates_parallel_and_sequential_steps(self) -> None:
        service = object.__new__(OrchestrationService)
        parent = SimpleNamespace(
            title="Build webhook retries",
            task_type="feature",
            acceptance_criteria="- implement retry logic\n- add tests\n- update docs",
            description="Create resilient retry flow",
            priority="high",
        )
        plan = service._generate_subtask_blueprint(parent, max_subtasks=5, context="payments")
        self.assertGreaterEqual(len(plan), 3)
        self.assertEqual(plan[0]["kind"], "plan")
        self.assertTrue(any(item["kind"] == "implement" for item in plan))
        self.assertTrue(any(item["kind"] == "verify" for item in plan))
        verify = next(item for item in plan if item["kind"] == "verify")
        self.assertTrue(verify["dependency_indexes"])


class AgentLintingTests(unittest.TestCase):
    def test_lint_agent_payload_returns_warnings_for_missing_recommended_fields(self) -> None:
        service = object.__new__(OrchestrationService)

        async def list_skill_packs():
            return []

        async def get_agent_template_by_slug(slug: str):
            return None

        async def get_provider(user_id: str, provider_id: str):
            return None

        async def list_providers(user_id: str, project_id: str | None):
            return []

        service.repo = SimpleNamespace(
            list_skill_packs=list_skill_packs,
            get_agent_template_by_slug=get_agent_template_by_slug,
            get_provider=get_provider,
            list_providers=list_providers,
        )
        service._provider_model_exists = lambda provider, model_name: asyncio.sleep(0, result=True)
        service._model_capability = lambda model_name, provider_type: asyncio.sleep(0, result=None)

        lint = asyncio.run(
            service.lint_agent_payload_detailed(
                SimpleNamespace(id="user-1"),
                {
                    "name": "Sparse Agent",
                    "slug": "sparse-agent",
                    "role": "specialist",
                    "capabilities": [],
                    "allowed_tools": [],
                    "skills": [],
                    "budget": {},
                    "memory_policy": {},
                    "model_policy": {},
                    "output_schema": {},
                    "metadata": {},
                },
            )
        )

        self.assertEqual(lint["errors"], [])
        self.assertIn("Capabilities are empty.", lint["warnings"])
        self.assertIn("Allowed tools are empty.", lint["warnings"])
        self.assertIn("Primary model is not configured.", lint["warnings"])
        self.assertTrue(lint["activation_ready"])

    def test_activation_rejects_agents_with_validation_errors(self) -> None:
        service = object.__new__(OrchestrationService)
        agent = SimpleNamespace(id="agent-1", is_active=False)

        async def get_agent(user, agent_id: str):
            return agent

        service.get_agent = get_agent
        service.summarize_agent_lint = lambda user, item: asyncio.sleep(
            0,
            result={
                "errors": ["Tool 'github' is not available in the orchestration runtime."],
                "warnings": ["Description is missing."],
                "activation_ready": False,
            },
        )
        service.db = SimpleNamespace(
            commit=lambda: asyncio.sleep(0),
            refresh=lambda item: asyncio.sleep(0),
        )

        with self.assertRaises(HTTPException):
            asyncio.run(service.set_agent_active_state(SimpleNamespace(id="user-1"), "agent-1", True))


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

    def test_brainstorm_stop_conditions_normalize_aliases_and_mode_defaults(self) -> None:
        service = object.__new__(OrchestrationService)
        payload = service._normalize_brainstorm_stop_conditions(
            {"mode": "code review debate", "output_type": "architecture decision record"}
        )
        self.assertEqual(payload["mode"], "code_review")
        self.assertEqual(payload["output_type"], "adr")
        defaulted = service._normalize_brainstorm_stop_conditions({"mode": "incident triage"})
        self.assertEqual(defaulted["mode"], "incident_triage")
        self.assertEqual(defaulted["output_type"], "risk_register")

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

    def test_create_brainstorm_deduplicates_participants_and_uses_default_manager(self) -> None:
        service = object.__new__(OrchestrationService)
        created: dict[str, object] = {}

        async def get_project(user, project_id: str):
            return SimpleNamespace(id=project_id, owner_id="user-1", settings_json={})

        async def get_agent(user, agent_id: str):
            return SimpleNamespace(id=agent_id, slug=agent_id, is_active=True, model_policy_json={})

        async def create_brainstorm(**kwargs):
            created["moderator_agent_id"] = kwargs["moderator_agent_id"]
            return SimpleNamespace(
                id="brainstorm-1",
                project_id=kwargs["project_id"],
                task_id=kwargs.get("task_id"),
                initiator_user_id=kwargs["initiator_user_id"],
                moderator_agent_id=kwargs.get("moderator_agent_id"),
                topic=kwargs["topic"],
                max_rounds=kwargs["max_rounds"],
                stop_conditions_json=kwargs["stop_conditions_json"],
                decision_log_json=[],
                summary=None,
                final_recommendation=None,
                status="draft",
                created_at=datetime.now(UTC),
                updated_at=datetime.now(UTC),
            )

        participant_rows: list[tuple[str, int]] = []

        async def create_brainstorm_participant(*, brainstorm_id: str, agent_id: str, order_index: int):
            participant_rows.append((agent_id, order_index))
            return SimpleNamespace(id=f"p-{order_index}", brainstorm_id=brainstorm_id, agent_id=agent_id, order_index=order_index)

        service.get_project = get_project
        service.get_agent = get_agent
        service.get_task = lambda user, project_id, task_id: asyncio.sleep(0, result=SimpleNamespace(id=task_id, project_id=project_id))
        service._project_default_manager = lambda project_id, project=None: asyncio.sleep(0, result=SimpleNamespace(id="manager-1"))
        service._brainstorm_pair_allowed = lambda left, right: True
        service._decorate_brainstorms = lambda items: asyncio.sleep(0, result=None)
        service.repo = SimpleNamespace(
            create_brainstorm=create_brainstorm,
            create_brainstorm_participant=create_brainstorm_participant,
        )
        service.db = SimpleNamespace(commit=lambda: asyncio.sleep(0), refresh=lambda item: asyncio.sleep(0))

        result = asyncio.run(
            service.create_brainstorm(
                SimpleNamespace(id="user-1"),
                {
                    "project_id": "project-1",
                    "task_id": "task-1",
                    "topic": "Review rollout plan",
                    "participant_agent_ids": ["a-1", "a-2", "a-1"],
                },
            )
        )
        self.assertEqual(result.moderator_agent_id, "manager-1")
        self.assertEqual(created["moderator_agent_id"], "manager-1")
        self.assertEqual(participant_rows, [("a-1", 0), ("a-2", 1)])

    def test_create_brainstorm_requires_at_least_two_unique_participants(self) -> None:
        service = object.__new__(OrchestrationService)
        service.get_project = lambda user, project_id: asyncio.sleep(0, result=SimpleNamespace(id=project_id, settings_json={}))
        with self.assertRaises(HTTPException):
            asyncio.run(
                service.create_brainstorm(
                    SimpleNamespace(id="user-1"),
                    {"project_id": "project-1", "topic": "Solo brainstorm", "participant_agent_ids": ["a-1"]},
                )
            )


class GithubHelperTests(unittest.TestCase):
    def test_branch_name_uses_project_template(self) -> None:
        service = object.__new__(OrchestrationService)
        project = SimpleNamespace(settings_json={"github": {"branch_prefix": "troop/{task_id}-{slug}"}})
        task = SimpleNamespace(id="task-123", title="Fix flaky webhook sync")
        branch = service._github_branch_name_for_task(project, task)
        self.assertEqual(branch, "troop/task-123-fix-flaky-webhook-sync")

    def test_branch_name_validation_rejects_non_matching_branch(self) -> None:
        service = object.__new__(OrchestrationService)
        project = SimpleNamespace(settings_json={"github": {"branch_prefix": "troop/{task_id}-{slug}"}})
        task = SimpleNamespace(id="task-123", title="Fix flaky webhook sync")
        self.assertFalse(service._github_branch_name_valid_for_task(project, task, "feature/random"))
        self.assertTrue(
            service._github_branch_name_valid_for_task(
                project, task, "troop/task-123-fix-flaky-webhook-sync"
            )
        )

    def test_repo_pool_config_prefers_repository_full_name(self) -> None:
        service = object.__new__(OrchestrationService)
        project = SimpleNamespace(
            settings_json={
                "github": {
                    "repo_agent_pools": {
                        "org/repo": {"default_assignee_agent_id": "agent-1"},
                    }
                }
            }
        )
        repository = SimpleNamespace(id="repo-1", full_name="org/repo")
        pool = service._repo_pool_config(project, repository=repository)
        self.assertEqual(pool["default_assignee_agent_id"], "agent-1")

    def test_task_state_maps_completed_to_closed_issue(self) -> None:
        service = object.__new__(OrchestrationService)
        self.assertEqual(
            service._task_state_to_github_issue_state(SimpleNamespace(status="completed")),
            "closed",
        )
        self.assertEqual(
            service._task_state_to_github_issue_state(SimpleNamespace(status="planned")),
            "open",
        )

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

    def test_execute_with_routing_prefers_agent_model_over_project_default(self) -> None:
        service = object.__new__(OrchestrationService)
        service.repo = SimpleNamespace(
            list_model_capabilities=lambda provider_type=None, active_only=True: asyncio.sleep(0, result=[]),
            list_providers=lambda owner_id, project_id: asyncio.sleep(0, result=[]),
        )
        project = SimpleNamespace(id="project-1", owner_id="user-1", settings_json={"execution": {"model_name": "project-default"}})
        service.db = SimpleNamespace(
            get=lambda model, entity_id: asyncio.sleep(0, result=project if entity_id == "project-1" else None)
        )
        service._emit_run_event = lambda *args, **kwargs: asyncio.sleep(0)
        service._apply_result_metrics = lambda *args, **kwargs: asyncio.sleep(0)
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider_type="openai",
            default_model="project-default",
            fallback_model=None,
            is_healthy=True,
            metadata_json={},
        )
        agent = SimpleNamespace(model_policy_json={"model": "agent-preferred"})
        run = SimpleNamespace(
            task_id=None,
            project_id="project-1",
            input_payload_json={"orchestration_meta": {"model_source": "project_execution"}},
            model_name="project-default",
            provider_config_id=None,
        )
        import backend.modules.orchestration.service as service_module

        previous = service_module.execute_prompt
        service_module.execute_prompt = lambda provider, **kwargs: asyncio.sleep(
            0,
            result=ProviderExecutionResult(
                model_name=kwargs.get("model_name") or "unknown",
                output_text="ok",
                output_json=None,
                input_tokens=9,
                output_tokens=4,
                latency_ms=10,
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
        self.assertEqual(result.model_name, "agent-preferred")

    def test_execute_with_routing_blocks_disallowed_provider_type(self) -> None:
        service = object.__new__(OrchestrationService)
        service.repo = SimpleNamespace(
            list_model_capabilities=lambda provider_type=None, active_only=True: asyncio.sleep(0, result=[]),
            list_providers=lambda owner_id, project_id: asyncio.sleep(0, result=[]),
        )
        project = SimpleNamespace(
            id="project-1",
            owner_id="user-1",
            settings_json={
                "execution": {
                    "enforce_project_model_policy": True,
                    "allowed_provider_types": ["ollama"],
                }
            },
        )
        service.db = SimpleNamespace(
            get=lambda model, entity_id: asyncio.sleep(0, result=project if entity_id == "project-1" else None)
        )
        service._emit_run_event = lambda *args, **kwargs: asyncio.sleep(0)
        service._apply_result_metrics = lambda *args, **kwargs: asyncio.sleep(0)
        provider = SimpleNamespace(
            id="provider-1",
            name="OpenAI",
            provider_type="openai",
            default_model="gpt-4.1-mini",
            fallback_model=None,
            is_healthy=True,
            metadata_json={},
        )
        run = SimpleNamespace(
            task_id=None,
            project_id="project-1",
            input_payload_json={},
            model_name=None,
            provider_config_id=None,
        )
        with self.assertRaises(HTTPException):
            asyncio.run(
                service._execute_with_routing(
                    run,
                    provider=provider,
                    agent=None,
                    system_prompt="system",
                    user_prompt="prompt",
                    append_metrics=False,
                    purpose="unit test",
                )
            )


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

    def test_project_default_manager_prefers_execution_setting(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        svc.db = SimpleNamespace(
            get=lambda model, agent_id: asyncio.sleep(
                0,
                result=SimpleNamespace(id=agent_id, is_active=True),
            )
        )
        svc.repo = SimpleNamespace(
            list_project_memberships=lambda project_id: asyncio.sleep(
                0,
                result=[
                    SimpleNamespace(
                        id="mem-1",
                        agent_id="manager-from-membership",
                        role="manager",
                        is_default_manager=True,
                    )
                ],
            )
        )
        svc._project_execution_settings = lambda project: {"manager_agent_id": "manager-from-settings"}
        project = SimpleNamespace(id="project-1", settings_json={})
        manager = asyncio.run(svc._project_default_manager(project.id, project=project))
        self.assertEqual(manager.id, "manager-from-settings")

    def test_blocked_handoff_prefers_configured_agent_then_manager_fallback(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        task = SimpleNamespace(
            project_id="project-1",
            metadata_json={},
        )
        worker = SimpleNamespace(
            id="worker-1",
            model_policy_json={"escalation_path": "tech-lead"},
        )
        configured = SimpleNamespace(id="configured-1", slug="ops-manager", is_active=True)
        svc.db = SimpleNamespace(
            get=lambda model, ident: asyncio.sleep(
                0,
                result=SimpleNamespace(id="project-1", owner_id="user-1", settings_json={})
                if ident == "project-1"
                else None,
            )
        )
        svc._load_agent_for_run = lambda agent_id: asyncio.sleep(0, result=worker if agent_id == "worker-1" else None)
        svc.repo = SimpleNamespace(
            get_agent_by_slug=lambda owner_id, slug: asyncio.sleep(0, result=None),
            get_agent=lambda owner_id, agent_id: asyncio.sleep(0, result=configured if agent_id == "configured-1" else None),
            list_project_memberships=lambda project_id: asyncio.sleep(
                0,
                result=[
                    SimpleNamespace(agent_id="configured-1"),
                    SimpleNamespace(agent_id="manager-1"),
                ],
            ),
        )
        svc._project_execution_settings = lambda project: {
            "manager_agent_id": "manager-1",
            "blocked_handoff": {
                "mode": "configured_agent",
                "target_agent_id": "configured-1",
                "fallback_to_manager": True,
            },
        }
        asyncio.run(
            svc._apply_blocked_handoff_suggestion(
                task,
                SimpleNamespace(worker_agent_id="worker-1"),
                "blocked on test",
            )
        )
        self.assertEqual(task.metadata_json["suggested_handoff_agent_id"], "configured-1")
        self.assertEqual(task.metadata_json["handoff_suggested_via"], "configured_agent")


class RoutingModeTests(unittest.TestCase):
    def test_cost_aware_routing_prefers_cheaper_worker_when_capability_is_tied(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        cheap = SimpleNamespace(
            id="a1",
            name="Cheap",
            allowed_tools_json=["fs_read"],
            provider_config_id="provider-cheap",
            parent_agent_id=None,
        )
        costly = SimpleNamespace(
            id="a2",
            name="Costly",
            allowed_tools_json=["fs_read"],
            provider_config_id="provider-costly",
            parent_agent_id=None,
        )
        svc.db = SimpleNamespace(get=lambda model, project_id: asyncio.sleep(0, result=SimpleNamespace(settings_json={})))
        svc.repo = SimpleNamespace(
            count_active_runs_by_worker=lambda project_id, agent_ids: asyncio.sleep(0, result={"a1": 0, "a2": 0})
        )
        svc._provider_health_snapshots = lambda agents: asyncio.sleep(0, result={})
        svc._extract_required_tools = lambda task: ["fs_read"]
        svc._agent_estimated_run_cost = lambda agent: 1.0 if agent.id == "a1" else 10.0
        ranked = asyncio.run(
            svc._rank_worker_candidates(
                "project-1",
                SimpleNamespace(id="task-1", due_date=None, priority="normal"),
                [costly, cheap],
                execution_settings={"routing_mode": "cost_aware", "sibling_load_balance": "queue_depth"},
            )
        )
        self.assertEqual([agent.id for agent in ranked], ["a1", "a2"])


class ReviewerChainTests(unittest.TestCase):
    def test_reviewer_chain_advances_to_next_reviewer_before_final_approval(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        task = SimpleNamespace(
            reviewer_agent_id="rev-1",
            metadata_json={},
            status="needs_review",
        )
        project = SimpleNamespace(settings_json={})
        svc._project_execution_settings = lambda proj: {"reviewer_agent_ids": ["rev-1", "rev-2"]}
        changed = asyncio.run(svc._advance_task_reviewer_chain(task, project, "rev-1"))
        self.assertTrue(changed)
        self.assertEqual(task.reviewer_agent_id, "rev-2")
        self.assertEqual(task.metadata_json["review_chain"]["current_index"], 1)

    def test_reviewer_chain_finishes_when_last_reviewer_approves(self) -> None:
        svc = OrchestrationService.__new__(OrchestrationService)  # noqa: PLC2801
        task = SimpleNamespace(
            reviewer_agent_id="rev-2",
            metadata_json={"review_chain": {"current_index": 1}},
            status="needs_review",
        )
        project = SimpleNamespace(settings_json={})
        svc._project_execution_settings = lambda proj: {"reviewer_agent_ids": ["rev-1", "rev-2"]}
        changed = asyncio.run(svc._advance_task_reviewer_chain(task, project, "rev-2"))
        self.assertFalse(changed)
        self.assertEqual(task.reviewer_agent_id, "rev-2")


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


class DurableWorkflowTests(unittest.TestCase):
    def test_workflow_state_assigns_workflow_id_and_handle(self) -> None:
        checkpoint = ensure_workflow_state(
            {},
            run_mode="single_agent",
            steps=[{"id": "build_prompt", "title": "Build prompt", "actor": "system"}],
            run_id="run-123",
        )
        state = workflow_state(checkpoint)
        self.assertEqual(state["workflow_id"], "wf_run-123")
        self.assertEqual(state["execution_handle"]["run_id"], "run-123")
        self.assertEqual(state["migration"]["strategy"], "checkpoint-first coexistence")

    def test_workflow_state_tracks_started_and_failed_steps(self) -> None:
        checkpoint = ensure_workflow_state(
            {},
            run_mode="single_agent",
            steps=[{"id": "build_prompt", "title": "Build prompt", "actor": "system"}],
        )
        checkpoint = mark_step(checkpoint, step_id="build_prompt", status="in_progress")
        checkpoint = mark_step(
            checkpoint,
            step_id="build_prompt",
            status="failed",
            error="provider timeout",
        )
        state = checkpoint["durable_workflow_v1"]
        self.assertEqual(state["current_step_id"], "build_prompt")
        self.assertEqual(state["steps"][0]["status"], "failed")
        self.assertEqual(state["steps"][0]["last_error"], "provider timeout")

    def test_service_marks_failed_runs_resumable_when_checkpoint_has_current_step(self) -> None:
        service = object.__new__(OrchestrationService)
        checkpoint = ensure_workflow_state(
            {},
            run_mode="single_agent",
            steps=[{"id": "build_prompt", "title": "Build prompt", "actor": "system"}],
        )
        checkpoint = mark_step(checkpoint, step_id="build_prompt", status="failed", error="boom")
        run = SimpleNamespace(status="failed", checkpoint_json=checkpoint)
        self.assertTrue(service._run_is_resumable(run))

    def test_service_trace_payload_reads_checkpoint_steps(self) -> None:
        service = object.__new__(OrchestrationService)
        checkpoint = ensure_workflow_state(
            {},
            run_mode="manager_worker",
            steps=[
                {"id": "supervisor_plan", "title": "Supervisor plan", "actor": "supervisor"},
                {"id": "run_branches", "title": "Run branches", "actor": "worker_pool"},
            ],
        )
        checkpoint = mark_step(checkpoint, step_id="supervisor_plan", status="completed")
        run = SimpleNamespace(checkpoint_json=checkpoint)
        trace = service._workflow_trace_payload(run)
        self.assertEqual(len(trace), 2)
        self.assertEqual(trace[0]["status"], "completed")

    def test_signal_queue_and_query_snapshot_round_trip(self) -> None:
        checkpoint = ensure_workflow_state(
            {},
            run_mode="single_agent",
            steps=[{"id": "build_prompt", "title": "Build prompt", "actor": "system"}],
            run_id="run-1",
        )
        checkpoint = enqueue_signal(
            checkpoint,
            signal_name="add_note",
            payload={"note": "watch provider latency"},
            requested_by_user_id="user-1",
        )
        state = workflow_state(checkpoint)
        self.assertEqual(len(state["signal_queue"]), 1)
        checkpoint, consumed = consume_signal_queue(checkpoint)
        self.assertEqual(len(consumed), 1)
        checkpoint = update_query_snapshot(checkpoint, data={"latest_status": "in_progress"})
        state = workflow_state(checkpoint)
        self.assertEqual(len(state["signal_queue"]), 0)
        self.assertEqual(len(state["signal_history"]), 1)
        self.assertEqual(state["query_snapshot"]["latest_status"], "in_progress")


if __name__ == "__main__":
    unittest.main()
