from __future__ import annotations

import io
import logging
import re
import tarfile
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.memory.settings import merge_memory_settings
from backend.modules.notifications.repository import NotificationsRepository
from backend.modules.orchestration.local_repo import (
    LocalRepoError,
    build_context_pack,
    create_isolated_worktree,
    inspect_workspace,
    normalize_workspace,
    read_repo_file,
    run_safe_command,
)
from backend.modules.projects.models import Project, ProjectTask
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    PortfolioExecutionPolicy,
    ProjectDecision,
    ProjectMilestone,
)
from backend.modules.projects.repository import ProjectsRepository
from backend.modules.projects.schemas import (
    ProjectTaskCreate,
    ProjectTaskReorderRequest,
    ProjectTaskUpdate,
)
from backend.modules.team.models import AgentProfile
from backend.modules.users.repository import UsersRepository

logger = logging.getLogger(__name__)


DEFAULT_PORTFOLIO_EXECUTION_POLICY: dict[str, Any] = {
    "routing_mode": "capability_based",
    "approval_policy": "manager_review",
    "repo_indexing_cadence": "daily",
    "cost_cap_usd": 250.0,
}


class ProjectsService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ProjectsRepository(db)
        self.users_repo = UsersRepository(db)
        self.notifications_repo = NotificationsRepository(db)

    async def create_project(self, owner_id: str, name: str, description: str | None) -> Project:
        project = await self.repo.create(owner_id, name, description)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def list_projects(self, user_id: str) -> list[Project]:
        return await self.repo.list_accessible_by_user(user_id)

    async def get_project(self, user_id: str, project_id: str) -> Project:
        return await self._get_project_or_404(user_id, project_id)

    async def list_tasks(
        self, user_id: str, project_id: str
    ) -> list[tuple[ProjectTask, User | None]]:
        project = await self._get_project_or_404(user_id, project_id)
        return await self.repo.list_tasks_with_assignees(project.id)

    async def create_task(
        self,
        user_id: str,
        actor: User,
        project_id: str,
        payload: ProjectTaskCreate,
    ) -> tuple[ProjectTask, User | None]:
        project = await self._get_project_or_404(user_id, project_id)
        assignee = await self._get_assignee_or_404(payload.assignee_id)
        position = await self.repo.get_next_task_position(project.id, payload.status)
        task = await self.repo.create_task(
            project_id=project.id,
            title=payload.title,
            description=payload.description,
            status=payload.status,
            priority=payload.priority,
            due_date=payload.due_date,
            assignee_id=assignee.id if assignee else None,
            position=position,
        )

        await self._notify_assignment(project, task, actor, None, assignee)
        await self._notify_due_date_change(project, task, actor, None, assignee)

        await self.db.commit()
        task_row = await self.repo.get_task_with_assignee(project.id, task.id)
        if not task_row:
            raise HTTPException(status_code=500, detail="Failed to load created task")
        return task_row

    async def update_task(
        self,
        user_id: str,
        actor: User,
        project_id: str,
        task_id: str,
        payload: ProjectTaskUpdate,
    ) -> tuple[ProjectTask, User | None]:
        project = await self._get_project_or_404(user_id, project_id)
        task = await self.repo.get_task_by_id(project.id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        fields_set = payload.model_fields_set
        previous_status = task.status
        previous_due_date = task.due_date
        previous_assignee_id = task.assignee_id

        if "title" in fields_set:
            task.title = payload.title or task.title
        if "description" in fields_set:
            task.description = payload.description
        if "priority" in fields_set and payload.priority is not None:
            task.priority = payload.priority
        if "due_date" in fields_set:
            task.due_date = payload.due_date

        assignee = None
        if "assignee_id" in fields_set:
            assignee = await self._get_assignee_or_404(payload.assignee_id)
            task.assignee_id = assignee.id if assignee else None
        elif task.assignee_id:
            assignee = await self.users_repo.get_active_user_by_id(task.assignee_id)

        if "status" in fields_set and payload.status is not None and payload.status != task.status:
            task.status = payload.status
            task.position = await self.repo.get_next_task_position(project.id, payload.status)

        await self._normalize_positions(project.id)
        await self._notify_assignment(project, task, actor, previous_assignee_id, assignee)
        await self._notify_due_date_change(project, task, actor, previous_due_date, assignee)
        await self._notify_status_change(project, task, actor, previous_status)

        await self.db.commit()
        task_row = await self.repo.get_task_with_assignee(project.id, task.id)
        if not task_row:
            raise HTTPException(status_code=500, detail="Failed to load updated task")
        return task_row

    async def delete_task(self, user_id: str, project_id: str, task_id: str) -> None:
        project = await self._get_project_or_404(user_id, project_id)
        task = await self.repo.get_task_by_id(project.id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")

        await self.repo.delete_task(task)
        await self._normalize_positions(project.id)
        await self.db.commit()

    async def reorder_tasks(
        self,
        user_id: str,
        actor: User,
        project_id: str,
        payload: ProjectTaskReorderRequest,
    ) -> list[tuple[ProjectTask, User | None]]:
        project = await self._get_project_or_404(user_id, project_id)
        task_rows = await self.repo.list_tasks_with_assignees(project.id)
        tasks_by_id = {task.id: task for task, _ in task_rows}
        previous_status_by_id = {task.id: task.status for task, _ in task_rows}

        seen_ids: list[str] = []
        for column in payload.columns:
            for position, task_id in enumerate(column.task_ids):
                task = tasks_by_id.get(task_id)
                if not task:
                    raise HTTPException(status_code=404, detail="Task not found in reorder payload")
                task.status = column.status
                task.position = position
                seen_ids.append(task_id)

        if len(seen_ids) != len(tasks_by_id) or set(seen_ids) != set(tasks_by_id):
            raise HTTPException(
                status_code=400,
                detail="Reorder payload must include every task exactly once",
            )

        await self._normalize_positions(project.id)

        for task, _ in task_rows:
            await self._notify_status_change(project, task, actor, previous_status_by_id[task.id])

        await self.db.commit()
        return await self.repo.list_tasks_with_assignees(project.id)

    async def _get_project_or_404(self, user_id: str, project_id: str) -> Project:
        project = await self.repo.get_by_id_for_user(project_id, user_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    async def _get_assignee_or_404(self, assignee_id: str | None) -> User | None:
        if not assignee_id:
            return None
        assignee = await self.users_repo.get_active_user_by_id(assignee_id)
        if not assignee:
            raise HTTPException(status_code=404, detail="Assignee not found")
        return assignee

    async def _normalize_positions(self, project_id: str) -> None:
        rows = await self.repo.list_tasks_with_assignees(project_id)
        grouped: dict[str, list[ProjectTask]] = {}
        for task, _ in rows:
            grouped.setdefault(task.status, []).append(task)

        for tasks in grouped.values():
            for index, task in enumerate(tasks):
                task.position = index

        await self.db.flush()

    async def _notify_assignment(
        self,
        project: Project,
        task: ProjectTask,
        actor: User,
        previous_assignee_id: str | None,
        assignee: User | None,
    ) -> None:
        if not assignee or assignee.id == previous_assignee_id or assignee.id == actor.id:
            return

        await self.notifications_repo.create(
            user_id=assignee.id,
            type="task_assigned",
            title=f"Task assigned: {task.title}",
            body=(
                f"{self._actor_label(actor)} assigned you the task "
                f"\"{task.title}\" in project \"{project.name}\"."
            ),
        )

    async def _notify_due_date_change(
        self,
        project: Project,
        task: ProjectTask,
        actor: User,
        previous_due_date: date | None,
        assignee: User | None,
    ) -> None:
        if (
            not assignee
            or assignee.id == actor.id
            or task.due_date is None
            or task.due_date == previous_due_date
        ):
            return

        await self.notifications_repo.create(
            user_id=assignee.id,
            type="task_due_date_updated",
            title=f"Due date updated: {task.title}",
            body=(
                f"{self._actor_label(actor)} set the due date for \"{task.title}\" "
                f"to {task.due_date.isoformat()} in project \"{project.name}\"."
            ),
        )

    async def _notify_status_change(
        self,
        project: Project,
        task: ProjectTask,
        actor: User,
        previous_status: str,
    ) -> None:
        if task.status == previous_status or project.owner_id == actor.id:
            return

        if task.status not in {"review", "done"}:
            return

        target_label = "review" if task.status == "review" else "done"
        await self.notifications_repo.create(
            user_id=project.owner_id,
            type="task_status_changed",
            title=f"Task moved to {target_label}: {task.title}",
            body=(
                f"{self._actor_label(actor)} moved \"{task.title}\" to {target_label} "
                f"in project \"{project.name}\"."
            ),
        )

    @staticmethod
    def _actor_label(actor: User) -> str:
        return actor.full_name or actor.email


class OrchestrationProjectsServiceMixin:
    """Project, portfolio, and policy methods extracted from orchestration.

    The host service is expected to provide ``self.db``, ``self.repo``,
    ``self.audit_repo``, and the orchestration-only helpers used for repository
    indexing, task bootstrapping, and knowledge-graph side effects.
    """

    async def get_overview(self, user: User) -> dict[str, Any]:
        ensure_catalog_seeded = getattr(self, "_ensure_catalog_seeded", None)
        if callable(ensure_catalog_seeded):
            await ensure_catalog_seeded()
        return {
            "projects": await self.repo.list_projects(user.id),
            "agents": await self.repo.list_agents(user.id),
            "active_runs": (await self.repo.list_runs(user.id))[:10],
            "pending_approvals": (await self.repo.list_approvals(user.id, "pending"))[:10],
            "github_events": (await self.repo.list_sync_events(user.id))[:10],
        }

    async def list_projects(self, user: User):
        return await self.repo.list_projects(user.id)

    async def get_portfolio_execution_policy(self, user: User) -> dict[str, Any]:
        stmt = select(PortfolioExecutionPolicy).where(PortfolioExecutionPolicy.owner_id == user.id)
        record = (await self.db.execute(stmt)).scalar_one_or_none()
        return self._normalize_portfolio_execution_policy(record.settings_json if record else None)

    async def update_portfolio_execution_policy(
        self, user: User, payload: dict[str, Any]
    ) -> dict[str, Any]:
        normalized = self._normalize_portfolio_execution_policy(payload)
        stmt = select(PortfolioExecutionPolicy).where(PortfolioExecutionPolicy.owner_id == user.id)
        record = (await self.db.execute(stmt)).scalar_one_or_none()
        if record is None:
            record = PortfolioExecutionPolicy(owner_id=user.id, settings_json=normalized)
            self.db.add(record)
        else:
            record.settings_json = normalized

        projects = await self.repo.list_projects(user.id)
        for project in projects:
            project.settings_json = self._normalize_project_settings(
                self._apply_portfolio_defaults_to_project_settings(
                    project.settings_json or {},
                    normalized,
                )
            )

        await self.db.commit()
        return normalized

    async def _resolve_default_company_id(self, owner_id: str) -> str:
        from backend.modules.companies.service import CompanyService

        company = await CompanyService(self.db).get_or_create_default(owner_id)
        return company.id

    async def _ensure_company_id_for_project(self, project: OrchestratorProject) -> str:
        if getattr(project, "company_id", None):
            return project.company_id  # type: ignore[return-value]
        company_id = await self._resolve_default_company_id(project.owner_id)
        project.company_id = company_id
        return company_id

    async def create_project(self, user: User, payload: dict[str, Any]):
        policy_defaults = await self.get_portfolio_execution_policy(user)
        settings = self._apply_portfolio_defaults_to_project_settings(
            payload.get("settings", {}),
            policy_defaults,
            explicit_settings=payload.get("settings", {}),
        )
        company_id = payload.get("company_id") or await self._resolve_default_company_id(user.id)
        project = await self.repo.create_project(
            owner_id=user.id,
            company_id=company_id,
            name=payload["name"],
            slug=payload["slug"],
            description=payload.get("description"),
            status=payload.get("status", "active"),
            goals_markdown=payload.get("goals_markdown", ""),
            settings_json=self._normalize_project_settings(settings),
            memory_scope=payload.get("memory_scope", "project"),
            knowledge_summary=payload.get("knowledge_summary"),
        )
        await self.audit_repo.log(
            "orchestration.project.created",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
        )
        await self.db.commit()
        await self.db.refresh(project)
        execution_settings = ((project.settings_json or {}).get("execution") or {})
        team_profile_id = str(execution_settings.get("team_profile_id") or "").strip()
        if team_profile_id:
            try:
                await self._materialize_team_profile_for_project(user, project, team_profile_id)
                settings = dict(project.settings_json or {})
                execution = dict(settings.get("execution") or {})
                execution["team_profile_apply_status"] = "applied"
                execution["team_profile_apply_error"] = None
                settings["execution"] = execution
                project.settings_json = self._normalize_project_settings(settings)
                await self.db.commit()
            except HTTPException as exc:
                settings = dict(project.settings_json or {})
                execution = dict(settings.get("execution") or {})
                execution["team_profile_apply_status"] = "failed"
                execution["team_profile_apply_error"] = str(exc.detail)
                settings["execution"] = execution
                project.settings_json = self._normalize_project_settings(settings)
                await self.db.commit()
            await self.db.refresh(project)
        return project

    async def _materialize_team_profile_for_project(
        self,
        user: User,
        project: OrchestratorProject,
        team_profile_id: str,
    ) -> None:
        get_team_profile = getattr(self.repo, "get_team_profile", None)
        if not callable(get_team_profile):
            raise HTTPException(status_code=500, detail="Team profile repository is unavailable.")
        team_profile = await get_team_profile(user.id, team_profile_id)
        if team_profile is None:
            raise HTTPException(status_code=404, detail="Selected team profile not found.")
        template_slugs = [str(slug).strip() for slug in (team_profile.agent_template_slugs_json or []) if str(slug).strip()]
        if not template_slugs:
            raise HTTPException(
                status_code=409,
                detail="Selected team profile has no agent templates. Add templates to team profile first.",
            )
        all_agents = await self.repo.list_agents(user.id, project.id)
        reserved_slugs = {agent.slug for agent in all_agents}

        def _slugify(value: str) -> str:
            return re.sub(r"(^-|-$)", "", re.sub(r"[^a-z0-9]+", "-", value.lower().strip()))

        def _unique_slug(base: str) -> str:
            candidate = _slugify(base) or "agent"
            if candidate not in reserved_slugs:
                reserved_slugs.add(candidate)
                return candidate
            index = 2
            while f"{candidate}-{index}" in reserved_slugs:
                index += 1
            resolved = f"{candidate}-{index}"
            reserved_slugs.add(resolved)
            return resolved

        manager_assigned = False
        for template_slug in template_slugs:
            try:
                agent = await self.create_agent_from_template(
                    user,
                    template_slug,
                    {
                        "project_id": project.id,
                        "slug": _unique_slug(f"{project.slug}-{template_slug}"),
                    },
                )
            except HTTPException as exc:
                if exc.status_code != 422:
                    raise
                template = await self.repo.get_agent_template_by_slug(template_slug)
                if template is None:
                    raise
                allowed_runtime_tools = {
                    "github_comment",
                    "github_label_issue",
                    "github_create_pr",
                    "web_fetch",
                    "web_search",
                    "code_execute",
                    "fs_read",
                    "fs_write",
                    "db_query",
                    "repo_search",
                }
                fallback_payload = {
                    "project_id": project.id,
                    "parent_template_slug": template.slug,
                    "name": template.name or template.slug,
                    "slug": _unique_slug(f"{project.slug}-{template.slug}"),
                    "description": template.description or "",
                    "role": template.role or "specialist",
                    "capabilities": list(template.capabilities_json or []),
                    "allowed_tools": [tool for tool in (template.allowed_tools_json or []) if tool in allowed_runtime_tools],
                    "tags": list(template.tags_json or []),
                    "model_policy": {"permissions": "read-only", "escalation_path": None},
                    "memory_policy": {"scope": "project-only"},
                    "output_schema": {"format": "json"},
                    "budget": {"token_budget": 8000, "time_budget_seconds": 300, "retry_budget": 1},
                    "task_filters": [],
                    "metadata": {
                        "from_template": template.slug,
                        "team_profile_id": team_profile_id,
                        "materialized_with_fallback": True,
                    },
                }
                agent = await self.create_agent(user, fallback_payload)
            role = agent.role if agent.role in {"manager", "reviewer", "moderator"} else "member"
            is_default_manager = role == "manager" and not manager_assigned
            await self.add_project_agent(
                user,
                project.id,
                {
                    "agent_id": agent.id,
                    "role": role,
                    "is_default_manager": is_default_manager,
                },
            )
            if is_default_manager:
                manager_assigned = True

    async def get_project(self, user: User, project_id: str):
        project = await self.repo.get_project(user.id, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    async def update_project(self, user: User, project_id: str, updates: dict[str, Any]):
        project = await self.get_project(user, project_id)
        for field, value in updates.items():
            if field == "settings":
                defaults = await self.get_portfolio_execution_policy(user)
                merged = self._merge_nested_project_settings(project.settings_json or {}, value or {})
                merged = self._apply_portfolio_defaults_to_project_settings(
                    merged,
                    defaults,
                    explicit_settings=value or {},
                )
                project.settings_json = self._normalize_project_settings(merged)
            else:
                setattr(project, field, value)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def delete_project(self, user: User, project_id: str) -> None:
        project = await self.get_project(user, project_id)
        await self.db.delete(project)
        await self.audit_repo.log(
            "orchestration.project.deleted",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
        )
        await self.db.commit()

    async def get_gate_config(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = self._project_execution_settings(project)
        return {
            "autonomy_level": settings.get("autonomy_level", "assisted"),
            "approval_gates": settings.get(
                "approval_gates",
                [
                    "post_to_github",
                    "open_pr",
                    "mark_complete",
                    "change_task_ownership",
                    "write_memory",
                    "use_expensive_model",
                    "run_tool",
                ],
            ),
        }

    async def update_gate_config(
        self,
        user: User,
        project_id: str,
        autonomy_level: str | None,
        approval_gates: list[str] | None,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        if autonomy_level is not None:
            execution["autonomy_level"] = autonomy_level
        if approval_gates is not None:
            execution["approval_gates"] = approval_gates
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return await self.get_gate_config(user, project_id)

    async def add_project_agent(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        agent = await self.repo.get_agent(user.id, payload["agent_id"])
        if agent is None:
            raise HTTPException(status_code=404, detail="Agent not found")
        existing = await self.repo.get_project_membership(project.id, agent.id)
        if existing:
            raise HTTPException(status_code=409, detail="Agent already assigned to project")
        if payload.get("is_default_manager"):
            for membership in await self.repo.list_project_memberships(project.id):
                membership.is_default_manager = False
        membership = await self.repo.create_project_membership(project_id=project.id, **payload)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def list_project_agents(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        await self._purge_orphan_template_agents(user.id)
        return await self.repo.list_project_memberships(project_id)

    async def update_project_agent(
        self, user: User, project_id: str, membership_id: str, updates: dict[str, Any]
    ):
        project = await self.get_project(user, project_id)
        membership = await self.repo.get_project_membership_by_id(project.id, membership_id)
        if not membership:
            raise HTTPException(status_code=404, detail="Project agent membership not found")
        if updates.get("is_default_manager"):
            for item in await self.repo.list_project_memberships(project.id):
                item.is_default_manager = item.id == membership.id
        if "role" in updates and updates["role"] is not None:
            membership.role = updates["role"]
        if "is_default_manager" in updates and updates["is_default_manager"] is not None:
            membership.is_default_manager = updates["is_default_manager"]
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def remove_project_agent(self, user: User, project_id: str, membership_id: str) -> None:
        project = await self.get_project(user, project_id)
        membership = await self.repo.get_project_membership_by_id(project.id, membership_id)
        if not membership:
            raise HTTPException(status_code=404, detail="Project agent membership not found")
        await self.db.delete(membership)
        await self.db.commit()

    async def add_project_repository(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        item = await self.repo.create_project_repository(project_id=project_id, **payload)
        await self.db.commit()
        await self.db.refresh(item)
        sync_repository = getattr(self, "_sync_knowledge_graph_for_project_repository", None)
        if callable(sync_repository):
            await sync_repository(project, item)
            await self.db.commit()
        return item

    async def list_project_repositories(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        return await self.repo.list_project_repositories(project_id)

    async def get_local_repo_workspace(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        return normalize_workspace(settings.get("local_repo"))

    async def validate_local_repo_workspace(self, user: User, payload: dict[str, Any]) -> dict[str, Any]:
        _ = user
        workspace = normalize_workspace(payload)
        try:
            return inspect_workspace(workspace)
        except LocalRepoError as exc:
            return {"valid": False, "blocked_reasons": [str(exc)], "workspace": workspace}

    async def update_local_repo_workspace(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        workspace = normalize_workspace(payload)
        try:
            status = inspect_workspace(workspace)
        except LocalRepoError as exc:
            if workspace["enabled"]:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            status = {"valid": False, "blocked_reasons": [str(exc)], "workspace": workspace}
        settings = dict(project.settings_json or {})
        settings["local_repo"] = {**workspace, "last_validation": status}
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return status

    async def inspect_local_repo_workspace(self, user: User, project_id: str) -> dict[str, Any]:
        workspace = await self.get_local_repo_workspace(user, project_id)
        try:
            return inspect_workspace(workspace)
        except LocalRepoError as exc:
            return {"valid": False, "blocked_reasons": [str(exc)], "workspace": workspace}

    async def create_local_repo_worktree(
        self,
        user: User,
        project_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        task = await self.repo.get_task(project.id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        workspace = normalize_workspace((project.settings_json or {}).get("local_repo"))
        try:
            worktree = create_isolated_worktree(workspace, task_id=task.id, title=task.title)
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        metadata = dict(task.metadata_json or {})
        session = dict(metadata.get("local_repo_session") or {})
        session.update(
            {
                "status": "preparing_workspace",
                "worktree": worktree,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        await self.db.commit()
        return worktree

    async def build_local_repo_context_pack(
        self,
        user: User,
        project_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        task = await self.repo.get_task(project.id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        issue_text = "\n\n".join(part for part in [task.title, task.description or ""] if part)
        try:
            context = build_context_pack(
                (project.settings_json or {}).get("local_repo"),
                issue_text=issue_text,
                acceptance_criteria=task.acceptance_criteria,
            )
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await self.repo.create_task_artifact(
            task_id=task.id,
            run_id=None,
            kind="local_repo_context_pack",
            title="Local repo context pack",
            content=None,
            metadata_json=context,
        )
        metadata = dict(task.metadata_json or {})
        session = dict(metadata.get("local_repo_session") or {})
        session.update({"status": "analyzing", "context_pack_created_at": context["created_at"]})
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        await self.db.commit()
        return context

    async def run_local_repo_command(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        try:
            result = run_safe_command(
                (project.settings_json or {}).get("local_repo"),
                command=str(payload.get("command") or ""),
                cwd=payload.get("cwd"),
                timeout_seconds=int(payload.get("timeout_seconds") or 60),
            )
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "command": result.command,
            "cwd": result.cwd,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
        }

    async def read_local_repo_file(
        self,
        user: User,
        project_id: str,
        path: str,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        try:
            return read_repo_file((project.settings_json or {}).get("local_repo"), path)
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc

    async def update_project_repository(
        self, user: User, project_id: str, repository_link_id: str, updates: dict[str, Any]
    ):
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if "default_branch" in updates:
            repository_link.default_branch = updates.get("default_branch")
        if "metadata" in updates and isinstance(updates.get("metadata"), dict):
            repository_link.metadata_json = {
                **(repository_link.metadata_json or {}),
                **(updates.get("metadata") or {}),
            }
        if "github_repository_id" in updates and updates.get("github_repository_id") is not None:
            repository_link.github_repository_id = updates["github_repository_id"]
        await self.db.commit()
        await self.db.refresh(repository_link)
        sync_repository = getattr(self, "_sync_knowledge_graph_for_project_repository", None)
        if callable(sync_repository):
            await sync_repository(project, repository_link)
            await self.db.commit()
        return repository_link

    async def list_project_memory_ingest_jobs(
        self, user: User, project_id: str, *, limit: int = 60
    ) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        rows = await self.repo.list_memory_ingest_jobs_for_project(user.id, project_id, limit=limit)
        return [
            {
                "id": row.id,
                "project_id": row.project_id,
                "job_type": row.job_type,
                "status": row.status,
                "error_text": row.error_text,
                "created_at": row.created_at,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "payload": row.payload_json or {},
            }
            for row in rows
        ]

    async def project_repository_index_status(self, user: User, project_id: str) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        repositories = await self.repo.list_project_repositories(project.id)
        jobs = await self.repo.list_memory_ingest_jobs_for_project(user.id, project.id, limit=240)
        documents = await self.repo.list_documents(project.id, None)

        documents_by_repo: dict[str, list[Any]] = {}
        for document in documents:
            metadata = document.metadata_json or {}
            if metadata.get("source_kind") != "repo_index":
                continue
            repository_link_id = str(metadata.get("repository_link_id") or "")
            if not repository_link_id:
                continue
            documents_by_repo.setdefault(repository_link_id, []).append(document)

        jobs_by_repo: dict[str, list[Any]] = {}
        for job in jobs:
            if job.job_type != "repo_index":
                continue
            repository_link_id = str((job.payload_json or {}).get("repository_link_id") or "")
            if not repository_link_id:
                continue
            jobs_by_repo.setdefault(repository_link_id, []).append(job)

        rows: list[dict[str, Any]] = []
        for repository in repositories:
            repo_docs = documents_by_repo.get(repository.id, [])
            repo_jobs = jobs_by_repo.get(repository.id, [])
            latest_job = repo_jobs[0] if repo_jobs else None
            latest_success = next((job for job in repo_jobs if job.status == "completed"), None)
            indexed_files = len(repo_docs)
            chunk_count = sum(int(doc.chunk_count or 0) for doc in repo_docs)
            latest_indexed_at = None
            if repo_docs:
                latest_indexed_at = max(
                    (
                        doc.updated_at or doc.created_at
                        for doc in repo_docs
                        if (doc.updated_at or doc.created_at)
                    ),
                    default=None,
                )
            recent_files = [
                {
                    "document_id": doc.id,
                    "path": str((doc.metadata_json or {}).get("path") or doc.filename),
                    "branch": str(
                        (doc.metadata_json or {}).get("branch") or repository.default_branch or ""
                    ),
                    "chunk_count": int(doc.chunk_count or 0),
                    "status": doc.ingestion_status,
                }
                for doc in sorted(
                    repo_docs,
                    key=lambda item: item.updated_at or item.created_at,
                    reverse=True,
                )[:10]
            ]
            recent_errors = [
                {
                    "job_id": job.id,
                    "error_text": job.error_text,
                    "created_at": job.created_at,
                    "mode": str((job.payload_json or {}).get("mode") or "full"),
                    "path_prefixes": list((job.payload_json or {}).get("path_prefixes") or []),
                }
                for job in repo_jobs
                if job.status == "failed" and job.error_text
            ][:5]
            index_settings = dict((repository.metadata_json or {}).get("indexing") or {})
            rows.append(
                {
                    "repository_link_id": repository.id,
                    "github_repository_id": repository.github_repository_id,
                    "full_name": repository.full_name,
                    "default_branch": repository.default_branch,
                    "repository_url": repository.repository_url,
                    "index_settings": index_settings,
                    "indexed_files": indexed_files,
                    "chunk_count": chunk_count,
                    "searchable_documents": indexed_files,
                    "last_indexed_at": latest_indexed_at,
                    "latest_job": {
                        "id": latest_job.id,
                        "status": latest_job.status,
                        "error_text": latest_job.error_text,
                        "created_at": latest_job.created_at,
                        "started_at": latest_job.started_at,
                        "finished_at": latest_job.finished_at,
                        "mode": str((latest_job.payload_json or {}).get("mode") or "full"),
                        "path_prefixes": list((latest_job.payload_json or {}).get("path_prefixes") or []),
                    }
                    if latest_job
                    else None,
                    "last_successful_job_id": latest_success.id if latest_success else None,
                    "pending_jobs": sum(1 for job in repo_jobs if job.status == "pending"),
                    "running_jobs": sum(1 for job in repo_jobs if job.status == "running"),
                    "recent_files": recent_files,
                    "recent_errors": recent_errors,
                }
            )
        return rows

    async def index_project_repository(
        self,
        user: User,
        project_id: str,
        repository_link_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if not repository_link.github_repository_id:
            raise HTTPException(status_code=422, detail="Project repository is not linked to GitHub")
        path_prefixes = [
            str(item).strip()
            for item in list(payload.get("path_prefixes") or [])
            if str(item).strip()
        ][:20]
        mode = "incremental" if str(payload.get("mode") or "full") == "incremental" else "full"
        auto_enabled = payload.get("auto_enabled")
        schedule_label = str(payload.get("schedule_label") or "").strip() or None
        if auto_enabled is not None or schedule_label is not None:
            metadata = dict(repository_link.metadata_json or {})
            metadata["indexing"] = {
                **dict(metadata.get("indexing") or {}),
                **({"auto_enabled": bool(auto_enabled)} if auto_enabled is not None else {}),
                **({"schedule_label": schedule_label} if schedule_label is not None else {}),
                "last_requested_mode": mode,
                "last_requested_at": datetime.now(UTC).isoformat(),
                "path_prefixes": path_prefixes,
            }
            repository_link.metadata_json = metadata
        job = await self.repo.create_memory_ingest_job(
            owner_id=user.id,
            project_id=project.id,
            job_type="repo_index",
            payload_json={
                "project_id": project.id,
                "repository_link_id": repository_link.id,
                "requested_by_user_id": user.id,
                "mode": mode,
                "path_prefixes": path_prefixes,
            },
            status="pending",
        )
        await self.db.commit()
        try:
            from backend.workers.orchestration import queue_memory_ingest_jobs

            queue_memory_ingest_jobs()
        except Exception as exc:
            logger.warning("queue memory ingest jobs failed for repo index: %s", exc)
        return {
            "queued": True,
            "job_id": job.id,
            "project_id": project.id,
            "repository_link_id": repository_link.id,
            "status": job.status,
            "mode": mode,
            "path_prefixes": path_prefixes,
        }

    async def _run_repository_index_job(
        self,
        *,
        owner_id: str,
        project_id: str,
        repository_link_id: str,
        requested_by_user_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        user = SimpleNamespace(id=owner_id)
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if not repository_link.github_repository_id:
            raise HTTPException(status_code=422, detail="Project repository is not linked to GitHub")
        github_repository = await self.repo.get_github_repository(user.id, repository_link.github_repository_id)
        if github_repository is None:
            raise HTTPException(status_code=404, detail="GitHub repository not found")
        connection = await self.repo.get_github_connection(user.id, github_repository.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="GitHub connection not found")

        github_request = getattr(self, "_github_request", None)
        if not callable(github_request):
            raise RuntimeError("_run_repository_index_job requires a host _github_request helper")
        index_document = getattr(self, "_index_project_document", None)
        if not callable(index_document):
            raise RuntimeError("_run_repository_index_job requires a host _index_project_document helper")

        branch = repository_link.default_branch or github_repository.default_branch or "main"
        path_prefixes = [
            str(item).strip()
            for item in list(payload.get("path_prefixes") or [])
            if str(item).strip()
        ][:20]
        requested_mode = str(payload.get("mode") or "full")
        archive_response = await github_request(
            connection,
            "GET",
            f"/repos/{github_repository.full_name}/tarball/{branch}",
        )
        if archive_response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch repository snapshot")
        allowed_suffixes = {
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".sql",
        }
        indexed = 0
        chunk_total = 0
        max_files = 200
        with tarfile.open(fileobj=io.BytesIO(archive_response.content), mode="r:gz") as tf:
            for member in tf.getmembers():
                if indexed >= max_files:
                    break
                if not member.isfile():
                    continue
                raw_name = str(member.name or "")
                _, _, path = raw_name.partition("/")
                if not path or not any(path.endswith(suffix) for suffix in allowed_suffixes):
                    continue
                if path_prefixes and not any(path.startswith(prefix) for prefix in path_prefixes):
                    continue
                extracted = tf.extractfile(member)
                if extracted is None:
                    continue
                file_payload = extracted.read()
                if not file_payload:
                    continue
                try:
                    content = file_payload.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                document = await self.repo.create_document(
                    project_id=project.id,
                    task_id=None,
                    uploaded_by_user_id=requested_by_user_id or user.id,
                    filename=path,
                    content_type="text/plain",
                    source_text=content,
                    object_key=None,
                    size_bytes=len(file_payload),
                    summary_text=content[:500],
                    ingestion_status="pending",
                    chunk_count=0,
                    ttl_days=None,
                    expires_at=None,
                    metadata_json={
                        "source_kind": "repo_index",
                        "repository_link_id": repository_link.id,
                        "repository_full_name": github_repository.full_name,
                        "branch": branch,
                        "path": path,
                        "index_mode": requested_mode,
                    },
                )
                await index_document(document)
                indexed += 1
                chunk_total += document.chunk_count
        return {
            "repository_link_id": repository_link.id,
            "repository_full_name": github_repository.full_name,
            "branch": branch,
            "indexed_files": indexed,
            "chunk_count": chunk_total,
            "mode": requested_mode,
            "path_prefixes": path_prefixes,
        }

    async def list_milestones(self, user: User, project_id: str) -> list[ProjectMilestone]:
        await self.get_project(user, project_id)
        return await self.repo.list_project_milestones(project_id)

    async def create_milestone(
        self,
        user: User,
        project_id: str,
        title: str,
        description: str | None,
        due_date: Any,
        status: str,
        position: int,
    ) -> ProjectMilestone:
        await self.get_project(user, project_id)
        item = await self.repo.create_project_milestone(
            project_id=project_id,
            title=title,
            description=description,
            due_date=due_date,
            status=status,
            position=position,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_milestone(
        self, user: User, project_id: str, milestone_id: str, updates: dict[str, Any]
    ) -> ProjectMilestone:
        await self.get_project(user, project_id)
        item = await self.repo.update_project_milestone(
            milestone_id,
            {k: v for k, v in updates.items() if v is not None},
        )
        if not item:
            raise HTTPException(status_code=404, detail="Milestone not found")
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_decisions(self, user: User, project_id: str) -> list[ProjectDecision]:
        await self.get_project(user, project_id)
        return await self.repo.list_project_decisions(project_id)

    async def create_decision(
        self,
        user: User,
        project_id: str,
        title: str,
        decision: str,
        rationale: str | None,
        author_label: str | None,
        task_id: str | None,
        brainstorm_id: str | None,
    ) -> ProjectDecision:
        project = await self.get_project(user, project_id)
        item = await self.repo.create_project_decision(
            project_id=project_id,
            task_id=task_id,
            brainstorm_id=brainstorm_id,
            title=title,
            decision=decision,
            rationale=rationale,
            author_label=author_label,
        )
        await self.db.commit()
        await self.db.refresh(item)
        sync_decision = getattr(self, "_sync_knowledge_graph_for_decision", None)
        if callable(sync_decision):
            await sync_decision(project, item)
            await self.db.commit()
        maybe_promote = getattr(self, "_maybe_promote_decision_to_semantic", None)
        if callable(maybe_promote):
            await maybe_promote(user, project, item)
        return item

    async def summarize_portfolio(self, user: User) -> list[dict[str, Any]]:
        return await self.repo.summarize_portfolio_for_owner(user.id)

    async def portfolio_control_plane(self, user: User) -> dict[str, Any]:
        projects = await self.repo.list_projects(user.id)
        approvals = await self.repo.list_approvals(user.id)
        providers = await self.repo.list_providers(user.id)
        policy_defaults = await self.get_portfolio_execution_policy(user)
        rows: list[dict[str, Any]] = []
        totals = {
            "projects": len(projects),
            "active_runs": 0,
            "blocked_tasks": 0,
            "pending_escalations": 0,
            "queue_depth": 0,
            "cost_usd_30d": 0.0,
        }
        cost_since = datetime.now(UTC) - timedelta(days=30)
        all_runs: list[Any] = []
        all_sync_events: list[Any] = []
        all_ingest_jobs: list[Any] = []

        for project in projects:
            memberships = await self.repo.list_project_memberships(project.id)
            manager_membership = next(
                (item for item in memberships if item.is_default_manager),
                next((item for item in memberships if item.role == "manager"), None),
            )
            manager_agent = (
                await self.db.get(AgentProfile, manager_membership.agent_id)
                if manager_membership
                else None
            )
            tasks = await self.repo.list_tasks(project.id)
            runs = await self.repo.list_runs(user.id, project.id)
            repositories = await self.repo.list_project_repositories(project.id)
            sync_events = await self.repo.list_sync_events(user.id, project.id)
            ingest_jobs = await self.repo.list_memory_ingest_jobs_for_project(
                user.id,
                project.id,
                limit=80,
            )
            all_runs.extend(runs)
            all_sync_events.extend(sync_events)
            all_ingest_jobs.extend(ingest_jobs)
            project_approvals = [
                item for item in approvals if item.project_id == project.id and item.status == "pending"
            ]

            blocked_tasks = [task for task in tasks if task.status == "blocked"]
            queue_depth = {
                "queued_runs": sum(1 for run in runs if run.status == "queued"),
                "active_runs": sum(1 for run in runs if run.status in {"in_progress", "blocked"}),
                "queued_tasks": sum(1 for task in tasks if task.status in {"queued", "planned"}),
            }
            cost_usd_30d = sum(
                float(run.estimated_cost_micros or 0) / 1_000_000
                for run in runs
                if run.created_at >= cost_since
            )
            escalation_inbox = [
                {
                    "approval_id": item.id,
                    "approval_type": item.approval_type,
                    "task_id": item.task_id,
                    "run_id": item.run_id,
                    "reason": item.reason,
                    "created_at": item.created_at,
                }
                for item in project_approvals
                if item.approval_type in {"rule_escalation", "task_escalation", "sla_escalation"}
            ][:8]
            latest_run = runs[0] if runs else None
            repo_failures = sum(1 for event in sync_events if event.status in {"failed", "error"})
            ingest_failures = sum(1 for job in ingest_jobs if job.status == "failed")

            health_score = 100
            health_score -= min(len(blocked_tasks) * 10, 40)
            health_score -= min(repo_failures * 8, 24)
            health_score -= min(ingest_failures * 8, 16)
            health_score -= min(len(escalation_inbox) * 6, 18)
            health_status = (
                "healthy" if health_score >= 80 else "watch" if health_score >= 55 else "critical"
            )

            row = {
                "project_id": project.id,
                "name": project.name,
                "slug": project.slug,
                "manager": {
                    "agent_id": getattr(manager_agent, "id", None),
                    "name": getattr(manager_agent, "name", None),
                    "slug": getattr(manager_agent, "slug", None),
                },
                "health": {
                    "status": health_status,
                    "score": health_score,
                    "repository_failures": repo_failures,
                    "index_failures": ingest_failures,
                    "open_blockers": len(blocked_tasks),
                },
                "queue_depth": queue_depth,
                "cost_rollup": {
                    "cost_usd_30d": round(cost_usd_30d, 4),
                    "token_total_30d": sum(
                        int(run.token_total or 0) for run in runs if run.created_at >= cost_since
                    ),
                    "repository_links": len(repositories),
                },
                "blocked_work": [
                    {
                        "task_id": task.id,
                        "title": task.title,
                        "priority": task.priority,
                        "updated_at": task.updated_at,
                    }
                    for task in blocked_tasks[:6]
                ],
                "escalation_inbox": escalation_inbox,
                "latest_run": {
                    "run_id": latest_run.id,
                    "status": latest_run.status,
                    "task_id": latest_run.task_id,
                    "created_at": latest_run.created_at,
                }
                if latest_run
                else None,
                "execution_policy": self._project_execution_policy_summary(project, policy_defaults),
            }
            totals["active_runs"] += queue_depth["active_runs"] + queue_depth["queued_runs"]
            totals["blocked_tasks"] += len(blocked_tasks)
            totals["pending_escalations"] += len(escalation_inbox)
            totals["queue_depth"] += sum(queue_depth.values())
            totals["cost_usd_30d"] += cost_usd_30d
            rows.append(row)

        queued_runs = [run for run in all_runs if run.status == "queued"]
        blocked_or_running_runs = [run for run in all_runs if run.status in {"in_progress", "blocked"}]
        stuck_threshold = datetime.now(UTC) - timedelta(minutes=45)
        stuck_runs = [
            run
            for run in blocked_or_running_runs
            if (run.started_at or run.created_at) <= stuck_threshold
        ]
        pending_webhooks = [event for event in all_sync_events if event.status in {"queued", "pending"}]
        replay_candidates = [
            event
            for event in all_sync_events
            if (
                ((event.payload_json or {}).get("_webhook_meta") or {}).get("replay_history")
                or "replay" in str(event.action or "").lower()
            )
        ]
        replay_backlog = [
            event
            for event in replay_candidates
            if event.status in {"queued", "pending", "failed", "error"}
        ]
        oldest_pending_webhook = min((event.created_at for event in pending_webhooks), default=None)
        webhook_lag_minutes = (
            round((datetime.now(UTC) - oldest_pending_webhook).total_seconds() / 60, 1)
            if oldest_pending_webhook
            else 0.0
        )
        provider_unhealthy = [provider for provider in providers if not provider.is_healthy]
        index_running = [job for job in all_ingest_jobs if job.status == "running"]
        index_failed = [job for job in all_ingest_jobs if job.status == "failed"]

        operator_dashboard = {
            "generated_at": datetime.now(UTC),
            "queue_health": {
                "queued_runs": len(queued_runs),
                "active_runs": len(blocked_or_running_runs),
                "blocked_tasks": totals["blocked_tasks"],
                "status": "critical"
                if len(queued_runs) >= 20
                else "watch"
                if len(queued_runs) >= 8
                else "healthy",
            },
            "webhook_lag": {
                "pending_events": len(pending_webhooks),
                "max_lag_minutes": webhook_lag_minutes,
                "status": "critical"
                if webhook_lag_minutes >= 60
                else "watch"
                if webhook_lag_minutes >= 15
                else "healthy",
            },
            "replay_backlog": {
                "events": len(replay_backlog),
                "failed_events": sum(
                    1 for event in replay_backlog if event.status in {"failed", "error"}
                ),
                "status": "critical"
                if len(replay_backlog) >= 8
                else "watch"
                if len(replay_backlog) >= 3
                else "healthy",
            },
            "stuck_runs": {
                "count": len(stuck_runs),
                "threshold_minutes": 45,
                "oldest_started_at": min(
                    ((run.started_at or run.created_at) for run in stuck_runs),
                    default=None,
                ),
                "status": "critical" if len(stuck_runs) >= 5 else "watch" if stuck_runs else "healthy",
            },
            "services": [
                {
                    "key": "runtime_queue",
                    "label": "Runtime queue",
                    "status": "critical"
                    if len(queued_runs) >= 20
                    else "watch"
                    if len(queued_runs) >= 8
                    else "healthy",
                    "summary": (
                        f"{len(queued_runs)} queued run(s), "
                        f"{len(blocked_or_running_runs)} active/blocking run(s)."
                    ),
                    "metrics": {
                        "queued_runs": len(queued_runs),
                        "active_runs": len(blocked_or_running_runs),
                    },
                },
                {
                    "key": "github_sync",
                    "label": "GitHub sync",
                    "status": "critical"
                    if webhook_lag_minutes >= 60
                    else "watch"
                    if pending_webhooks
                    else "healthy",
                    "summary": (
                        f"{len(pending_webhooks)} pending webhook event(s), "
                        f"max lag {webhook_lag_minutes} min."
                    ),
                    "metrics": {
                        "pending_events": len(pending_webhooks),
                        "max_lag_minutes": webhook_lag_minutes,
                    },
                },
                {
                    "key": "repo_indexing",
                    "label": "Repo indexing",
                    "status": "critical" if index_failed else "watch" if index_running else "healthy",
                    "summary": f"{len(index_running)} indexing job(s) running, {len(index_failed)} failed.",
                    "metrics": {
                        "running_jobs": len(index_running),
                        "failed_jobs": len(index_failed),
                    },
                },
                {
                    "key": "durable_workflow",
                    "label": "Durable workflow",
                    "status": "critical" if stuck_runs else "healthy",
                    "summary": f"{len(stuck_runs)} stuck run(s) over 45 min threshold.",
                    "metrics": {
                        "stuck_runs": len(stuck_runs),
                        "threshold_minutes": 45,
                    },
                },
                {
                    "key": "model_routing",
                    "label": "Model routing",
                    "status": "critical"
                    if len(provider_unhealthy) >= 2
                    else "watch"
                    if provider_unhealthy
                    else "healthy",
                    "summary": (
                        f"{len(provider_unhealthy)} unhealthy provider(s) "
                        f"out of {len(providers)} configured."
                    ),
                    "metrics": {
                        "unhealthy_providers": len(provider_unhealthy),
                        "providers": len(providers),
                    },
                },
            ],
        }

        totals["cost_usd_30d"] = round(float(totals["cost_usd_30d"]), 4)
        return {
            "generated_at": datetime.now(UTC),
            "totals": totals,
            "execution_policy": policy_defaults,
            "operator_dashboard": operator_dashboard,
            "projects": rows,
        }

    async def portfolio_live_snapshot(self, user: User) -> dict[str, Any]:
        rows = await self.summarize_portfolio(user)
        return {
            "projects": rows,
            "totals": {
                "projects": len(rows),
                "active_runs": sum(int(row.get("active_runs") or 0) for row in rows),
                "open_tasks": sum(int(row.get("open_tasks") or 0) for row in rows),
                "repository_links": sum(int(row.get("repository_links") or 0) for row in rows),
            },
        }

    async def project_live_snapshot(self, user: User, project_id: str) -> dict[str, Any]:
        await self.get_project(user, project_id)
        return await self.repo.get_project_live_snapshot(user.id, project_id)

    async def hierarchy_live_snapshot(self, user: User) -> dict[str, Any]:
        agents = await self.repo.list_agents(user.id, None)
        runs = await self.repo.list_runs(user.id, None)
        return {
            "agents": len(agents),
            "runs": {
                "active": sum(1 for run in runs if run.status in {"queued", "in_progress", "blocked"}),
                "failed": sum(1 for run in runs if run.status == "failed"),
            },
            "latest_run_id": runs[0].id if runs else None,
        }

    async def execution_insights(self, user: User, days: int = 7) -> dict[str, Any]:
        safe_days = max(1, min(int(days or 7), 90))
        since = datetime.now(UTC) - timedelta(days=safe_days)
        rows = await self.repo.aggregate_run_events_by_type_for_owner(user.id, since)
        by_type = {event_type: count for event_type, count in rows}
        tf_payloads = await self.repo.list_tool_failure_payloads_for_owner(user.id, since)
        tool_counts: Counter[str] = Counter()
        for payload in tf_payloads:
            tool = str((payload or {}).get("tool") or "unknown")
            tool_counts[tool] += 1
        tool_failures_by_tool = [{"tool": tool, "count": count} for tool, count in tool_counts.most_common(25)]
        return {
            "since": since,
            "days": safe_days,
            "by_event_type": [{"event_type": event_type, "count": count} for event_type, count in rows],
            "tool_failures_by_tool": tool_failures_by_tool,
            "reopen_events": int(by_type.get("reopened", 0)),
            "brainstorm_round_summary_events": int(by_type.get("brainstorm_round_summary", 0)),
            "blocked_events": int(by_type.get("blocked", 0)),
            "tool_call_failed_events": int(by_type.get("tool_call_failed", 0)),
        }

    async def bootstrap_project_from_text(self, user: User, prompt: str) -> dict[str, Any]:
        del user
        text = str(prompt or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="Prompt is required")
        sentence = text[:200]
        slug_base = re.sub(r"[^a-z0-9]+", "-", sentence.lower()).strip("-")[:40] or "new-project"
        return {
            "approved": False,
            "proposal": {
                "name": sentence[:80].title(),
                "slug": slug_base,
                "description": f"Bootstrapped from natural-language request: {sentence}",
                "goals": [
                    f"Deliver requested outcome: {sentence}",
                    "Establish milestones and measurable acceptance criteria",
                    "Keep cost and risk within project policies",
                ],
                "milestones": [
                    {"title": "Discovery & scope", "description": "Clarify scope and dependencies"},
                    {"title": "Implementation", "description": "Build and validate core functionality"},
                    {"title": "Release readiness", "description": "Review, approvals, and rollout"},
                ],
                "tasks": [
                    {
                        "title": "Draft implementation plan",
                        "task_type": "planning",
                        "priority": "high",
                    },
                    {
                        "title": "Implement core feature set",
                        "task_type": "feature",
                        "priority": "normal",
                    },
                    {
                        "title": "Validation and handoff",
                        "task_type": "review",
                        "priority": "normal",
                    },
                ],
                "team_suggestion": {
                    "manager_role": "manager",
                    "worker_roles": ["specialist", "reviewer"],
                },
            },
        }

    async def apply_bootstrap_project(self, user: User, payload: dict[str, Any]) -> OrchestratorProject:
        create_task = getattr(self, "create_task", None)
        if not callable(create_task):
            raise RuntimeError("apply_bootstrap_project requires a host create_task method")
        proposal = dict(payload.get("proposal") or payload)
        project = await self.create_project(
            user,
            {
                "name": proposal.get("name") or "Bootstrapped Project",
                "slug": proposal.get("slug"),
                "description": proposal.get("description"),
                "goals_markdown": "\n".join(f"- {goal}" for goal in (proposal.get("goals") or [])),
                "settings": {"bootstrap_source": "natural_language"},
            },
        )
        for index, milestone in enumerate((proposal.get("milestones") or [])[:12]):
            await self.create_milestone(
                user,
                project.id,
                title=str(milestone.get("title") or f"Milestone {index + 1}"),
                description=str(milestone.get("description") or ""),
                due_date=None,
                status="open",
                position=index,
            )
        for task in (proposal.get("tasks") or [])[:30]:
            await create_task(
                user,
                project.id,
                {
                    "title": str(task.get("title") or "Bootstrapped task"),
                    "description": str(task.get("description") or ""),
                    "task_type": str(task.get("task_type") or "general"),
                    "priority": str(task.get("priority") or "normal"),
                    "status": "backlog",
                },
            )
        return project

    async def project_budget_projection(self, user: User, days: int = 30) -> dict[str, Any]:
        safe_days = max(1, min(int(days or 30), 365))
        since = datetime.now(UTC) - timedelta(days=safe_days)
        raw = await self.repo.aggregate_run_costs(user.id, since=since)
        total = float(raw.get("total_cost_micros") or 0) / 1_000_000
        burn_daily = total / safe_days
        projected_month = burn_daily * 30.0
        return {
            "days": safe_days,
            "total_cost_usd": round(total, 6),
            "daily_burn_usd": round(burn_daily, 6),
            "projected_monthly_usd": round(projected_month, 6),
            "soft_cap_warning": projected_month > 1000,
            "hard_cap_exceeded": projected_month > 5000,
        }

    def _normalize_project_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(settings or {})
        execution = dict(raw.get("execution") or {})
        execution.setdefault("autonomy_level", "assisted")
        execution.setdefault("manager_agent_id", None)
        execution.setdefault("reviewer_agent_ids", [])
        execution.setdefault("reviewer_chain_mode", "sequential")
        execution.setdefault("provider_config_id", None)
        execution.setdefault("model_name", None)
        execution.setdefault("fallback_model", None)
        execution.setdefault("escalation_rules", [])
        execution.setdefault("routing_mode", "capability_based")
        execution.setdefault("approval_policy", "manager_review")
        execution.setdefault("cost_cap_usd", 250.0)
        execution.setdefault("sibling_load_balance", "queue_depth")
        execution.setdefault("skip_unhealthy_worker_providers", True)
        execution.setdefault("offline_local_only_mode", False)
        execution.setdefault("enforce_project_model_policy", False)
        execution.setdefault("allowed_provider_types", [])
        execution.setdefault("allowed_model_slugs", [])
        blocked_handoff = dict(execution.get("blocked_handoff") or {})
        blocked_handoff.setdefault("mode", "escalation_path")
        blocked_handoff.setdefault("target_agent_id", None)
        blocked_handoff.setdefault("fallback_to_manager", True)
        execution["blocked_handoff"] = blocked_handoff
        sla = dict(execution.get("sla") or {})
        sla.setdefault("enabled", True)
        sla.setdefault("warn_hours_before_due", 24)
        sla.setdefault("escalate_hours_after_due", 0)
        execution["sla"] = sla
        execution.setdefault(
            "approval_gates",
            [
                "post_to_github",
                "open_pr",
                "mark_complete",
                "change_task_ownership",
                "write_memory",
                "use_expensive_model",
                "run_tool",
            ],
        )
        execution.setdefault("expensive_model_cost_per_1k_usd", 0.01)
        normalize_policy_routing = getattr(self, "_normalize_policy_routing", None)
        if callable(normalize_policy_routing):
            execution["policy_routing"] = normalize_policy_routing(execution.get("policy_routing"))
        else:
            policy_routing = execution.get("policy_routing")
            execution["policy_routing"] = (
                dict(policy_routing)
                if isinstance(policy_routing, dict)
                else {"routes": list(policy_routing or [])}
            )
        raw["execution"] = execution
        github = dict(raw.get("github") or {})
        github.setdefault("branch_prefix", "troop/{task_id}-{slug}")
        github.setdefault("enforce_branch_naming", True)
        github.setdefault("auto_post_progress", False)
        github.setdefault("auto_review_on_pr_review", False)
        github.setdefault("auto_activate_review_on_pr_open", True)
        github.setdefault("draft_prs_by_default", True)
        github.setdefault("close_issue_with_manager_summary", True)
        github.setdefault("write_requires_approval", True)
        github.setdefault("sync_labels_to_github", True)
        github.setdefault("sync_assignees_to_github", True)
        github.setdefault("sync_state_to_github", True)
        github.setdefault("sync_milestone_to_github", True)
        github.setdefault("repo_indexing_cadence", "daily")
        github.setdefault("repo_agent_pools", {})
        github.setdefault("outbound_comment_policy", "manual_approval")
        github.setdefault("outbound_comment_trusted_user_ids", [])
        github.setdefault("github_field_locks", {})
        github.setdefault("commit_message_template", "troop: task {task_id} {slug}")
        github.setdefault("respect_branch_protections", True)
        raw["github"] = github
        hitl = dict(raw.get("hitl") or {})
        hitl.setdefault("sandbox_note", "")
        hitl.setdefault("secret_scope", "project_default")
        hitl.setdefault("sandbox_mode", "allow_host_fallback")
        raw["hitl"] = hitl
        mem_defaults = merge_memory_settings({})
        mem_in = dict(raw.get("memory") or {})
        raw["memory"] = {**mem_defaults, **mem_in}
        return raw

    def _normalize_portfolio_execution_policy(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(DEFAULT_PORTFOLIO_EXECUTION_POLICY)
        if settings:
            raw.update({key: value for key, value in settings.items() if value is not None})
        raw["routing_mode"] = str(
            raw.get("routing_mode") or DEFAULT_PORTFOLIO_EXECUTION_POLICY["routing_mode"]
        )
        raw["approval_policy"] = str(
            raw.get("approval_policy") or DEFAULT_PORTFOLIO_EXECUTION_POLICY["approval_policy"]
        )
        raw["repo_indexing_cadence"] = str(
            raw.get("repo_indexing_cadence")
            or DEFAULT_PORTFOLIO_EXECUTION_POLICY["repo_indexing_cadence"]
        )
        try:
            raw["cost_cap_usd"] = round(
                float(
                    raw.get("cost_cap_usd")
                    or DEFAULT_PORTFOLIO_EXECUTION_POLICY["cost_cap_usd"]
                ),
                2,
            )
        except (TypeError, ValueError):
            raw["cost_cap_usd"] = float(DEFAULT_PORTFOLIO_EXECUTION_POLICY["cost_cap_usd"])
        return raw

    def _apply_portfolio_defaults_to_project_settings(
        self,
        settings: dict[str, Any] | None,
        defaults: dict[str, Any],
        *,
        explicit_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        raw = dict(settings or {})
        execution = dict(raw.get("execution") or {})
        github = dict(raw.get("github") or {})
        overrides = dict(raw.get("portfolio_policy_overrides") or {})
        explicit = dict(explicit_settings or {})
        explicit_execution = (
            explicit.get("execution") if isinstance(explicit.get("execution"), dict) else {}
        )
        explicit_github = explicit.get("github") if isinstance(explicit.get("github"), dict) else {}

        for key in ("routing_mode", "approval_policy", "cost_cap_usd"):
            if key in explicit_execution:
                overrides[key] = True
        if "repo_indexing_cadence" in explicit_github:
            overrides["repo_indexing_cadence"] = True

        if not overrides.get("routing_mode"):
            execution["routing_mode"] = defaults["routing_mode"]
        if not overrides.get("approval_policy"):
            execution["approval_policy"] = defaults["approval_policy"]
        if not overrides.get("cost_cap_usd"):
            execution["cost_cap_usd"] = defaults["cost_cap_usd"]
        if not overrides.get("repo_indexing_cadence"):
            github["repo_indexing_cadence"] = defaults["repo_indexing_cadence"]

        raw["execution"] = execution
        raw["github"] = github
        raw["portfolio_policy_overrides"] = overrides
        return raw

    def _project_execution_policy_summary(
        self,
        project: OrchestratorProject,
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        settings = self._normalize_project_settings(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        github = dict(settings.get("github") or {})
        overrides = dict(settings.get("portfolio_policy_overrides") or {})

        def item(key: str, label: str, effective: Any, default: Any) -> dict[str, Any]:
            source = (
                "project_override"
                if overrides.get(key) or effective != default
                else "portfolio_default"
            )
            return {
                "key": key,
                "label": label,
                "effective": effective,
                "default": default,
                "source": source,
                "overridden": source == "project_override",
            }

        items = [
            item(
                "routing_mode",
                "Routing mode",
                execution.get("routing_mode"),
                defaults["routing_mode"],
            ),
            item(
                "approval_policy",
                "Approval policy",
                execution.get("approval_policy"),
                defaults["approval_policy"],
            ),
            item(
                "repo_indexing_cadence",
                "Repo indexing cadence",
                github.get("repo_indexing_cadence"),
                defaults["repo_indexing_cadence"],
            ),
            item(
                "cost_cap_usd",
                "Cost cap",
                execution.get("cost_cap_usd"),
                defaults["cost_cap_usd"],
            ),
        ]
        return {
            "items": items,
            "override_count": sum(1 for entry in items if entry["overridden"]),
        }

    def _merge_nested_project_settings(
        self,
        base: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        out = dict(base)
        for key, value in incoming.items():
            if key == "execution" and isinstance(value, dict):
                out["execution"] = {**(base.get("execution") or {}), **value}
            elif key == "memory" and isinstance(value, dict):
                out["memory"] = {**(base.get("memory") or {}), **value}
            else:
                out[key] = value
        return out

    def _project_execution_settings(self, project: OrchestratorProject) -> dict[str, Any]:
        return self._normalize_project_settings(project.settings_json).get("execution", {})
