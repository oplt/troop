"""Worker execute_run path, retry, and stale-run recovery."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.memory.working_memory import EXECUTION_THREAD_ID_KEY
from backend.modules.orchestration._helpers import BlockedExecution
from backend.modules.orchestration.execution.durable_execution import is_run_execution_claimable
from backend.modules.orchestration.execution.execution_workflow import (
    consume_signal_queue,
    current_step,
    mark_step,
    set_workflow_artifact,
    update_query_snapshot,
)
from backend.modules.orchestration.execution.policies import next_retry_numbers
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.identity_access.models import User

logger = get_logger(__name__)


class ExecutionRunExecutionMixin:
    async def _compress_run_context_if_needed(self, run: TaskRun) -> None:
        payload = dict(run.input_payload_json or {})
        replay = payload.get("orchestration_replay")
        if not isinstance(replay, dict):
            return
        transcript = str(replay.get("prior_transcript") or "")
        if len(transcript) < 4000:
            return
        compressed = transcript[:1800] + "\n...\n" + transcript[-1200:]
        replay["prior_transcript"] = compressed
        payload["orchestration_replay"] = replay
        run.input_payload_json = payload
        saved_chars = max(len(transcript) - len(compressed), 0)
        run.checkpoint_json = set_workflow_artifact(
            run.checkpoint_json,
            key="context_compression",
            value={
                "saved_chars": saved_chars,
                "saved_tokens_estimate": int(saved_chars / 4),
            },
        )
        await self._emit_run_event(
            run,
            event_type="context_compressed",
            message="Replay context compressed to reduce token usage.",
            payload={"saved_chars": saved_chars, "saved_tokens_estimate": int(saved_chars / 4)},
        )

    async def _enforce_run_output_schema(self, run: TaskRun) -> None:
        agent = await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id)
        schema = (agent.output_schema_json or {}) if agent else {}
        fmt = str(schema.get("format") or "").strip()
        final_output = str(
            (run.output_payload_json or {}).get("final_output")
            or (run.output_payload_json or {}).get("summary")
            or ""
        )
        if not fmt or not final_output:
            return
        valid = True
        if fmt == "json":
            structured = (run.output_payload_json or {}).get("structured_output_json")
            if isinstance(structured, (dict, list)):
                valid = True
            else:
                try:
                    json.loads(final_output)
                except Exception:
                    valid = False
        elif fmt == "checklist":
            valid = "- " in final_output or "1." in final_output
        elif fmt == "adr":
            low = final_output.lower()
            valid = "decision" in low and "context" in low
        elif fmt == "patch_proposal":
            low = final_output.lower()
            valid = "file" in low and "test" in low
        elif fmt == "issue_reply":
            low = final_output.lower()
            valid = "finding" in low or "review" in low
        else:
            valid = False
        if not valid:
            raise BlockedExecution(f"Output validation failed for schema format '{fmt}'.")
    async def retry_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        new_run = await self.repo.create_run(
            parent_run_id=run.parent_run_id,
            project_id=run.project_id,
            task_id=run.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=run.orchestrator_agent_id,
            worker_agent_id=run.worker_agent_id,
            reviewer_agent_id=run.reviewer_agent_id,
            provider_config_id=run.provider_config_id,
            brainstorm_id=run.brainstorm_id,
            run_mode=run.run_mode,
            status="queued",
            model_name=run.model_name,
            attempt_number=next_retry_numbers(run.retry_count, run.attempt_number)[1],
            retry_count=next_retry_numbers(run.retry_count, run.attempt_number)[0],
            input_payload_json=run.input_payload_json,
        )
        task = await self.db.get(OrchestratorTask, new_run.task_id) if new_run.task_id else None
        if task:
            await self._transition_task_status(task, "queued", run=new_run, reason="retry queued")
        await self._emit_run_event(
            new_run,
            event_type="retry_queued",
            message=f"Retry created from run {run.id}.",
            payload={"previous_run_id": run.id},
        )
        await self.db.commit()
        from backend.modules.orchestration.execution.durable_execution import (
            submit_orchestration_run,
        )

        submit_orchestration_run(new_run.id, expected_owner_id=project.owner_id)
        await self.db.refresh(new_run)
        return new_run
    async def recover_stale_in_progress_runs(self, *, limit: int = 100) -> int:
        """Mark stuck in_progress runs as failed so they become claimable again.

        Soft/hard worker kills can leave runs in ``in_progress`` after the early status commit.
        """
        from datetime import UTC, datetime, timedelta

        stale_after = max(60, int(settings.ORCHESTRATION_STALE_IN_PROGRESS_SECONDS))
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_after)
        runs = await self.repo.list_stale_in_progress_runs(cutoff, limit=limit)
        recovered = 0
        for run in runs:
            run.status = "failed"
            run.error_message = (
                run.error_message
                or f"Recovered stale in_progress run (no heartbeat for >{stale_after}s)."
            )
            run.completed_at = datetime.now(UTC)
            await self._emit_run_event(
                run,
                event_type="workflow_recovery",
                level="warning",
                message="Stale in_progress run marked failed for reclaim.",
                payload={"stale_after_seconds": stale_after, "started_at": str(run.started_at)},
            )
            recovered += 1
        if recovered:
            await self.db.commit()
            logger.warning("stale_in_progress_recovered count=%s cutoff=%s", recovered, cutoff.isoformat())
        return recovered
    async def execute_run(self, run_id: str, *, expected_owner_id: str | None = None) -> TaskRun:
        logger.info("execute_run_start run_id=%s", run_id)
        run = await self.repo.get_run_for_worker(run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} not found")
        if run.status == "cancelled":
            logger.info("execute_run_cancelled run_id=%s", run_id)
            return run
        if not is_run_execution_claimable(run.status):
            logger.info(
                "execute_run_duplicate_delivery_ignored run_id=%s status=%s", run_id, run.status
            )
            return run
        logger.info(
            "execute_run_active run_id=%s status=%s run_mode=%s", run_id, run.status, run.run_mode
        )
        prior_status = run.status
        workflow = self._ensure_run_workflow(run)
        run.status = "in_progress"
        run.started_at = datetime.now(UTC)
        run.checkpoint_json = {
            **(run.checkpoint_json or {}),
            EXECUTION_THREAD_ID_KEY: run.id,
        }
        run.checkpoint_json, consumed_signals = consume_signal_queue(run.checkpoint_json)
        run.checkpoint_json = update_query_snapshot(
            run.checkpoint_json,
            data={
                "run_id": run.id,
                "project_id": run.project_id,
                "run_mode": run.run_mode,
                "worker_agent_id": run.worker_agent_id,
                "orchestrator_agent_id": run.orchestrator_agent_id,
                "latest_status": "in_progress",
                "signal_count": len(consumed_signals),
            },
        )
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError(f"Project {run.project_id} not found")
        if expected_owner_id is not None and project.owner_id != expected_owner_id:
            raise RuntimeError(
                f"Run {run_id} owner mismatch: expected {expected_owner_id}, got {project.owner_id}"
            )
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_token_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.worker_agent_id
        )
        await self._enforce_agent_cost_budget(
            owner_id=project.owner_id, agent_id=run.orchestrator_agent_id
        )
        # Task "planned" = accepted for execution but workflow not started yet. We keep it until after
        # run setup so the UI can show planned instead of jumping queued → in_progress in one tick.
        if task is not None and task.status == "queued":
            await self._transition_task_status(
                task, "planned", run=run, reason="execution planning"
            )
        await self._emit_run_event(
            run,
            event_type="started",
            message="Run execution started.",
            payload={
                "run_mode": run.run_mode,
                "durable_backend": workflow.get("backend"),
                "trace": self._workflow_trace_payload(run),
            },
        )
        if prior_status in {"failed", "blocked"}:
            await self._emit_run_event(
                run,
                event_type="workflow_recovery",
                message="Worker resumed execution from checkpoint after a recoverable interruption.",
                payload={"prior_status": prior_status, "trace": self._workflow_trace_payload(run)},
            )
        if consumed_signals:
            await self._emit_run_event(
                run,
                event_type="workflow_signal_applied",
                message=f"Applied {len(consumed_signals)} queued workflow signal(s).",
                payload={"signals": consumed_signals},
            )

        try:
            await self._compress_run_context_if_needed(run)
            if task is not None and task.status in {"planned", "blocked"}:
                await self._transition_task_status(
                    task, "in_progress", run=run, reason="execution started"
                )
            if run.run_mode == "brainstorm":
                await self._execute_brainstorm_run(run)
            elif run.run_mode == "review":
                await self._execute_review_run(run)
            elif run.run_mode == "debate":
                await self._execute_debate_run(run)
            elif run.run_mode == "manager_worker":
                await self._execute_manager_worker_run(run)
            else:
                await self._execute_single_agent_run(run)

            await self._enforce_run_output_schema(run)
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            try:
                from backend.modules.orchestration.skill_evaluation_hooks import (
                    record_skill_usage_for_run,
                )

                agent_id = (
                    getattr(run, "worker_agent_id", None)
                    or getattr(run, "agent_id", None)
                    or (task.assigned_agent_id if task else None)
                )
                latency_ms = None
                if run.started_at and run.completed_at:
                    latency_ms = int((run.completed_at - run.started_at).total_seconds() * 1000)
                await record_skill_usage_for_run(
                    self.db,
                    agent_id=agent_id,
                    task_id=run.task_id,
                    run_id=run.id,
                    success=True,
                    latency_ms=latency_ms,
                    notes="auto-recorded on run completion",
                    used_skill_version_ids=(
                        (run.checkpoint_json or {})
                        .get("skill_version_snapshot", {})
                        .get("skill_version_ids")
                    ),
                    run=run,
                )
            except Exception:
                pass
            run.checkpoint_json = set_workflow_artifact(
                mark_step(
                    run.checkpoint_json,
                    step_id=self._workflow_steps_for_run(run)[-1]["id"],
                    status="completed",
                ),
                key="final_status",
                value="completed",
            )
            run.checkpoint_json = update_query_snapshot(
                run.checkpoint_json,
                data={
                    "latest_status": "completed",
                    "completed_at": run.completed_at.isoformat(),
                    "task_id": run.task_id,
                },
            )
            if task and run.run_mode != "brainstorm":
                task.result_summary = (
                    str(
                        run.output_payload_json.get("summary")
                        or run.output_payload_json.get("final_output")
                        or ""
                    )[:2000]
                    or task.result_summary
                )
                if task.status not in {"blocked", "approved", "completed", "needs_review"}:
                    next_status = "needs_review" if task.reviewer_agent_id else "completed"
                    await self._transition_task_status(
                        task, next_status, run=run, reason="run completed"
                    )
                elif run.run_mode == "manager_worker" and task.status == "approved":
                    await self._transition_task_status(
                        task, "completed", run=run, reason="manager-worker flow fully completed"
                    )
                self._update_task_execution_memory(task, run)
                await self._detect_and_log_task_output_conflict(task, run)
            await self._emit_run_event(
                run,
                event_type="completed",
                message="Run completed successfully.",
                payload=run.output_payload_json,
            )
            await self._persist_agent_memory_from_run(
                run,
                await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id),
                task,
            )
            await self._apply_run_completion_external_actions(run, task)
            await self.db.commit()
            try:
                from backend.modules.workforce.services.workflow_hooks import on_task_run_terminal

                await on_task_run_terminal(self.db, run.id, status="completed")
            except Exception:
                logger.exception("workflow_task_run_terminal_hook_failed run_id=%s", run.id)
            if task and task.status in {"completed", "archived", "synced_to_github"}:
                await self.db.refresh(task)
                hook_user = None
                if run.triggered_by_user_id:
                    hook_user = await self.db.get(User, run.triggered_by_user_id)
                if hook_user:
                    await self._maybe_promote_task_close_working_memory(hook_user, project, task)
                await self._run_task_close_memory_lifecycle(hook_user, project, task)
                await self._enqueue_classifier_job_for_task(project, task)
            if task:
                await self._apply_project_escalation_rules(
                    project, run=run, task=task, trigger="run_completed"
                )
            return run
        except BlockedExecution as exc:
            run.status = "blocked"
            run.error_message = str(exc)
            step = current_step(run.checkpoint_json)
            if step:
                await self._mark_run_step(
                    run,
                    step_id=str(step.get("id")),
                    status="blocked",
                    level="warning",
                    message=f"Checkpoint captured at blocked step '{step.get('title')}'.",
                    error=str(exc),
                )
            if task:
                await self._transition_task_status(task, "blocked", run=run, reason=str(exc))
            await self._emit_run_event(
                run,
                event_type="blocked",
                level="warning",
                message=str(exc),
            )
            run.checkpoint_json = update_query_snapshot(
                run.checkpoint_json,
                data={"latest_status": "blocked", "last_error": str(exc), "task_id": run.task_id},
            )
            await self.db.commit()
            try:
                from backend.modules.orchestration.skill_evaluation_hooks import (
                    safe_record_skill_usage_for_run,
                )

                agent_id = (
                    getattr(run, "worker_agent_id", None)
                    or getattr(run, "agent_id", None)
                    or (task.assigned_agent_id if task else None)
                )
                await safe_record_skill_usage_for_run(
                    self.db,
                    run=run,
                    agent_id=agent_id,
                    success=False,
                    notes=f"auto-recorded on run blocked: {exc}",
                    task=task,
                )
            except Exception:
                logger.exception("skill_evaluation_hook_failed run_id=%s", run.id)
            if task:
                await self._apply_project_escalation_rules(
                    project, run=run, task=task, trigger="task_blocked"
                )
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            step = current_step(run.checkpoint_json)
            if step:
                await self._mark_run_step(
                    run,
                    step_id=str(step.get("id")),
                    status="failed",
                    level="error",
                    message=f"Failure captured for step '{step.get('title')}'.",
                    error=str(exc),
                )
            if task and task.status != "blocked":
                await self._transition_task_status(task, "failed", run=run, reason=str(exc))
            await self._emit_run_event(
                run,
                event_type="failed",
                level="error",
                message=str(exc),
            )
            run.checkpoint_json = update_query_snapshot(
                run.checkpoint_json,
                data={"latest_status": "failed", "last_error": str(exc), "task_id": run.task_id},
            )
            await self.db.commit()
            try:
                from backend.modules.orchestration.skill_evaluation_hooks import (
                    safe_record_skill_usage_for_run,
                )

                agent_id = (
                    getattr(run, "worker_agent_id", None)
                    or getattr(run, "agent_id", None)
                    or (task.assigned_agent_id if task else None)
                )
                await safe_record_skill_usage_for_run(
                    self.db,
                    run=run,
                    agent_id=agent_id,
                    success=False,
                    notes=f"auto-recorded on run failure: {exc}",
                    task=task,
                )
            except Exception:
                logger.exception("skill_evaluation_hook_failed run_id=%s", run.id)
            try:
                from backend.modules.workforce.services.workflow_hooks import on_task_run_terminal

                await on_task_run_terminal(self.db, run.id, status="failed")
            except Exception:
                logger.exception("workflow_task_run_terminal_hook_failed run_id=%s", run.id)
            if task:
                await self._apply_project_escalation_rules(
                    project, run=run, task=task, trigger="run_failed"
                )
            return run

