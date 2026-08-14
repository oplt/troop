"""Single-agent checkpointed execution."""

from __future__ import annotations

from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


class ManagerWorkerSingleAgentMixin:
    async def _execute_single_agent_run(self, run: TaskRun) -> None:
        agent = await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id)
        provider = await self._resolve_provider_for_run(run, agent)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        prompt = self._workflow_checkpoint_artifact(run, "single_agent.prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            await self._mark_run_step(
                run,
                step_id="build_prompt",
                status="in_progress",
                message="Building task prompt.",
            )
            await self._emit_run_event(
                run, event_type="prompt_building", message="Building task prompt..."
            )
            prompt = await self._build_task_prompt(run, agent)
            self._set_workflow_checkpoint_artifact(run, key="single_agent.prompt", value=prompt)
            await self._mark_run_step(
                run,
                step_id="build_prompt",
                status="completed",
                message="Task prompt checkpoint saved.",
            )

        execution_plan = self._workflow_checkpoint_artifact(run, "single_agent.plan")
        if not isinstance(execution_plan, dict) or not execution_plan:
            await self._mark_run_step(
                run,
                step_id="plan_execution",
                status="in_progress",
                message="Planning single-agent execution.",
            )
            execution_plan = await self._plan_agent_execution(
                run,
                provider=provider,
                agent=agent,
                prompt=prompt,
                purpose="single-agent task execution",
            )
            self._set_workflow_checkpoint_artifact(
                run, key="single_agent.plan", value=execution_plan
            )
            await self._mark_run_step(
                run,
                step_id="plan_execution",
                status="completed",
                message="Execution plan checkpoint saved.",
                metadata={"tool_call_count": len(execution_plan.get("tool_calls", []))},
            )

        tool_results = self._workflow_checkpoint_artifact(run, "single_agent.tool_results")
        if not isinstance(tool_results, list):
            await self._mark_run_step(
                run,
                step_id="run_tools",
                status="in_progress",
                message="Executing planned tools.",
            )
            tool_results = await self._execute_tool_calls(
                run,
                project=project,
                task=task,
                tool_calls=execution_plan.get("tool_calls", []),
                allowed_tools=(agent.allowed_tools_json if agent else []),
                agent=agent,
            )
            self._set_workflow_checkpoint_artifact(
                run, key="single_agent.tool_results", value=tool_results
            )
            await self._mark_run_step(
                run,
                step_id="run_tools",
                status="completed",
                message="Tool results checkpoint saved.",
                metadata={"completed_tools": len(tool_results)},
            )

        final_prompt = self._build_final_prompt(
            base_prompt=prompt,
            execution_plan=execution_plan,
            tool_results=tool_results,
        )
        model_name = run.model_name or (provider.default_model if provider else None)
        await self._mark_run_step(
            run,
            step_id="model_response",
            status="in_progress",
            message=f"Requesting model response ({model_name or 'default'}).",
        )
        await self._emit_run_event(
            run,
            event_type="llm_request",
            message=f"Sending request to model ({model_name or 'default'})...",
            payload={"prompt_chars": len(final_prompt), "tool_calls": len(tool_results)},
        )
        provider, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=agent,
            system_prompt=agent.system_prompt if agent else "You are a helpful software agent.",
            user_prompt=final_prompt,
            purpose="single-agent execution",
            response_format=self._structured_output_response_format(agent),
        )
        run.output_payload_json = {
            "plan": execution_plan,
            "tool_results": tool_results,
            "summary": result.output_text[:1200],
            "final_output": result.output_text,
            "structured_output_json": result.output_json,
        }
        self._set_workflow_checkpoint_artifact(
            run,
            key="single_agent.output_payload",
            value=run.output_payload_json,
        )
        await self._mark_run_step(
            run,
            step_id="model_response",
            status="completed",
            message="Model response checkpoint saved.",
            metadata={"output_chars": len(result.output_text)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="in_progress",
            message="Persisting execution artifacts.",
        )
        await self._write_artifact(
            run,
            kind="run_output",
            title="Execution output",
            content=result.output_text,
            metadata={"tool_calls": len(tool_results)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="completed",
            message="Execution artifacts persisted.",
        )
