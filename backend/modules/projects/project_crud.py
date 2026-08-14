"""Project CRUD, milestones, decisions, and bootstrap helpers."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from backend.core.cache import (
    get_cached_project_acl,
    invalidate_portfolio_summary_cache,
    invalidate_project_acl_cache_for_project,
    invalidate_project_memory_settings_cache,
    set_cached_project_acl,
)
from backend.modules.identity_access.models import User
from backend.modules.identity_access.workspace_authorization import WorkspaceAuthorizationService
from backend.modules.identity_access.workspace_context import get_active_workspace_id
from backend.modules.orchestration.hierarchy_policy import (
    apply_policy_to_execution,
    policy_from_execution,
    validate_hierarchy_policy,
)
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    ProjectDecision,
    ProjectMilestone,
)


class ProjectCrudMixin:
    async def list_projects(self, user: User):
        return await self.repo.list_projects(user.id)

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
            department_id=payload.get("department_id"),
            name=payload["name"],
            slug=payload["slug"],
            description=payload.get("description"),
            status=payload.get("status", "active"),
            goals_markdown=payload.get("goals_markdown", ""),
            settings_json=self._normalize_project_settings(settings),
            memory_scope=payload.get("memory_scope", "project"),
            knowledge_summary=payload.get("knowledge_summary"),
            knowledge_policy_json=payload.get("knowledge_policy", {}),
            budget_json=payload.get("budget", {}),
            metadata_json=payload.get("metadata", {}),
        )
        await self.audit_repo.log(
            "orchestration.project.created",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
        )
        await self.db.commit()
        await self.db.refresh(project)
        await invalidate_portfolio_summary_cache(user.id)
        execution_settings = (project.settings_json or {}).get("execution") or {}
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

    async def get_project(self, user: User, project_id: str):
        auth = WorkspaceAuthorizationService(self.db)
        ctx = await auth.resolve_active_workspace(user, workspace_id=get_active_workspace_id())

        cached_acl = await get_cached_project_acl(user.id, project_id)
        if cached_acl is False:
            raise HTTPException(status_code=404, detail="Project not found")
        project = await self.repo.get_project_by_id(project_id)
        if not project:
            await set_cached_project_acl(user.id, project_id, allowed=False)
            raise HTTPException(status_code=404, detail="Project not found")
        try:
            auth.authorize_project_read(ctx, project_owner_id=project.owner_id)
        except HTTPException:
            await set_cached_project_acl(user.id, project_id, allowed=False)
            raise HTTPException(status_code=404, detail="Project not found") from None
        if cached_acl is not True:
            await set_cached_project_acl(user.id, project_id, allowed=True)
        return project

    async def update_project(self, user: User, project_id: str, updates: dict[str, Any]):
        project = await self.get_project(user, project_id)
        for field, value in updates.items():
            if field == "settings":
                defaults = await self.get_portfolio_execution_policy(user)
                merged = self._merge_nested_project_settings(
                    project.settings_json or {}, value or {}
                )
                merged = self._apply_portfolio_defaults_to_project_settings(
                    merged,
                    defaults,
                    explicit_settings=value or {},
                )
                normalized = self._normalize_project_settings(merged)
                incoming_execution = (
                    (value or {}).get("execution") if isinstance(value, dict) else None
                )
                if isinstance(incoming_execution, dict):
                    _, member_ids, roles = await self._project_hierarchy_members(user, project.id)
                    policy = policy_from_execution(normalized.get("execution"))
                    policy = self._ensure_reviewer_chain(policy, member_ids, roles)
                    if member_ids:
                        errors = validate_hierarchy_policy(policy, member_ids, roles)
                        if errors:
                            raise HTTPException(status_code=422, detail={"errors": errors})
                        normalized["execution"] = apply_policy_to_execution(
                            dict(normalized.get("execution") or {}), policy
                        )
                project.settings_json = normalized
            else:
                setattr(project, field, value)
        if "settings" in updates:
            await self.audit_repo.log(
                "orchestration.project.settings.updated",
                user_id=user.id,
                resource_type="orchestrator_project",
                resource_id=project.id,
                metadata={
                    "changed_sections": sorted(str(key) for key in (updates.get("settings") or {})),
                    "hitl": "hitl" in (updates.get("settings") or {}),
                },
            )
        await self.db.commit()
        await self.db.refresh(project)
        if "settings" in updates:
            await invalidate_project_memory_settings_cache(project.id)
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
        await invalidate_project_acl_cache_for_project(project_id)
        await invalidate_project_memory_settings_cache(project_id)
        await invalidate_portfolio_summary_cache(user.id)

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

    async def project_live_snapshot(self, user: User, project_id: str) -> dict[str, Any]:
        await self.get_project(user, project_id)
        return await self.repo.get_project_live_snapshot(user.id, project_id)

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
                    {
                        "title": "Implementation",
                        "description": "Build and validate core functionality",
                    },
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

    async def apply_bootstrap_project(
        self, user: User, payload: dict[str, Any]
    ) -> OrchestratorProject:
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
