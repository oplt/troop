"""Project team membership and profile materialization."""

from __future__ import annotations

import re
from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorProject


class ProjectTeamMixin:
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
        template_slugs = [
            str(slug).strip()
            for slug in (team_profile.agent_template_slugs_json or [])
            if str(slug).strip()
        ]
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
                    "knowledge_search",
                }
                fallback_payload = {
                    "project_id": project.id,
                    "parent_template_slug": template.slug,
                    "name": template.name or template.slug,
                    "slug": _unique_slug(f"{project.slug}-{template.slug}"),
                    "description": template.description or "",
                    "role": template.role or "specialist",
                    "capabilities": list(template.capabilities_json or []),
                    "allowed_tools": [
                        tool
                        for tool in (template.allowed_tools_json or [])
                        if tool in allowed_runtime_tools
                    ],
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
        if "role" in updates and updates["role"] is not None:
            await self._assert_reviewer_membership_invariant(
                user,
                project.id,
                membership_id,
                proposed_role=str(updates["role"]),
            )
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
        await self._assert_reviewer_membership_invariant(
            user, project.id, membership_id, removing=True
        )
        await self.db.delete(membership)
        await self.db.commit()

