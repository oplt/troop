"""Tool-call execution and LLM result metrics."""

from __future__ import annotations

import json
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.db.session import SessionLocal
from backend.modules.orchestration._helpers import BlockedExecution
from backend.modules.orchestration.execution.parallel_group import (
    partition_tool_calls,
    run_parallel_group,
)
from backend.modules.orchestration.models import ProviderConfig, TaskRun
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.team.models import AgentProfile
from backend.modules.workforce.services.tool_governance import tool_requires_hitl_execution_grant


class ExecutionToolCallsMixin:
    def _effective_allowed_tools(
        self, run: TaskRun, agent: AgentProfile | None
    ) -> list[str] | None:
        allowed = list(agent.allowed_tools_json or []) if agent else []
        extra = (run.input_payload_json or {}).get("agent_pattern_tools") or []
        if isinstance(extra, list):
            for tool in extra:
                slug = str(tool).strip()
                if slug and slug not in allowed:
                    allowed.append(slug)
        return allowed or None

    async def _execute_tool_call_isolated_read(
        self,
        *,
        call: dict[str, Any],
        run: TaskRun,
        project: OrchestratorProject,
        task: OrchestratorTask | None,
        effective_allowed: set[str],
    ) -> dict[str, Any]:
        tool_name = str(call.get("tool") or "").strip()
        try:
            async with SessionLocal() as session:
                repo = OrchestrationRepository(session)
                toolbox = OrchestrationToolbox(
                    db=session,
                    repo=repo,
                    project=project,
                    task=task,
                    run=run,
                )
                result = await toolbox.execute(
                    {
                        **call,
                        "allowed_tools": list(effective_allowed) if effective_allowed else None,
                        "approval_granted": bool(call.get("approval_granted")),
                    }
                )
                return {"tool": tool_name, "status": "completed", "result": result}
        except ToolExecutionError as exc:
            return {"tool": tool_name, "status": "failed", "error": str(exc)}

    async def _execute_one_tool_call(
        self,
        *,
        index: int,
        call: dict[str, Any],
        run: TaskRun,
        project: OrchestratorProject,
        task: OrchestratorTask | None,
        allowed_tools: list[str] | None,
        agent: AgentProfile | None,
        toolbox: OrchestrationToolbox,
        effective_allowed: set[str],
        secret_scope: str,
        failures: int,
    ) -> tuple[dict[str, Any], int, bool]:
        """Returns (result_payload, updated_failures, should_stop)."""
        tool_name = str(call.get("tool") or "").strip()
        self._tool_allowed_for_agent_permissions(tool_name, agent)
        if self.action_requires_approval(project, "run_tool") and tool_requires_hitl_execution_grant(
            tool_name
        ):
            grant_consumed = await self._consume_hitl_grant(
                run,
                "dangerous_tool_call",
                {"tool": tool_name, "tool_call_index": index},
            )
            if not grant_consumed:
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id if task else None,
                    run_id=run.id,
                    issue_link_id=task.github_issue_link_id if task else None,
                    requested_by_user_id=run.triggered_by_user_id,
                    approval_type="dangerous_tool_call",
                    status="pending",
                    payload_json={
                        "tool": tool_name,
                        "tool_call_index": index,
                        "arguments": call.get("arguments") or {},
                    },
                )
                await self.db.commit()
                raise BlockedExecution(
                    f"Dangerous tool '{tool_name}' requires approval (approval_id={approval.id})."
                )
        if secret_scope == "deny_external" and tool_name in {
            "github_comment",
            "github_label_issue",
            "github_create_pr",
            "web_fetch",
            "web_search",
        }:
            raise BlockedExecution(
                f"Tool '{tool_name}' blocked by secret scope policy ({secret_scope})."
            )
        if effective_allowed and tool_name not in effective_allowed:
            raise BlockedExecution(f"Tool '{tool_name}' is not allowed for this agent")
        await self._emit_run_event(
            run,
            event_type="tool_call_started",
            message=f"Executing tool {tool_name}.",
            payload={"index": index, "tool": tool_name},
        )
        try:
            result = await toolbox.execute(
                {
                    **call,
                    "allowed_tools": list(effective_allowed) if effective_allowed else None,
                    "approval_granted": bool(call.get("approval_granted")),
                }
            )
        except ToolExecutionError as exc:
            message = str(exc)
            if message.startswith("APPROVAL_REQUIRED:"):
                grant_consumed = await self._consume_hitl_grant(
                    run,
                    "dangerous_tool_call",
                    {"tool": tool_name, "tool_call_index": index},
                )
                if not grant_consumed:
                    approval = await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id if task else None,
                        run_id=run.id,
                        issue_link_id=task.github_issue_link_id if task else None,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="dangerous_tool_call",
                        status="pending",
                        payload_json={
                            "tool": tool_name,
                            "tool_call_index": index,
                            "arguments": call.get("arguments") or {},
                            "source": "action_policy",
                        },
                    )
                    await self.db.commit()
                    raise BlockedExecution(
                        f"Tool '{tool_name}' requires approval (approval_id={approval.id})."
                    ) from exc
                result = await toolbox.execute(
                    {
                        **call,
                        "allowed_tools": list(effective_allowed) if effective_allowed else None,
                        "approval_granted": True,
                    }
                )
            else:
                failures += 1
                await self._emit_run_event(
                    run,
                    event_type="tool_call_failed",
                    level="warning",
                    message=message,
                    payload={"tool": tool_name, "index": index},
                )
                should_stop = failures >= 2
                if should_stop:
                    await self._escalate_blocker(
                        run,
                        task=task,
                        reason="Multiple tool failures detected during execution.",
                        metadata={"tool_failures": failures},
                    )
                    raise BlockedExecution(
                        "Task blocked after repeated tool-call failures"
                    ) from exc
                return (
                    {"tool": tool_name, "status": "failed", "error": message},
                    failures,
                    False,
                )

        payload = {"tool": tool_name, "status": "completed", "result": result}
        await self._emit_run_event(
            run,
            event_type="tool_call_completed",
            message=f"Tool {tool_name} completed.",
            payload={
                "index": index,
                "tool": tool_name,
                "result_preview": json.dumps(result, default=str)[:500],
            },
        )
        await self._write_artifact(
            run,
            kind="tool_result",
            title=f"Tool result: {tool_name}",
            content=json.dumps(result, default=str, indent=2)[:12000],
            metadata={"tool": tool_name},
        )
        return payload, failures, False

    async def _record_parallel_tool_result(
        self,
        *,
        index: int,
        payload: dict[str, Any],
        run: TaskRun,
        task: OrchestratorTask | None,
        failures: int,
    ) -> tuple[int, bool]:
        tool_name = str(payload.get("tool") or "")
        if payload.get("status") == "failed":
            failures += 1
            await self._emit_run_event(
                run,
                event_type="tool_call_failed",
                level="warning",
                message=str(payload.get("error") or "tool failed"),
                payload={"tool": tool_name, "index": index, "parallel_group": True},
            )
            if failures >= 2:
                await self._escalate_blocker(
                    run,
                    task=task,
                    reason="Multiple tool failures detected during execution.",
                    metadata={"tool_failures": failures},
                )
                raise BlockedExecution("Task blocked after repeated tool-call failures")
            return failures, False

        result = payload.get("result")
        await self._emit_run_event(
            run,
            event_type="tool_call_completed",
            message=f"Tool {tool_name} completed.",
            payload={
                "index": index,
                "tool": tool_name,
                "parallel_group": True,
                "result_preview": json.dumps(result, default=str)[:500],
            },
        )
        await self._write_artifact(
            run,
            kind="tool_result",
            title=f"Tool result: {tool_name}",
            content=json.dumps(result, default=str, indent=2)[:12000],
            metadata={"tool": tool_name, "parallel_group": True},
        )
        return failures, True

    async def _execute_tool_calls(
        self,
        run: TaskRun,
        *,
        project: OrchestratorProject,
        task: OrchestratorTask | None,
        tool_calls: list[dict[str, Any]],
        allowed_tools: list[str] | None,
        agent: AgentProfile | None = None,
    ) -> list[dict[str, Any]]:
        if not tool_calls:
            return []
        if agent and not self._tool_calling_allowed(agent):
            await self._emit_run_event(
                run,
                event_type="tool_calls_skipped",
                level="warning",
                message="Tool calls were skipped because tool_calling_enabled is false for this agent.",
                payload={"requested": [str(c.get("tool") or "") for c in tool_calls]},
            )
            return [
                {
                    "tool": str(call.get("tool") or ""),
                    "status": "skipped",
                    "error": "Tool calling disabled by agent model policy.",
                }
                for call in tool_calls
            ]

        toolbox = OrchestrationToolbox(
            db=self.db, repo=self.repo, project=project, task=task, run=run
        )
        effective_allowed = set(allowed_tools or [])
        hitl_settings = (project.settings_json or {}).get("hitl") or {}
        secret_scope = str(hitl_settings.get("secret_scope") or "project_default")
        workspace_key = str(getattr(project, "owner_id", "") or run.project_id or "default")

        batches = partition_tool_calls(tool_calls)
        results_by_index: dict[int, dict[str, Any]] = {}
        failures = 0

        for batch in batches:
            if batch.kind == "parallel":
                group_id = batch.items[0][1].get("parallel_group_id") or batch.items[0][1].get(
                    "parallel_group"
                )
                await self._emit_run_event(
                    run,
                    event_type="tool_parallel_group_started",
                    message=f"Executing parallel read group `{group_id}`.",
                    payload={
                        "parallel_group_id": group_id,
                        "tools": [str(call.get("tool") or "") for _, call in batch.items],
                    },
                )

                async def _execute_parallel_call(
                    call_index: int, call: dict[str, Any]
                ) -> dict[str, Any]:
                    self._tool_allowed_for_agent_permissions(str(call.get("tool") or ""), agent)
                    if effective_allowed and str(call.get("tool") or "") not in effective_allowed:
                        raise BlockedExecution(
                            f"Tool '{call.get('tool')}' is not allowed for this agent"
                        )
                    if secret_scope == "deny_external" and str(call.get("tool") or "") in {
                        "github_comment",
                        "github_label_issue",
                        "github_create_pr",
                        "web_fetch",
                        "web_search",
                    }:
                        raise BlockedExecution(
                            f"Tool '{call.get('tool')}' blocked by secret scope policy ({secret_scope})."
                        )
                    return await self._execute_tool_call_isolated_read(
                        call=call,
                        run=run,
                        project=project,
                        task=task,
                        effective_allowed=effective_allowed,
                    )

                parallel_results = await run_parallel_group(
                    batch.items,
                    workspace_key=workspace_key,
                    execute_call=_execute_parallel_call,
                )
                for call_index, payload in parallel_results:
                    failures, _ = await self._record_parallel_tool_result(
                        index=call_index + 1,
                        payload=payload,
                        run=run,
                        task=task,
                        failures=failures,
                    )
                    results_by_index[call_index] = payload
                continue

            call_index, call = batch.items[0]
            payload, failures, _ = await self._execute_one_tool_call(
                index=call_index + 1,
                call=call,
                run=run,
                project=project,
                task=task,
                allowed_tools=allowed_tools,
                agent=agent,
                toolbox=toolbox,
                effective_allowed=effective_allowed,
                secret_scope=secret_scope,
                failures=failures,
            )
            results_by_index[call_index] = payload

        return [results_by_index[index] for index in range(len(tool_calls))]

    async def _apply_result_metrics(
        self,
        run: TaskRun,
        provider: ProviderConfig | None,
        results: list,
        *,
        agent=None,
        append: bool = False,
    ) -> None:
        total_in = sum(item.input_tokens for item in results)
        total_out = sum(item.output_tokens for item in results)
        total_latency = sum(item.latency_ms for item in results)
        call_micros = sum(
            self._estimate_cost_micros(
                provider,
                item.input_tokens,
                item.output_tokens,
                model_name=getattr(item, "model_name", None) or run.model_name,
            )
            for item in results
        )
        if append:
            run.token_input += total_in
            run.token_output += total_out
            run.latency_ms = (run.latency_ms or 0) + total_latency
            run.estimated_cost_micros = (run.estimated_cost_micros or 0) + call_micros
        else:
            run.token_input = total_in
            run.token_output = total_out
            run.latency_ms = total_latency
            run.estimated_cost_micros = call_micros
        run.token_total = run.token_input + run.token_output
        token_budget = (agent.budget_json or {}).get("token_budget") if agent else None
        if token_budget and run.token_total > int(token_budget):
            await self._emit_run_event(
                run,
                event_type="budget_exceeded",
                level="warning",
                message=f"Token budget {token_budget} exceeded ({run.token_total} used).",
            )
