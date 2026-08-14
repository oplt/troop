"""User-facing run commands: start, cancel, resume, replay."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import attributes as orm_attributes

from backend.core.logging import get_logger
from backend.modules.identity_access.models import User
from backend.modules.orchestration.constants import TASK_TRANSITIONS
from backend.modules.orchestration.execution.execution_workflow import (
    ensure_workflow_state,
    increment_resume_count,
    update_query_snapshot,
)
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask

logger = get_logger(__name__)


class ExecutionRunCommandsMixin:
    async def start_task_run(
        self,
        user: User,
        project_id: str,
        task_id: str,
        payload: dict[str, Any],
    ) -> tuple[TaskRun, list[str]]:
        project = await self.get_project(user, project_id)
        task = await self.get_task(user, project_id, task_id)
        deps = await self.repo.list_task_dependencies_for_task(task.id)
        if deps:
            blocking = []
            for dep in deps:
                dep_task = await self.db.get(OrchestratorTask, dep.depends_on_task_id)
                if dep_task and dep_task.status not in {"completed", "approved"}:
                    blocking.append(dep_task.title)
            if blocking:
                raise HTTPException(400, f"Task has incomplete dependencies: {blocking}")
        execution_settings = self._project_execution_settings(project)
        run_mode = payload.get("run_mode", "single_agent")
        orchestrator_agent_id = payload.get("orchestrator_agent_id") or execution_settings.get(
            "manager_agent_id"
        )
        reviewer_agent_id = payload.get("reviewer_agent_id") or task.reviewer_agent_id
        if reviewer_agent_id is None:
            reviewer_ids = execution_settings.get("reviewer_agent_ids", [])
            reviewer_agent_id = reviewer_ids[0] if reviewer_ids else None
        if reviewer_agent_id and task.reviewer_agent_id != reviewer_agent_id:
            task.reviewer_agent_id = reviewer_agent_id
            chain = [
                str(item).strip()
                for item in execution_settings.get("reviewer_agent_ids", [])
                if str(item).strip()
            ]
            if chain and reviewer_agent_id in chain:
                meta = dict(task.metadata_json or {})
                meta["review_chain"] = {
                    "reviewer_agent_ids": chain,
                    "current_index": chain.index(reviewer_agent_id),
                }
                task.metadata_json = meta
                orm_attributes.flag_modified(task, "metadata_json")

        worker_explicit = (
            "worker_agent_id" in payload and payload.get("worker_agent_id") is not None
        )
        if worker_explicit:
            worker_agent_id = payload.get("worker_agent_id")
            worker_source = "payload"
        else:
            pinned_raw = (
                payload.get("pinned_worker_agent_id")
                or (task.metadata_json or {}).get("pinned_worker_agent_id")
                or execution_settings.get("pinned_worker_agent_id")
            )
            if pinned_raw:
                worker_agent_id = str(pinned_raw)
                worker_source = "pinned"
            elif task.assigned_agent_id:
                worker_agent_id = task.assigned_agent_id
                worker_source = "task"
            else:
                worker_agent_id = None
                worker_source = None

        if run_mode in {"single_agent", "manager_worker", "debate"} and worker_agent_id is None:
            selected_worker = await self._select_best_agent_for_task(
                project.id,
                task=task,
                exclude_agent_ids=[orchestrator_agent_id] if orchestrator_agent_id else [],
            )
            worker_agent_id = selected_worker.id if selected_worker else None
            worker_source = "auto" if worker_agent_id else worker_source

        if run_mode == "manager_worker" and orchestrator_agent_id is None:
            manager = await self._project_default_manager(project.id)
            orchestrator_agent_id = manager.id if manager else None

        if run_mode == "debate":
            pair = await self._select_debate_pair(
                project.id,
                task,
                exclude_agent_ids=[orchestrator_agent_id] if orchestrator_agent_id else [],
            )
            if pair:
                worker_agent_id = pair[0].id
                if len(pair) > 1:
                    reviewer_agent_id = pair[1].id
                worker_source = "debate_pair"

        if worker_agent_id and worker_source == "pinned":
            member_ids = {m.agent_id for m in await self.repo.list_project_memberships(project.id)}
            if worker_agent_id not in member_ids:
                raise HTTPException(
                    status_code=400,
                    detail="pinned_worker_agent_id is not a member of this project.",
                )
            p_agent = await self._load_agent_for_run(worker_agent_id)
            if p_agent is None or not p_agent.is_active:
                raise HTTPException(
                    status_code=400, detail="Pinned worker agent is missing or inactive."
                )
            if not self._agent_eligible_for_task_by_filters(p_agent, task):
                raise HTTPException(
                    status_code=400,
                    detail="Pinned worker agent task_filters do not match this task.",
                )

        if run_mode in {"single_agent", "manager_worker", "debate"} and worker_agent_id:
            worker = await self._load_agent_for_run(worker_agent_id)
            req_tools = self._extract_required_tools(task)
            if req_tools and not self._required_tools_satisfied(worker, req_tools):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Worker agent allowed_tools must include every task required_tools entry: "
                        + ", ".join(req_tools)
                    ),
                )

        payload_model = payload.get("model_name")
        if payload_model not in (None, ""):
            model_source = "payload"
        elif execution_settings.get("model_name"):
            model_source = "project_execution"
        else:
            model_source = "runtime_default"
        model_name = payload_model or execution_settings.get("model_name")

        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=worker_agent_id)
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=worker_agent_id)
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=orchestrator_agent_id
        )
        await self._enforce_orchestration_run_rate_limit(user.id)

        selection_meta = await self._run_selection_meta(
            project_id=project.id,
            task=task,
            payload=payload,
            execution_settings=execution_settings,
            run_mode=run_mode,
            worker_agent_id=worker_agent_id,
            orchestrator_agent_id=orchestrator_agent_id,
            worker_source=worker_source,
            model_name=model_name,
            model_source=model_source,
        )
        input_payload = dict(payload.get("input_payload") or {})
        prev_meta = input_payload.get("orchestration_meta")
        if isinstance(prev_meta, dict):
            input_payload["orchestration_meta"] = {**prev_meta, **selection_meta}
        else:
            input_payload["orchestration_meta"] = selection_meta

        task_meta = dict(task.metadata_json or {})
        task_meta["routing_explainability"] = self._routing_explainability_from_payload(
            {"orchestration_meta": input_payload.get("orchestration_meta")}
        )
        task.metadata_json = task_meta
        orm_attributes.flag_modified(task, "metadata_json")

        run = await self.repo.create_run(
            project_id=project_id,
            task_id=task.id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=orchestrator_agent_id,
            worker_agent_id=worker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            provider_config_id=payload.get("provider_config_id")
            or execution_settings.get("provider_config_id"),
            run_mode=run_mode,
            status="queued",
            model_name=model_name,
            input_payload_json=input_payload,
        )
        run.checkpoint_json = ensure_workflow_state(
            run.checkpoint_json,
            run_mode=run.run_mode,
            steps=self._workflow_steps_for_run(run),
            run_id=run.id,
        )
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={
                "latest_status": "queued",
                "run_id": run.id,
                "task_id": task.id,
                "project_id": project_id,
                "worker_agent_id": worker_agent_id,
                "orchestrator_agent_id": orchestrator_agent_id,
            },
        )
        # Freeze SkillVersion IDs for the lifetime of this run (immutable snapshot).
        # Fail closed for workforce runs — never silently proceed without a snapshot.
        from backend.modules.orchestration.task_run_starter import freeze_or_degrade_snapshot

        await freeze_or_degrade_snapshot(
            self.db,
            run,
            agent_id=worker_agent_id or orchestrator_agent_id,
            allow_degraded=bool((payload or {}).get("allow_degraded_snapshot")),
        )
        startup_warnings: list[str] = []
        resolution_agent = await self._load_agent_for_run(worker_agent_id or orchestrator_agent_id)
        resolved_provider = await self._resolve_provider_for_run(run, resolution_agent)
        if resolved_provider is None:
            startup_warnings.append(
                "No LLM provider is configured for this run: the worker agent has no provider, and no project or "
                "run-level default provider was found. The run will use stub/heuristic output until you add a provider "
                "(Admin → Settings → Providers) and assign it to the agent or project."
            )
        # Only move the task when the state machine allows it. in_progress → queued is invalid (409); follow-up runs
        # while a task is already active leave the task status unchanged. Re-runs after completion use planned.
        allowed_next = TASK_TRANSITIONS.get(task.status, set())
        if task.status == "queued":
            pass
        elif "queued" in allowed_next:
            await self._transition_task_status(task, "queued", run=run, reason="run queued")
        elif task.status == "completed" and "planned" in allowed_next:
            await self._transition_task_status(
                task, "planned", run=run, reason="run queued after completion"
            )
        await self._emit_run_event(
            run,
            event_type="queued",
            message="Run queued for execution.",
            payload={"run_mode": run.run_mode},
        )
        if startup_warnings:
            await self._emit_run_event(
                run,
                event_type="startup_notice",
                level="warning",
                message=startup_warnings[0],
                payload={"warnings": startup_warnings},
            )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(run.id, expected_owner_id=project.owner_id)
        await self.db.refresh(run)
        return run, startup_warnings

    async def cancel_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        child_runs = await self._child_runs_for_parent(run.id)
        run.status = "cancelled"
        run.cancelled_at = datetime.now(UTC)
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={
                "latest_status": "cancelled",
                "cancelled_at": run.cancelled_at.isoformat(),
                "run_id": run.id,
            },
        )
        for child in child_runs:
            if child.status in {"queued", "in_progress", "blocked"}:
                child.status = "cancelled"
                child.cancelled_at = run.cancelled_at
                child.checkpoint_json = update_query_snapshot(
                    child.checkpoint_json,
                    data={"latest_status": "cancelled", "parent_run_id": run.id},
                )
                await self._emit_run_event(
                    child,
                    event_type="cancelled",
                    level="warning",
                    message="Child run cancelled with parent.",
                    payload={"parent_run_id": run.id},
                )
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        if task and task.status in {"queued", "planned", "in_progress"}:
            await self._transition_task_status(task, "planned", run=run, reason="run cancelled")
        await self._emit_run_event(
            run,
            event_type="cancelled",
            level="warning",
            message="Run cancelled by user.",
        )
        await self.db.commit()
        try:
            from backend.modules.workforce.services.workflow_hooks import on_task_run_terminal

            await on_task_run_terminal(self.db, run.id, status="cancelled")
        except Exception:
            logger.exception("workflow_task_run_terminal_hook_failed run_id=%s", run.id)
        for child in child_runs:
            if child.status != "cancelled":
                continue
            try:
                from backend.modules.workforce.services.workflow_hooks import on_task_run_terminal

                await on_task_run_terminal(self.db, child.id, status="cancelled")
            except Exception:
                logger.exception("workflow_task_run_terminal_hook_failed run_id=%s", child.id)
        await self.db.refresh(run)
        return run

    async def resume_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        if not self._run_is_resumable(run):
            raise HTTPException(
                status_code=409, detail="Run is not resumable from its current checkpoint."
            )
        run.status = "queued"
        run.error_message = None
        run.completed_at = None
        run.cancelled_at = None
        run.checkpoint_json = increment_resume_count(run.checkpoint_json)
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={"latest_status": "queued", "resume_requested_by": user.id, "run_id": run.id},
        )
        await self._emit_run_event(
            run,
            event_type="workflow_resumed",
            message="Run resumed from durable checkpoint.",
            payload={"trace": self._workflow_trace_payload(run)},
        )
        for child in await self._child_runs_for_parent(run.id):
            if child.status in {"blocked", "failed"}:
                child.status = "queued"
                child.error_message = None
                child.completed_at = None
                child.cancelled_at = None
                child.checkpoint_json = increment_resume_count(child.checkpoint_json)
                await self._emit_run_event(
                    child,
                    event_type="workflow_resumed",
                    message="Child run re-queued from parent resume.",
                    payload={"parent_run_id": run.id},
                )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        project = await self.db.get(OrchestratorProject, run.project_id)
        submit_orchestration_run(
            run.id,
            expected_owner_id=project.owner_id if project else user.id,
        )
        await self.db.refresh(run)
        return run

    async def replay_run(
        self,
        user: User,
        run_id: str,
        from_event_index: int = 0,
        *,
        model_name: str | None = None,
    ):
        """Queue a new run that carries forward transcript context from a parent run."""
        old = await self.get_run(user, run_id)
        old_project = await self.db.get(OrchestratorProject, old.project_id)
        if old_project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await self._enforce_agent_token_budget(
            owner_id=old_project.owner_id, agent_id=old.worker_agent_id
        )
        await self._enforce_agent_token_budget(
            owner_id=old_project.owner_id, agent_id=old.orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=old_project.owner_id, agent_id=old.worker_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=old_project.owner_id, agent_id=old.orchestrator_agent_id
        )
        events = await self.repo.list_run_events(old.id)
        if from_event_index < 0 or from_event_index > len(events):
            raise HTTPException(
                status_code=400, detail="from_event_index is out of range for this run"
            )
        await self._enforce_orchestration_run_rate_limit(user.id)
        prior = events[:from_event_index]
        transcript = "\n".join(f"[{e.event_type}] {e.message}" for e in prior)
        base_input = dict(old.input_payload_json or {})
        base_input.pop("orchestration_replay", None)
        base_input["orchestration_replay"] = {
            "parent_run_id": old.id,
            "from_event_index": from_event_index,
            "prior_transcript": transcript[:12000],
        }
        old_orch = base_input.get("orchestration_meta")
        if isinstance(old_orch, dict):
            base_input["orchestration_meta"] = {**old_orch, "replayed_from_run_id": old.id}
        else:
            base_input["orchestration_meta"] = {"replayed_from_run_id": old.id}
        new_run = await self.repo.create_run(
            parent_run_id=getattr(old, "parent_run_id", None),
            project_id=old.project_id,
            task_id=old.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=old.orchestrator_agent_id,
            worker_agent_id=old.worker_agent_id,
            reviewer_agent_id=old.reviewer_agent_id,
            provider_config_id=old.provider_config_id,
            brainstorm_id=old.brainstorm_id,
            run_mode=old.run_mode,
            status="queued",
            model_name=(str(model_name).strip() or old.model_name)
            if model_name is not None
            else old.model_name,
            attempt_number=old.attempt_number + 1,
            retry_count=old.retry_count,
            checkpoint_json=dict(old.checkpoint_json or {}),
            input_payload_json=base_input,
        )
        new_run.checkpoint_json = ensure_workflow_state(
            new_run.checkpoint_json,
            run_mode=new_run.run_mode,
            steps=self._workflow_steps_for_run(new_run),
            run_id=new_run.id,
        )
        new_run.checkpoint_json = update_query_snapshot(
            new_run.checkpoint_json,
            data={"latest_status": "queued", "replayed_from_run_id": old.id, "run_id": new_run.id},
        )
        task = await self.db.get(OrchestratorTask, new_run.task_id) if new_run.task_id else None
        if task:
            await self._transition_task_status(task, "queued", run=new_run, reason="replay queued")
        await self._emit_run_event(
            new_run,
            event_type="replay_queued",
            message=f"Replay from run {old.id} starting after event index {from_event_index}.",
            payload={"parent_run_id": old.id, "from_event_index": from_event_index},
        )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(new_run.id, expected_owner_id=old_project.owner_id)
        await self.db.refresh(new_run)
        return new_run
