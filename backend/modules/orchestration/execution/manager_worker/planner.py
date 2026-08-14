"""Manager-worker planning helpers and review payload parsing."""

from __future__ import annotations

import json
from typing import Any

from backend.modules.orchestration._helpers import BlockedExecution
from backend.modules.orchestration.execution.execution_workflow import ensure_workflow_state
from backend.modules.orchestration.execution.policies import should_skip_agent_plan
from backend.modules.orchestration.models import ProviderConfig, TaskRun


class ManagerWorkerPlannerMixin:
    async def _create_child_run(
        self,
        parent_run: TaskRun,
        *,
        sub_task: dict[str, Any],
        assigned_agent_id: str | None,
    ) -> TaskRun:
        child = await self.repo.create_run(
            parent_run_id=parent_run.id,
            project_id=parent_run.project_id,
            task_id=parent_run.task_id,
            triggered_by_user_id=parent_run.triggered_by_user_id,
            orchestrator_agent_id=parent_run.orchestrator_agent_id,
            worker_agent_id=assigned_agent_id,
            reviewer_agent_id=parent_run.reviewer_agent_id,
            provider_config_id=parent_run.provider_config_id,
            brainstorm_id=parent_run.brainstorm_id,
            run_mode="single_agent",
            status="queued",
            model_name=parent_run.model_name,
            input_payload_json={
                "subtask": sub_task,
                "parent_run_id": parent_run.id,
                "orchestration_meta": {
                    "branch_id": sub_task.get("branch_id"),
                    "branch_title": sub_task.get("title"),
                    "parent_run_id": parent_run.id,
                    "routing_reason": sub_task.get("routing_reason"),
                    "dependency_ids": sub_task.get("dependency_ids") or [],
                },
            },
        )
        child.checkpoint_json = ensure_workflow_state(
            child.checkpoint_json,
            run_mode=child.run_mode,
            steps=self._workflow_steps_for_run(child),
            run_id=child.id,
        )
        return child

    async def _plan_agent_execution(
        self,
        run: TaskRun,
        *,
        provider: ProviderConfig | None,
        agent,
        prompt: str,
        purpose: str,
        default_tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        explicit = run.input_payload_json.get("tool_calls")
        explicit_subtasks = run.input_payload_json.get("sub_tasks")
        if explicit or explicit_subtasks:
            return {
                "summary": "Using explicit input payload plan.",
                "tool_calls": explicit or default_tool_calls or [],
                "sub_tasks": explicit_subtasks or [],
            }
        plan_mode = str((run.input_payload_json or {}).get("plan_mode") or "auto").strip().lower()
        allowed_tools = list(getattr(agent, "allowed_tools_json", None) or []) if agent else []
        tool_calling = True
        if hasattr(self, "_tool_calling_allowed"):
            tool_calling = bool(self._tool_calling_allowed(agent))
        if should_skip_agent_plan(
            plan_mode=plan_mode,
            allowed_tools=allowed_tools,
            tool_calling_allowed=tool_calling,
            purpose=purpose,
        ):
            return {
                "summary": "Plan skipped (empty tools, tool calling disabled, or plan_mode=off).",
                "tool_calls": default_tool_calls or [],
                "sub_tasks": [],
            }
        _, planning_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=agent,
            system_prompt=(agent.system_prompt if agent else "You are a planning agent."),
            user_prompt=(
                f"{prompt}\n\nReturn JSON for {purpose} with keys: summary, blocked_reason, tool_calls, "
                "and sub_tasks. Each tool call must contain tool and arguments."
            ),
            response_format="json",
            purpose=purpose,
        )
        payload = planning_result.output_json or {}
        if not isinstance(payload, dict):
            payload = {}
        tool_calls = payload.get("tool_calls")
        if not isinstance(tool_calls, list):
            tool_calls = default_tool_calls or []
        sub_tasks = payload.get("sub_tasks")
        if not isinstance(sub_tasks, list):
            sub_tasks = []
        blocked_reason = payload.get("blocked_reason")
        if blocked_reason:
            raise BlockedExecution(str(blocked_reason))
        return {
            "summary": str(payload.get("summary") or planning_result.output_text[:500]),
            "tool_calls": tool_calls,
            "sub_tasks": sub_tasks,
        }

    def _build_final_prompt(
        self,
        *,
        base_prompt: str,
        execution_plan: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> str:
        sections = [base_prompt]
        if execution_plan.get("summary"):
            sections.append(f"Execution plan summary:\n{execution_plan['summary']}")
        if tool_results:
            sections.append(f"Tool results:\n{json.dumps(tool_results, indent=2, default=str)}")
        sections.append(
            "Produce the final task output. Include concrete next steps, note blockers if any remain, "
            "and keep the response usable as a task artifact."
        )
        return "\n\n".join(section for section in sections if section)

    def _coerce_review_payload(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict) and data.get("decision"):
                    reasons = data.get("reasons")
                    if isinstance(reasons, str):
                        reasons = [reasons]
                    elif not isinstance(reasons, list):
                        reasons = []
                    checklist = data.get("checklist")
                    if not isinstance(checklist, list):
                        checklist = []
                    return {
                        "decision": str(data.get("decision")),
                        "summary": str(data.get("summary") or stripped[:1200]),
                        "reasons": [str(x) for x in reasons],
                        "checklist": [str(x) for x in checklist],
                    }
            except json.JSONDecodeError:
                pass
        lowered = stripped.lower()
        decision = "approved" if "approve" in lowered and "rework" not in lowered else "rework"
        return {"decision": decision, "summary": stripped[:1200], "reasons": [], "checklist": []}
