"""Task CRUD, comments, timeline, subtasks, and incident ingestion."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException
from sqlalchemy.orm import attributes as orm_attributes

from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import _normalize_task_priority
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


class TaskCrudMixin:
    async def list_tasks(self, user: User, project_id: str, *, limit: int | None = None):
        await self.get_project(user, project_id)
        return await self.repo.list_tasks(project_id, limit=limit)

    async def get_task(self, user: User, project_id: str, task_id: str):
        await self.get_project(user, project_id)
        task = await self.repo.get_task(project_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    async def create_task(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        if payload.get("assigned_agent_id"):
            await self._ensure_project_agent_member(
                user, project.id, payload["assigned_agent_id"], "Owner"
            )
        if payload.get("reviewer_agent_id"):
            await self._ensure_project_agent_member(
                user, project.id, payload["reviewer_agent_id"], "Reviewer"
            )
        metadata = self._normalized_task_metadata(
            payload.get("metadata"),
            required_tools=payload.get("required_tools"),
            external_links=payload.get("external_links"),
        )
        position = await self.repo.get_next_task_position(project.id)
        task = await self.repo.create_task(
            project_id=project.id,
            created_by_user_id=user.id,
            assigned_agent_id=payload.get("assigned_agent_id"),
            reviewer_agent_id=payload.get("reviewer_agent_id"),
            title=payload["title"],
            description=payload.get("description"),
            source=payload.get("source", "manual"),
            task_type=payload.get("task_type", "general"),
            priority=_normalize_task_priority(payload.get("priority")),
            status=payload.get("status", "queued"),
            acceptance_criteria=payload.get("acceptance_criteria"),
            due_date=payload.get("due_date"),
            response_sla_hours=payload.get("response_sla_hours"),
            labels_json=payload.get("labels", []),
            result_summary=payload.get("result_summary"),
            result_payload_json=payload.get("result_payload", {}),
            metadata_json=metadata,
            position=position,
        )
        dependency_ids = list(payload.get("dependency_ids", []) or [])
        await self._validate_task_dependencies(project.id, task.id, dependency_ids)
        await self.repo.replace_task_dependencies(task.id, dependency_ids)
        await self._sync_knowledge_graph_for_task(project, task)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task(
        self,
        user: User,
        project_id: str,
        task_id: str,
        updates: dict[str, Any],
        *,
        assignment_source: str = "manual_update",
    ):
        task = await self.get_task(user, project_id, task_id)
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if (
            "assigned_agent_id" in updates
            and updates.get("assigned_agent_id") != task.assigned_agent_id
            and self.action_requires_approval(project, "change_task_ownership")
        ):
            approval = await self.repo.create_approval(
                project_id=project.id,
                task_id=task.id,
                run_id=None,
                issue_link_id=task.github_issue_link_id,
                requested_by_user_id=user.id,
                approval_type="task_assignment_change",
                status="pending",
                payload_json={
                    "task_id": task.id,
                    "from_assigned_agent_id": task.assigned_agent_id,
                    "to_assigned_agent_id": updates.get("assigned_agent_id"),
                },
            )
            await self.db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Changing task ownership requires approval.",
                    "approval_id": approval.id,
                },
            )
        if (
            "status" in updates
            and updates.get("status") in {"completed", "approved"}
            and self.action_requires_approval(project, "mark_complete")
        ):
            approval = await self.repo.create_approval(
                project_id=project.id,
                task_id=task.id,
                run_id=None,
                issue_link_id=task.github_issue_link_id,
                requested_by_user_id=user.id,
                approval_type="task_mark_complete",
                status="pending",
                payload_json={
                    "task_id": task.id,
                    "from_status": task.status,
                    "to_status": updates.get("status"),
                },
            )
            await self.db.commit()
            raise HTTPException(
                status_code=409,
                detail={
                    "message": "Marking tasks complete requires approval.",
                    "approval_id": approval.id,
                },
            )
        prev_snapshot = {
            "status": task.status,
            "assigned_agent_id": getattr(task, "assigned_agent_id", None),
            "labels": list(getattr(task, "labels_json", None) or []),
            "metadata": dict(getattr(task, "metadata_json", None) or {}),
        }
        prev_status = task.status
        if "assigned_agent_id" in updates and updates["assigned_agent_id"]:
            await self._ensure_project_agent_member(
                user, project.id, updates["assigned_agent_id"], "Owner"
            )
        if "reviewer_agent_id" in updates and updates["reviewer_agent_id"]:
            await self._ensure_project_agent_member(
                user, project.id, updates["reviewer_agent_id"], "Reviewer"
            )

        if "assigned_agent_id" in updates:
            next_meta = dict(task.metadata_json or {})
            assigned_agent_id = updates.get("assigned_agent_id")
            if assigned_agent_id:
                agent = await self.get_agent(user, assigned_agent_id)
                next_meta["routing_explainability"] = {
                    "agent_selection_reason": f"Task assigned to {agent.name} via {assignment_source.replace('_', ' ')}.",
                    "model_selection_reason": "",
                    "routing_inputs": {
                        "assignment_source": assignment_source,
                        "assigned_agent_id": assigned_agent_id,
                    },
                    "routing_policy_snapshot": {},
                    "agent_source": "manual_update",
                    "model_source": None,
                }
            else:
                next_meta.pop("routing_explainability", None)
            task.metadata_json = next_meta
            orm_attributes.flag_modified(task, "metadata_json")

        for field, value in updates.items():
            if field == "labels":
                task.labels_json = value
            elif field == "result_payload":
                task.result_payload_json = value
            elif field == "metadata":
                task.metadata_json = self._normalized_task_metadata(value)
            elif field == "required_tools":
                metadata = dict(task.metadata_json or {})
                metadata["required_tools"] = self._normalized_required_tools(value)
                task.metadata_json = self._normalized_task_metadata(metadata)
                orm_attributes.flag_modified(task, "metadata_json")
            elif field == "external_links":
                metadata = dict(task.metadata_json or {})
                metadata["external_links"] = self._normalized_external_links(value)
                task.metadata_json = self._normalized_task_metadata(metadata)
                orm_attributes.flag_modified(task, "metadata_json")
            elif field == "dependency_ids":
                dependency_ids = list(value or [])
                await self._validate_task_dependencies(project_id, task.id, dependency_ids)
                await self.repo.replace_task_dependencies(task.id, dependency_ids)
            elif field == "github_secondary_repository_ids":
                sec_ids = [str(x).strip() for x in (value or []) if str(x).strip()]
                await self._validate_github_secondary_repository_ids(user, project_id, sec_ids)
                metadata = dict(task.metadata_json or {})
                metadata["github_secondary_repository_ids"] = sec_ids
                task.metadata_json = metadata
                orm_attributes.flag_modified(task, "metadata_json")
            elif field == "status":
                if value in {"completed", "approved"}:
                    acceptance = await self._check_task_acceptance_payload(task)
                    if not acceptance["passed"]:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": "Acceptance checks must pass before the task can be marked done.",
                                "checks": acceptance["checks"],
                            },
                        )
                if value in {"synced_to_github", "archived"}:
                    evidence = await self._check_task_evidence_bundle_payload(
                        task, target_status=value
                    )
                    if not evidence["passed"]:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": f"Evidence bundle must be complete before moving to {value}.",
                                "checks": evidence["checks"],
                            },
                        )
                terminal = {"completed", "archived", "synced_to_github"}
                if prev_status in terminal and value not in terminal:
                    metadata = dict(task.metadata_json or {})
                    metadata.pop("memory_checkpoint_compacted", None)
                    metadata.pop("memory_low_value_archived", None)
                    task.metadata_json = metadata
                    orm_attributes.flag_modified(task, "metadata_json")
                await self._transition_task_status(task, value, reason="manual update")
            elif field == "priority":
                setattr(
                    task, field, _normalize_task_priority(str(value) if value is not None else None)
                )
            else:
                setattr(task, field, value)
        await self.db.commit()
        await self.db.refresh(task)
        await self._queue_task_github_sync_from_internal_changes(user, task, prev_snapshot)
        await self._sync_knowledge_graph_for_task(project, task)
        if prev_status != task.status and task.status in {
            "completed",
            "archived",
            "synced_to_github",
        }:
            await self._maybe_promote_task_close_working_memory(user, project, task)
            await self.db.refresh(task)
            await self._run_task_close_memory_lifecycle(user, project, task)
            await self._enqueue_classifier_job_for_task(project, task)
        await self.db.commit()
        return task

    async def delete_task(self, user: User, project_id: str, task_id: str):
        task = await self.get_task(user, project_id, task_id)
        await self.db.delete(task)
        await self.db.commit()

    async def list_task_comments(self, user: User, project_id: str, task_id: str):
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_task_comments(task_id)

    async def add_task_comment(self, user: User, project_id: str, task_id: str, body: str):
        await self.get_task(user, project_id, task_id)
        comment = await self.repo.create_task_comment(
            task_id=task_id, author_user_id=user.id, body=body
        )
        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def list_task_timeline(
        self, user: User, project_id: str, task_id: str
    ) -> list[dict[str, Any]]:
        await self.get_task(user, project_id, task_id)
        comments = await self.repo.list_task_comments(task_id)
        sync_events = await self.repo.list_sync_events_for_task(task_id)
        approvals = await self.repo.list_approvals_for_task(user.id, project_id, task_id)
        merged: list[dict[str, Any]] = []
        for comment in comments:
            merged.append(
                {
                    "kind": "comment",
                    "id": comment.id,
                    "created_at": comment.created_at,
                    "title": "Task comment",
                    "body": comment.body,
                    "detail": None,
                    "payload": {
                        "author_user_id": comment.author_user_id,
                        "author_agent_id": comment.author_agent_id,
                    },
                }
            )
        for approval in approvals:
            payload = dict(approval.payload_json or {})
            merged.append(
                {
                    "kind": "approval",
                    "id": approval.id,
                    "created_at": approval.created_at,
                    "title": approval.approval_type,
                    "body": payload.get("body") or payload.get("draft_comment"),
                    "detail": f"{approval.status} approval",
                    "payload": {
                        **payload,
                        "approval_status": approval.status,
                        "approval_type": approval.approval_type,
                    },
                }
            )
        for event in sync_events:
            merged.append(
                {
                    "kind": "github_sync",
                    "id": event.id,
                    "created_at": event.created_at,
                    "title": event.action,
                    "body": None,
                    "detail": event.detail,
                    "payload": event.payload_json or {},
                }
            )
        merged.sort(key=lambda row: row["created_at"])
        return merged

    async def list_subtasks(
        self, user: User, project_id: str, task_id: str
    ) -> list[OrchestratorTask]:
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_subtasks(task_id)

    async def decompose_task(
        self,
        user: User,
        project_id: str,
        task_id: str,
        max_subtasks: int = 5,
        context: str | None = None,
    ) -> list[OrchestratorTask]:
        parent = await self.get_task(user, project_id, task_id)
        project = await self.get_project(user, project_id)
        existing = await self.repo.list_subtasks(task_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Task already has subtasks. Update or archive the existing branch plan before decomposing again.",
            )
        blueprint = self._generate_subtask_blueprint(
            parent, max_subtasks=max_subtasks, context=context
        )
        subtasks = []
        for item in blueprint:
            position = await self.repo.get_next_task_position(project_id)
            task = await self.repo.create_task(
                project_id=project_id,
                created_by_user_id=user.id,
                title=str(item["title"]),
                description=str(item["description"]),
                source="decompose",
                task_type=parent.task_type,
                priority=parent.priority,
                status="backlog",
                parent_task_id=task_id,
                position=position,
                labels_json=list(item.get("labels") or []),
                result_payload_json={},
                metadata_json={
                    "parallelizable": bool(item.get("parallelizable", False)),
                    "required_tools": list(item.get("required_tools") or []),
                    "blueprint_kind": item.get("kind"),
                },
                acceptance_criteria=item.get("acceptance_criteria"),
            )
            subtasks.append(task)
        for index, task in enumerate(subtasks):
            dependency_indexes = list(blueprint[index].get("dependency_indexes") or [])
            dependency_ids = [
                subtasks[dep_index].id
                for dep_index in dependency_indexes
                if 0 <= dep_index < len(subtasks)
            ]
            await self.repo.replace_task_dependencies(task.id, dependency_ids)
        await self.db.commit()
        for subtask in subtasks:
            await self.db.refresh(subtask)
            await self._sync_knowledge_graph_for_task(project, subtask)
        await self.db.commit()
        return subtasks

    def _generate_subtask_blueprint(
        self,
        parent: OrchestratorTask | Any,
        *,
        max_subtasks: int,
        context: str | None = None,
    ) -> list[dict[str, Any]]:
        criteria = self._acceptance_criteria_items(getattr(parent, "acceptance_criteria", "") or "")
        task_title = str(getattr(parent, "title", "Task")).strip()
        task_type = str(getattr(parent, "task_type", "general")).strip()
        shared_context = f"Context: {context}\n\n" if context else ""
        criteria_text = " ".join(criteria).lower()
        wants_docs = any(token in criteria_text for token in ["document", "docs", "adr", "summary"])
        wants_tests = any(
            token in criteria_text for token in ["test", "verify", "validation", "qa"]
        )
        plan: list[dict[str, Any]] = [
            {
                "kind": "plan",
                "title": f"Plan scope for {task_title}",
                "description": f"{shared_context}Define the execution plan, assumptions, and dependency/risk map for this {task_type} task.",
                "dependency_indexes": [],
                "parallelizable": False,
                "required_tools": ["fs_read"],
                "labels": ["planning"],
                "acceptance_criteria": "Document execution plan, assumptions, and risks.",
            }
        ]
        if criteria:
            plan.append(
                {
                    "kind": "implement",
                    "title": f"Implement core work for {task_title}",
                    "description": f"{shared_context}Deliver the main implementation required by the task and cover these criteria:\n- "
                    + "\n- ".join(criteria[:4]),
                    "dependency_indexes": [0],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["implementation"],
                    "acceptance_criteria": "\n".join(criteria[: min(3, len(criteria))]),
                }
            )
        else:
            plan.append(
                {
                    "kind": "implement",
                    "title": f"Implement {task_title}",
                    "description": f"{shared_context}Ship the main implementation for this task.",
                    "dependency_indexes": [0],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["implementation"],
                    "acceptance_criteria": "Primary implementation completed.",
                }
            )
        if wants_tests or max_subtasks >= 3:
            plan.append(
                {
                    "kind": "verify",
                    "title": f"Verify and test {task_title}",
                    "description": f"{shared_context}Run tests, validate acceptance criteria, and record any follow-up issues.",
                    "dependency_indexes": [1],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["testing"],
                    "acceptance_criteria": "Tests pass and acceptance criteria are validated.",
                }
            )
        if wants_docs or max_subtasks >= 4:
            plan.append(
                {
                    "kind": "document",
                    "title": f"Document rollout for {task_title}",
                    "description": f"{shared_context}Capture the final summary, operator notes, and any rollout caveats.",
                    "dependency_indexes": [1],
                    "parallelizable": True,
                    "required_tools": ["fs_write"],
                    "labels": ["documentation"],
                    "acceptance_criteria": "Documentation and rollout notes are updated.",
                }
            )
        return plan[:max_subtasks]

    async def ingest_incident_alert(self, user: User, payload: dict[str, Any]) -> OrchestratorTask:
        project_id = str(payload.get("project_id") or "")
        project = await self.get_project(user, project_id)
        source = str(payload.get("source") or "webhook")
        title = str(payload.get("title") or "Incident alert")
        body = str(payload.get("body") or "")
        severity = str(payload.get("severity") or "high")
        task = await self.create_task(
            user,
            project.id,
            {
                "title": f"[Incident:{severity}] {title}",
                "description": body,
                "priority": "urgent" if severity in {"critical", "sev1"} else "high",
                "task_type": "incident",
                "status": "planned",
                "metadata": {"incident_source": source, "alert_payload": payload},
            },
        )
        return task
