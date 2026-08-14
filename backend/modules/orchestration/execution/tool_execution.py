"""Tool-call execution and LLM result metrics."""

from __future__ import annotations

import json
from typing import Any

from backend.modules.orchestration._helpers import BlockedExecution
from backend.modules.orchestration.models import ProviderConfig, TaskRun
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.team.models import AgentProfile


class ExecutionToolCallsMixin:
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
        results: list[dict[str, Any]] = []
        failures = 0
        effective_allowed = set(allowed_tools or [])
        dangerous_tools = {
            "code_execute",
            "db_query",
            "fs_write",
            "github_create_pr",
            "github_label_issue",
        }
        hitl_settings = (project.settings_json or {}).get("hitl") or {}
        secret_scope = str(hitl_settings.get("secret_scope") or "project_default")
        for index, call in enumerate(tool_calls, start=1):
            tool_name = str(call.get("tool") or "").strip()
            self._tool_allowed_for_agent_permissions(tool_name, agent)
            if self.action_requires_approval(project, "run_tool") and tool_name in dangerous_tools:
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
                        )
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
                    results.append({"tool": tool_name, "status": "failed", "error": message})
                    if failures >= 2:
                        await self._escalate_blocker(
                            run,
                            task=task,
                            reason="Multiple tool failures detected during execution.",
                            metadata={"tool_failures": failures},
                        )
                        raise BlockedExecution(
                            "Task blocked after repeated tool-call failures"
                        ) from exc
                    continue
            results.append({"tool": tool_name, "status": "completed", "result": result})
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
        return results

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
