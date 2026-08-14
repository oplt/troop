"""GitHub and other external action sync stages during run execution."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from backend.modules.orchestration.execution.result_contracts import EXTERNAL_ACTION_STEP_ID
from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask

LEGACY_STEP_ALIASES = {"github_sync": EXTERNAL_ACTION_STEP_ID}


def normalize_workflow_step_id(step_id: str) -> str:
    return LEGACY_STEP_ALIASES.get(step_id, step_id)


def external_action_workflow_step() -> dict[str, Any]:
    return {
        "id": EXTERNAL_ACTION_STEP_ID,
        "title": "External action sync",
        "actor": "system",
        "specialization": "github",
    }


class ExecutionExternalActionsMixin:
    def _normalize_workflow_step_id(self, step_id: str) -> str:
        return normalize_workflow_step_id(step_id)

    def _github_action_already_completed(self, run: TaskRun) -> bool:
        state = run.output_payload_json.get("github_action_state")
        return isinstance(state, dict) and bool(state.get("completed"))

    async def _run_manager_worker_external_action_sync(
        self, run: TaskRun, task: OrchestratorTask | None
    ) -> None:
        await self._mark_run_step(
            run,
            step_id=EXTERNAL_ACTION_STEP_ID,
            status="in_progress",
            message="Syncing approved result to GitHub policy layer.",
        )
        if task:
            github_state = await self._sync_manager_run_to_github(run, task)
            run.output_payload_json["github_action_state"] = github_state
        await self._mark_run_step(
            run,
            step_id=EXTERNAL_ACTION_STEP_ID,
            status="completed",
            message="GitHub sync stage completed.",
        )

    async def _run_review_external_action_sync(self, run: TaskRun, task: OrchestratorTask) -> None:
        await self._mark_run_step(
            run,
            step_id=EXTERNAL_ACTION_STEP_ID,
            status="in_progress",
            message="Applying GitHub review automation.",
        )
        await self._sync_run_completion_to_github(run, task)
        run.output_payload_json["github_action_state"] = {
            "completed": True,
            "last_synced_at": datetime.now(UTC).isoformat(),
            "mode": "review",
        }
        await self._mark_run_step(
            run,
            step_id=EXTERNAL_ACTION_STEP_ID,
            status="completed",
            message="GitHub review automation completed.",
        )

    async def _apply_run_completion_external_actions(
        self, run: TaskRun, task: OrchestratorTask | None
    ) -> None:
        if task and not self._github_action_already_completed(run):
            await self._sync_run_completion_to_github(run, task)
        if task and task.github_issue_link_id and run.run_mode != "brainstorm":
            await self.repo.create_approval(
                project_id=run.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=task.github_issue_link_id,
                requested_by_user_id=run.triggered_by_user_id,
                approval_type="github_comment",
                status="pending",
                payload_json={
                    "draft_comment": task.result_summary or "Task completed.",
                    "close_issue": False,
                },
            )
