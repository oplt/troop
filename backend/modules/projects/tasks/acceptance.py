"""Task acceptance checks and output validation."""

from __future__ import annotations

import json
from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorTask
from backend.modules.projects.task_acceptance import (
    acceptance_criteria_items,
    acceptance_evidence_excerpt,
    acceptance_item_check,
    acceptance_item_matches_output,
    task_output_text,
)


class TaskAcceptanceMixin:
    async def check_task_acceptance(self, user: User, project_id: str, task_id: str) -> dict:
        task = await self.get_task(user, project_id, task_id)
        return await self._check_task_acceptance_payload(task)

    def _task_acceptance_checker_config(self, task: OrchestratorTask | Any) -> dict[str, Any]:
        meta = dict(getattr(task, "metadata_json", None) or {})
        raw = meta.get("acceptance_checker")
        config = raw if isinstance(raw, dict) else {}
        required_artifact_kinds = config.get("required_artifact_kinds")
        return {
            "required_artifact_kinds": [
                str(item).strip()
                for item in (
                    required_artifact_kinds if isinstance(required_artifact_kinds, list) else []
                )
                if str(item).strip()
            ],
            "require_github_comment": bool(config.get("require_github_comment", False)),
            "require_github_pr": bool(config.get("require_github_pr", False)),
            "require_reviewer_approval": bool(config.get("require_reviewer_approval", False)),
        }

    async def _check_task_acceptance_payload(self, task: OrchestratorTask) -> dict:
        checks: list[dict] = []
        config = self._task_acceptance_checker_config(task)

        output_text = self._task_output_text(task)
        has_output = bool(output_text.strip())
        checks.append(
            {
                "name": "has_output",
                "passed": has_output,
                "detail": "Task has output summary or payload"
                if has_output
                else "No task output yet",
            }
        )

        valid_statuses = {"completed", "needs_review"}
        in_valid_status = task.status in valid_statuses
        checks.append(
            {
                "name": "valid_status",
                "passed": in_valid_status,
                "detail": f"Status is '{task.status}'"
                if in_valid_status
                else f"Status '{task.status}' is not a terminal state",
            }
        )
        checks.append(await self._acceptance_output_schema_check(task, output_text))

        dep_rows = await self.repo.list_task_dependencies_for_task(task.id)
        if dep_rows:
            incomplete_count = 0
            for dep in dep_rows:
                dep_task = await self.repo.get_task_by_id(dep.depends_on_task_id)
                if dep_task and dep_task.status not in {"completed", "approved"}:
                    incomplete_count += 1
            deps_done = incomplete_count == 0
            checks.append(
                {
                    "name": "dependencies_complete",
                    "passed": deps_done,
                    "detail": "All dependencies completed"
                    if deps_done
                    else f"{incomplete_count} dependencies not yet complete",
                }
            )
        else:
            checks.append(
                {"name": "dependencies_complete", "passed": True, "detail": "No dependencies"}
            )

        criteria_items = self._acceptance_criteria_items(task.acceptance_criteria or "")
        if criteria_items:
            item_checks = [
                self._acceptance_item_check(item, output_text) for item in criteria_items
            ]
            missing = [item["item"] for item in item_checks if not item["passed"]]
            checks.append(
                {
                    "name": "acceptance_criteria",
                    "passed": len(missing) == 0,
                    "detail": "All acceptance criteria matched output."
                    if not missing
                    else f"Missing acceptance evidence for {len(missing)} item(s): {', '.join(missing[:3])}",
                    "items": item_checks,
                }
            )
        else:
            checks.append(
                {
                    "name": "acceptance_criteria",
                    "passed": False,
                    "detail": "No acceptance criteria defined.",
                    "items": [],
                }
            )

        if (getattr(task, "metadata_json", None) or {}).get("latest_reopen"):
            checks.append(
                {
                    "name": "reopen_items_resolved",
                    "passed": False,
                    "detail": "Latest review requested rework; rerun after addressing checklist items.",
                }
            )
        else:
            checks.append(
                {
                    "name": "reopen_items_resolved",
                    "passed": True,
                    "detail": "No outstanding rework checklist.",
                }
            )

        list_task_artifacts = getattr(self.repo, "list_task_artifacts", None)
        artifacts = await list_task_artifacts(task.id) if callable(list_task_artifacts) else []
        present_artifact_kinds = sorted(
            {
                str(getattr(item, "kind", "") or "").strip()
                for item in artifacts
                if str(getattr(item, "kind", "") or "").strip()
            }
        )
        if config["required_artifact_kinds"]:
            missing = [
                kind
                for kind in config["required_artifact_kinds"]
                if kind not in present_artifact_kinds
            ]
            checks.append(
                {
                    "name": "required_artifacts",
                    "passed": len(missing) == 0,
                    "detail": "All required artifact kinds are present."
                    if not missing
                    else f"Missing required artifact kinds: {', '.join(missing)}",
                    "required_artifact_kinds": config["required_artifact_kinds"],
                    "present_artifact_kinds": present_artifact_kinds,
                }
            )

        list_sync_events_for_task = getattr(self.repo, "list_sync_events_for_task", None)
        sync_events = (
            await list_sync_events_for_task(task.id) if callable(list_sync_events_for_task) else []
        )
        if config["require_github_comment"]:
            has_comment = any(
                "comment" in str(getattr(event, "action", "") or "").lower()
                and str(getattr(event, "status", "") or "").lower()
                in {"completed", "sent", "success", "approved"}
                for event in sync_events
            )
            checks.append(
                {
                    "name": "github_comment",
                    "passed": has_comment,
                    "detail": "GitHub comment evidence found."
                    if has_comment
                    else "Required GitHub comment evidence was not found.",
                }
            )

        if config["require_github_pr"]:
            has_pr = any(
                (
                    "pull_request" in str(getattr(event, "action", "") or "").lower()
                    or "create_pr" in str(getattr(event, "action", "") or "").lower()
                )
                and str(getattr(event, "status", "") or "").lower()
                in {"completed", "sent", "success", "approved"}
                for event in sync_events
            )
            checks.append(
                {
                    "name": "github_pr",
                    "passed": has_pr,
                    "detail": "GitHub PR evidence found."
                    if has_pr
                    else "Required GitHub PR evidence was not found.",
                }
            )

        if config["require_reviewer_approval"]:
            reviewer_ok = task.status in {"approved", "completed", "synced_to_github"} or bool(
                getattr(task, "approved_by_user_id", None)
            )
            checks.append(
                {
                    "name": "reviewer_approval",
                    "passed": reviewer_ok,
                    "detail": "Reviewer approval recorded."
                    if reviewer_ok
                    else "Reviewer approval is required before completion.",
                }
            )

        return {
            "task_id": task.id,
            "passed": all(c["passed"] for c in checks),
            "config": config,
            "checks": checks,
        }

    def _task_output_text(self, task: OrchestratorTask | Any) -> str:
        return task_output_text(
            result_summary=getattr(task, "result_summary", None),
            result_payload_json=getattr(task, "result_payload_json", None),
        )

    def _acceptance_criteria_items(self, text: str) -> list[str]:
        return acceptance_criteria_items(text)

    def _acceptance_item_matches_output(self, item: str, output_text: str) -> bool:
        return acceptance_item_matches_output(item, output_text)

    def _acceptance_item_check(self, item: str, output_text: str) -> dict[str, Any]:
        return acceptance_item_check(item, output_text)

    async def _acceptance_output_schema_check(
        self, task: OrchestratorTask, output_text: str
    ) -> dict[str, Any]:
        assigned_agent_id = str(getattr(task, "assigned_agent_id", None) or "").strip()
        if not assigned_agent_id:
            return {
                "name": "output_schema",
                "passed": True,
                "detail": "No assigned agent schema configured.",
            }
        get_agent = getattr(self.repo, "get_agent", None)
        agent = (
            await get_agent(task.created_by_user_id, assigned_agent_id)
            if callable(get_agent)
            else None
        )
        schema = dict(getattr(agent, "output_schema_json", None) or {}) if agent else {}
        fmt = str(schema.get("format") or "").strip().lower()
        if not fmt:
            return {
                "name": "output_schema",
                "passed": True,
                "detail": "No output schema configured.",
            }
        payload = getattr(task, "result_payload_json", None) or {}
        valid = bool(output_text.strip())
        if fmt == "json":
            structured = (
                payload.get("structured_output_json") if isinstance(payload, dict) else None
            )
            if not isinstance(structured, (dict, list)):
                try:
                    json.loads(
                        str(payload.get("final_output") or payload.get("summary") or output_text)
                    )
                except (TypeError, ValueError, json.JSONDecodeError):
                    valid = False
        elif fmt == "checklist":
            valid = valid and ("- " in output_text or "1." in output_text)
        elif fmt == "adr":
            lowered = output_text.lower()
            valid = valid and "decision" in lowered and "context" in lowered
        elif fmt == "patch_proposal":
            lowered = output_text.lower()
            valid = valid and "file" in lowered and "test" in lowered
        elif fmt == "issue_reply":
            lowered = output_text.lower()
            valid = valid and ("finding" in lowered or "review" in lowered)
        else:
            valid = False
        return {
            "name": "output_schema",
            "passed": valid,
            "detail": f"Output matches '{fmt}' schema."
            if valid
            else f"Output does not match '{fmt}' schema.",
            "format": fmt,
        }

    def _acceptance_evidence_excerpt(self, item: str, output_text: str) -> str:
        return acceptance_evidence_excerpt(item, output_text)
