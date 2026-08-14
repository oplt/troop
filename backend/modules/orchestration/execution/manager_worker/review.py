"""Standalone and inline manager-worker review runs."""

from __future__ import annotations

import json
from datetime import UTC, datetime

from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorTask


class ManagerWorkerReviewMixin:
    async def _execute_review_run(self, run: TaskRun) -> None:
        reviewer = await self._load_agent_for_run(run.reviewer_agent_id or run.worker_agent_id)
        provider = await self._resolve_provider_for_run(run, reviewer)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        await self._mark_run_step(
            run,
            step_id="review",
            status="in_progress",
            message="Reviewer is evaluating the task result.",
        )
        gh_review = (run.input_payload_json or {}).get("github_pr_review")
        extra_ctx = ""
        if isinstance(gh_review, dict):
            extra_ctx = (
                "\n\nExternal GitHub PR review context:\n"
                f"State: {gh_review.get('state')}\n"
                f"Author: {gh_review.get('author_login')}\n"
                f"Body:\n{gh_review.get('body') or ''}\n"
            )
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=reviewer,
            system_prompt=(reviewer.system_prompt if reviewer else "You are a careful reviewer."),
            user_prompt=(
                "Review this task result and return a single JSON object with:\n"
                '- decision: "approved" or "rework"\n'
                "- summary: short string\n"
                "- reasons: array of strings (each a concrete issue or gap)\n"
                "- checklist: array of actionable strings the worker must verify before resubmitting\n\n"
                f"Task title: {task.title if task else 'Unknown'}\n"
                f"Task summary: {task.result_summary if task else ''}\n"
                f"Acceptance criteria: {task.acceptance_criteria if task else ''}\n"
                f"Latest structured reopen (if any): {json.dumps((task.metadata_json or {}).get('latest_reopen'), default=str) if task else {}}"
                f"{extra_ctx}"
            ),
            response_format="json",
            purpose="review",
        )
        review_payload = (
            result.output_json
            if isinstance(result.output_json, dict) and result.output_json.get("decision")
            else self._coerce_review_payload(result.output_text)
        )
        run.output_payload_json = {
            "summary": str(review_payload.get("summary") or result.output_text)[:1200],
            "review": result.output_text,
            "decision": review_payload.get("decision"),
        }
        await self._mark_run_step(
            run,
            step_id="review",
            status="completed",
            message="Reviewer produced a structured verdict.",
        )
        if task:
            if review_payload.get("decision") == "approved":
                project = await self.db.get(OrchestratorProject, task.project_id)
                advanced = await self._advance_task_reviewer_chain(
                    task, project, run.reviewer_agent_id
                )
                if advanced:
                    run.output_payload_json["next_reviewer_agent_id"] = task.reviewer_agent_id
                    await self._emit_run_event(
                        run,
                        event_type="review_handoff",
                        message="Review approved and handed off to the next reviewer in chain.",
                        payload={"next_reviewer_agent_id": task.reviewer_agent_id},
                    )
                else:
                    await self._transition_task_status(
                        task, "approved", run=run, reason="review approved"
                    )
            else:
                self._append_structured_reopen_record(task, review_payload, run=run)
                await self._transition_task_status(
                    task, "planned", run=run, reason="review requested rework"
                )
                await self._emit_run_event(
                    run,
                    event_type="reopened",
                    level="warning",
                    message="Task reopened for rework after review (structured checklist recorded).",
                    payload=review_payload,
                )
            await self._post_reviewer_pr_comment(
                run,
                task,
                str(review_payload.get("summary") or result.output_text),
            )
            await self._mark_run_step(
                run,
                step_id="artifact_publish",
                status="in_progress",
                message="Publishing review artifacts.",
            )
            await self._write_artifact(
                run,
                kind="review",
                title="Review verdict",
                content=json.dumps(review_payload, indent=2, default=str),
                metadata={"task_id": task.id},
            )
            await self._mark_run_step(
                run,
                step_id="artifact_publish",
                status="completed",
                message="Review artifacts published.",
            )
            await self._run_review_external_action_sync(run, task)
