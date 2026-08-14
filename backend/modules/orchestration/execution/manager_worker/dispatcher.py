"""Manager-worker delegation graph execution."""

from __future__ import annotations

import json
from typing import Any

from backend.modules.orchestration._helpers import BlockedExecution
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


class ManagerWorkerDispatcherMixin:
    async def _execute_manager_worker_run(self, run: TaskRun) -> None:
        manager = await self._load_agent_for_run(run.orchestrator_agent_id)
        explicit_worker = await self._load_agent_for_run(run.worker_agent_id)
        provider = await self._resolve_provider_for_run(run, explicit_worker or manager)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        if (
            manager
            and explicit_worker
            and not self._delegation_edge_allowed(manager, explicit_worker, project=project)
        ):
            raise RuntimeError(
                "Manager cannot delegate to the selected worker (hierarchy or delegation_rules allowlist)."
            )
        await self._emit_run_event(
            run,
            event_type="manager_planning",
            message="Manager agent building execution graph...",
        )
        manager_plan = self._workflow_checkpoint_artifact(run, "manager_worker.plan")
        routed_sub_tasks = self._workflow_checkpoint_artifact(
            run, "manager_worker.routed_sub_tasks"
        )
        branch_results = self._workflow_checkpoint_artifact(run, "manager_worker.branch_results")

        if not isinstance(manager_plan, dict) or not manager_plan:
            await self._mark_run_step(
                run,
                step_id="planning",
                status="in_progress",
                message="Supervisor is planning delegated work.",
            )
            planning_prompt = await self._build_task_prompt(
                run,
                manager,
                prefix=(
                    "Produce a JSON execution graph with sub_tasks, required_tools, required_capabilities, "
                    "and whether each branch can run in parallel."
                ),
            )
            manager_plan = await self._plan_agent_execution(
                run,
                provider=provider,
                agent=manager,
                prompt=planning_prompt,
                purpose="manager delegation graph",
                default_tool_calls=[],
            )
            self._set_workflow_checkpoint_artifact(
                run, key="manager_worker.plan", value=manager_plan
            )
            await self._mark_run_step(
                run,
                step_id="planning",
                status="completed",
                message="Supervisor plan checkpoint saved.",
                metadata={"sub_task_count": len(manager_plan.get("sub_tasks") or [])},
            )

        sub_tasks = manager_plan.get("sub_tasks") or [
            {
                "title": task.title if task else "Primary task",
                "description": task.description if task else "",
                "required_tools": self._extract_required_tools(task),
                "required_capabilities": self._extract_required_tools(task),
                "parallelizable": False,
            }
        ]

        if not isinstance(routed_sub_tasks, list) or not routed_sub_tasks:
            await self._mark_run_step(
                run,
                step_id="subtask_dispatch",
                status="in_progress",
                message="Supervisor is routing subtasks to workers.",
            )
            candidate_workers = await self._candidate_workers(
                project.id, manager=manager, explicit_worker=explicit_worker, task=task
            )
            routed_sub_tasks = await self._route_sub_tasks_to_agents(
                project.id,
                sub_tasks,
                candidate_workers,
                manager=manager,
                parent_task=task,
            )
            self._set_workflow_checkpoint_artifact(
                run,
                key="manager_worker.routed_sub_tasks",
                value=routed_sub_tasks,
            )
            await self._emit_run_event(
                run,
                event_type="manager_plan",
                message="Manager created an execution graph.",
                payload={"sub_tasks": routed_sub_tasks},
            )
            await self._mark_run_step(
                run,
                step_id="subtask_dispatch",
                status="completed",
                message="Worker routing checkpoint saved.",
            )

        if not isinstance(branch_results, list):
            await self._mark_run_step(
                run,
                step_id="worker_execution",
                status="in_progress",
                message="Executing delegated branches.",
            )
            branch_results = []
            pending_by_id = {str(item.get("branch_id")): item for item in routed_sub_tasks}
            completed_ids: set[str] = set()
            while pending_by_id:
                ready = [
                    item
                    for item in pending_by_id.values()
                    if set(item.get("dependency_ids") or []).issubset(completed_ids)
                ]
                if not ready:
                    branch_results.extend(
                        [
                            {
                                **item,
                                "status": "blocked",
                                "reason": "dependency_cycle_or_missing_dependency",
                                "blocker_reason": "Dependency cycle or missing dependency prevented execution.",
                            }
                            for item in pending_by_id.values()
                        ]
                    )
                    break
                parallel = [item for item in ready if item.get("parallelizable")]
                sequential = [item for item in ready if not item.get("parallelizable")]
                max_branches = int(
                    (run.input_payload_json or {}).get("max_parallel_branches")
                    or (
                        (project.settings_json or {}).get("execution") or {}
                    ).get("max_parallel_branches")
                    or 999
                )
                if parallel and max_branches < len(parallel):
                    overflow = parallel[max_branches:]
                    parallel = parallel[:max_branches]
                    for item in overflow:
                        sequential.append({**item, "parallelizable": False})
                if parallel:
                    scheduled: list[tuple[dict[str, Any], TaskRun]] = []
                    for item in parallel:
                        scheduled.append(
                            (
                                item,
                                await self._create_child_run(
                                    run,
                                    sub_task=item,
                                    assigned_agent_id=item.get("assigned_agent_id"),
                                ),
                            )
                        )
                    for item, child_run in scheduled:
                        branch_results.append(
                            await self._execute_subtask_branch(
                                run,
                                child_run,
                                provider,
                                item,
                                project=project,
                                manager=manager,
                            )
                        )
                for item in sequential:
                    child_run = await self._create_child_run(
                        run,
                        sub_task=item,
                        assigned_agent_id=item.get("assigned_agent_id"),
                    )
                    branch_results.append(
                        await self._execute_subtask_branch(
                            run,
                            child_run,
                            provider,
                            item,
                            project=project,
                            manager=manager,
                        )
                    )
                completed_ids.update(
                    {
                        str(item.get("branch_id"))
                        for item in branch_results
                        if item.get("status") == "completed"
                    }
                )
                for item in ready:
                    pending_by_id.pop(str(item.get("branch_id")), None)
            self._set_workflow_checkpoint_artifact(
                run,
                key="manager_worker.branch_results",
                value=branch_results,
            )
            await self._mark_run_step(
                run,
                step_id="worker_execution",
                status="completed",
                message="Branch execution checkpoint saved.",
                metadata={"branch_count": len(branch_results)},
            )

        blocked = [item for item in branch_results if item.get("status") == "blocked"]
        self._set_workflow_checkpoint_artifact(
            run, key="manager_worker.blocker_queue", value=blocked
        )
        if blocked:
            await self._mark_run_step(
                run,
                step_id="blocker_resolution",
                status="in_progress",
                message="Supervisor is resolving blockers.",
            )
            if manager:
                _, handoff_result = await self._execute_with_routing(
                    run,
                    provider=provider,
                    agent=manager,
                    system_prompt=manager.system_prompt or "You are an escalation manager.",
                    user_prompt=(
                        "One or more delegated branches are blocked. Resolve the blockers or escalate.\n\n"
                        f"{json.dumps(blocked, indent=2)}"
                    ),
                    purpose="manager escalation",
                )
                await self._emit_run_event(
                    run,
                    event_type="manager_handoff",
                    message="Manager reviewed blocked branches.",
                    payload={
                        "blocked_count": len(blocked),
                        "resolution": handoff_result.output_text[:1000],
                    },
                )
            for item in blocked:
                await self._escalate_blocker(
                    run,
                    task=task,
                    reason=str(
                        item.get("blocker_reason")
                        or item.get("reason")
                        or "Delegated branch blocked"
                    ),
                    metadata={"branch": item},
                )
            raise BlockedExecution(
                "Delegated sub-task execution is blocked and requires escalation"
            )
        await self._mark_run_step(
            run,
            step_id="blocker_resolution",
            status="completed",
            message="No unresolved blockers remain.",
        )
        synthesis_input = json.dumps(branch_results, indent=2)
        synth_agent = explicit_worker or manager
        _, synthesis_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=synth_agent,
            system_prompt=(
                manager.system_prompt if manager else "You are an orchestration manager."
            ),
            user_prompt=(
                "Synthesize the delegated worker outputs into a final deliverable with decisions, "
                "tradeoffs, and next steps.\n\n"
                f"{synthesis_input}"
            ),
            purpose="manager synthesis",
            response_format=self._structured_output_response_format(synth_agent),
        )
        run.output_payload_json = {
            "manager_plan": manager_plan,
            "branches": branch_results,
            "summary": synthesis_result.output_text[:1200],
            "final_output": synthesis_result.output_text,
        }
        self._set_workflow_checkpoint_artifact(
            run,
            key="manager_worker.output_payload",
            value=run.output_payload_json,
        )
        review_round = (
            int(self._workflow_checkpoint_artifact(run, "manager_worker.review_round", 0) or 0) + 1
        )
        self._set_workflow_checkpoint_artifact(
            run, key="manager_worker.review_round", value=review_round
        )
        await self._mark_run_step(
            run,
            step_id="review",
            status="in_progress",
            message="Reviewer is validating the consolidated result.",
        )
        if run.reviewer_agent_id:
            reviewer = await self._load_agent_for_run(run.reviewer_agent_id)
            _, review_result = await self._execute_with_routing(
                run,
                provider=provider,
                agent=reviewer,
                system_prompt=(
                    reviewer.system_prompt if reviewer else "You are a careful reviewer."
                ),
                user_prompt=(
                    "Review this manager-worker delivery. Return JSON with decision, summary, reasons, checklist, rework_scope.\n\n"
                    f"Task title: {task.title if task else 'Unknown'}\n"
                    f"Acceptance criteria: {task.acceptance_criteria if task else ''}\n"
                    f"Branch results: {json.dumps(branch_results, indent=2, default=str)}\n"
                    f"Final output: {synthesis_result.output_text}"
                ),
                response_format="json",
                purpose="manager-worker review",
            )
            review_payload = (
                review_result.output_json
                if isinstance(review_result.output_json, dict)
                and review_result.output_json.get("decision")
                else self._coerce_review_payload(review_result.output_text)
            )
        else:
            review_payload = {
                "decision": "approved",
                "summary": "No reviewer configured; manager-worker flow auto-approved.",
                "reasons": [],
                "checklist": [],
                "rework_scope": [],
            }
        review_state = self._review_state_from_payload(review_payload, round_number=review_round)
        self._set_workflow_checkpoint_artifact(
            run, key="manager_worker.review_state", value=review_state
        )
        run.output_payload_json["review_state"] = review_state
        if review_state["decision"] != "approved":
            if task:
                self._append_structured_reopen_record(task, review_payload, run=run)
                await self._transition_task_status(
                    task, "planned", run=run, reason="review requested rework"
                )
            affected_scope = set(review_state.get("rework_scope") or [])
            for child in await self._child_runs_for_parent(run.id):
                branch_title = str(
                    ((child.input_payload_json or {}).get("subtask") or {}).get("title") or ""
                )
                if not affected_scope or branch_title in affected_scope:
                    child.status = "planned"
            raise BlockedExecution("Reviewer requested rework on one or more delegated branches")
        await self._mark_run_step(
            run,
            step_id="review",
            status="completed",
            message="Reviewer approved the consolidated result.",
        )
        if task:
            await self._transition_task_status(task, "approved", run=run, reason="review approved")
        await self._mark_run_step(
            run,
            step_id="artifact_publish",
            status="in_progress",
            message="Publishing final artifacts.",
        )
        await self._publish_final_artifacts(
            run,
            branch_results=branch_results,
            review_state=review_state,
        )
        await self._write_artifact(
            run,
            kind="execution_graph",
            title="Manager execution graph",
            content=json.dumps(manager_plan, indent=2),
            metadata={"sub_task_count": len(routed_sub_tasks)},
        )
        await self._mark_run_step(
            run,
            step_id="artifact_publish",
            status="completed",
            message="Final artifacts published.",
        )
        await self._run_manager_worker_external_action_sync(run, task)
