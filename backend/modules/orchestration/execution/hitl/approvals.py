"""HITL escalations, reviewer chains, and conflict detection."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import attributes as orm_attributes

from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


class ExecutionHitlApprovalsMixin:
    async def _detect_and_log_task_output_conflict(
        self, task: OrchestratorTask, run: TaskRun
    ) -> None:
        if not task.id:
            return
        all_runs = await self.repo.list_runs(task.created_by_user_id, task.project_id)
        related = [
            r
            for r in all_runs
            if r.task_id == task.id and r.id != run.id and r.status == "completed"
        ]
        if not related:
            return
        current = str(
            (run.output_payload_json or {}).get("final_output")
            or (run.output_payload_json or {}).get("summary")
            or ""
        ).strip()
        if not current:
            return
        previous = str(
            (related[-1].output_payload_json or {}).get("final_output")
            or (related[-1].output_payload_json or {}).get("summary")
            or ""
        ).strip()
        if not previous:
            return
        contradict = ("approve" in current.lower() and "reject" in previous.lower()) or (
            "reject" in current.lower() and "approve" in previous.lower()
        )
        if not contradict:
            return
        await self.repo.create_approval(
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            issue_link_id=task.github_issue_link_id,
            requested_by_user_id=run.triggered_by_user_id,
            approval_type="output_conflict_resolution",
            status="pending",
            payload_json={
                "current_run_id": run.id,
                "previous_run_id": related[-1].id,
                "current_summary": current[:500],
                "previous_summary": previous[:500],
            },
        )
        await self._transition_task_status(
            task, "blocked", run=run, reason="conflicting agent outputs require resolution"
        )

    async def _advance_task_reviewer_chain(
        self,
        task: OrchestratorTask,
        project: OrchestratorProject | None,
        reviewer_agent_id: str | None,
    ) -> bool:
        chain = self._reviewer_chain_for_project(project)
        if not chain or not reviewer_agent_id:
            return False
        try:
            current_index = chain.index(str(reviewer_agent_id))
        except ValueError:
            return False
        if current_index >= len(chain) - 1:
            return False
        next_reviewer_id = chain[current_index + 1]
        metadata = dict(task.metadata_json or {})
        metadata["review_chain"] = {
            "reviewer_agent_ids": chain,
            "current_index": current_index + 1,
            "last_completed_reviewer_agent_id": reviewer_agent_id,
        }
        task.metadata_json = metadata
        task.reviewer_agent_id = next_reviewer_id
        if hasattr(task, "_sa_instance_state"):
            orm_attributes.flag_modified(task, "metadata_json")
        return True

    async def _apply_project_escalation_rules(
        self,
        project: OrchestratorProject,
        *,
        run: TaskRun,
        task: OrchestratorTask,
        trigger: str,
        rounds_completed: int | None = None,
        consensus_reached: bool | None = None,
    ) -> None:
        rules = self._project_execution_settings(project).get("escalation_rules", [])
        if not isinstance(rules, list):
            return
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            escalate_to = rule.get("escalate_to") or self._project_execution_settings(project).get(
                "manager_agent_id"
            )
            condition = rule.get("condition")
            if condition == "stuck_for_minutes" and trigger in {"task_blocked", "run_failed"}:
                threshold = int(rule.get("value", 0) or 0)
                if threshold <= 0:
                    continue
                started_at = run.started_at or run.created_at
                elapsed_minutes = int((datetime.now(UTC) - started_at).total_seconds() / 60)
                if elapsed_minutes >= threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={
                            "condition": condition,
                            "value": threshold,
                            "elapsed_minutes": elapsed_minutes,
                            "escalate_to": escalate_to,
                        },
                    )
            if condition == "cost_exceeds_usd" and trigger == "run_completed":
                threshold = float(rule.get("value", 0) or 0)
                cost_usd = run.estimated_cost_micros / 1_000_000
                if threshold > 0 and cost_usd > threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={
                            "condition": condition,
                            "value": threshold,
                            "cost_usd": cost_usd,
                            "escalate_to": escalate_to,
                        },
                    )
            if condition == "no_consensus_after_rounds" and trigger == "brainstorm_finished":
                threshold = int(rule.get("value", 0) or 0)
                if (
                    threshold > 0
                    and consensus_reached is False
                    and (rounds_completed or 0) >= threshold
                ):
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={
                            "condition": condition,
                            "value": threshold,
                            "rounds_completed": rounds_completed,
                            "escalate_to": escalate_to,
                        },
                    )
        await self.db.commit()

    async def _escalate_blocker(
        self,
        run: TaskRun,
        *,
        task: OrchestratorTask | None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        escalate_to_agent_id = run.orchestrator_agent_id or task.reviewer_agent_id if task else None
        await self.repo.create_approval(
            project_id=run.project_id,
            task_id=task.id if task else None,
            run_id=run.id,
            requested_by_user_id=run.triggered_by_user_id,
            approval_type="task_escalation",
            status="pending",
            payload_json={
                "reason": reason,
                "escalate_to_agent_id": escalate_to_agent_id,
                "metadata": metadata or {},
            },
        )
        await self.db.commit()
