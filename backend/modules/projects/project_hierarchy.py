"""Project hierarchy policy and reviewer invariants."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.orchestration.hierarchy_policy import (
    apply_policy_to_execution,
    normalize_hierarchy_policy,
    policy_from_execution,
    validate_hierarchy_policy,
)


class ProjectHierarchyMixin:
    async def _project_hierarchy_members(
        self, user: User, project_id: str
    ) -> tuple[list[Any], set[str], dict[str, str]]:
        memberships = await self.repo.list_project_memberships(project_id)
        member_ids = {item.agent_id for item in memberships}
        agents = await self.repo.list_agents(user.id, project_id)
        agent_roles = {item.id: item.role for item in agents}
        supported_roles = {"manager", "team_lead", "specialist", "reviewer"}
        roles = {
            membership.agent_id: (
                membership.role
                if membership.role in supported_roles
                else agent_roles.get(membership.agent_id, membership.role or "specialist")
            )
            for membership in memberships
        }
        return memberships, member_ids, roles

    @staticmethod
    def _ensure_reviewer_chain(
        policy: dict[str, Any], member_ids: set[str], roles: dict[str, str]
    ) -> dict[str, Any]:
        if policy.get("reviewer_agent_ids"):
            return policy
        default_reviewer = next(
            (member_id for member_id in sorted(member_ids) if roles.get(member_id) == "reviewer"),
            None,
        )
        if not default_reviewer:
            return policy
        return normalize_hierarchy_policy({**policy, "reviewer_agent_ids": [default_reviewer]})

    async def _assert_reviewer_membership_invariant(
        self,
        user: User,
        project_id: str,
        membership_id: str,
        *,
        proposed_role: str | None = None,
        removing: bool = False,
    ) -> None:
        memberships, _, roles = await self._project_hierarchy_members(user, project_id)
        target = next((item for item in memberships if item.id == membership_id), None)
        if target is None:
            return
        if removing:
            roles.pop(target.agent_id, None)
        elif proposed_role is not None:
            roles[target.agent_id] = proposed_role
        if roles and not any(role == "reviewer" for role in roles.values()):
            raise HTTPException(
                status_code=422,
                detail="Project must retain at least one reviewer role. Add another reviewer before changing or removing this one.",
            )

    async def get_hierarchy_policy(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        execution = self._normalize_project_settings(project.settings_json or {}).get(
            "execution", {}
        )
        policy = policy_from_execution(execution)
        _, member_ids, roles = await self._project_hierarchy_members(user, project.id)
        return {
            **policy,
            "validation_errors": validate_hierarchy_policy(policy, member_ids, roles),
        }

    async def update_hierarchy_policy(
        self,
        user: User,
        project_id: str,
        policy_updates: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        current = policy_from_execution(execution)
        incoming = {**current, **dict(policy_updates)}
        policy = normalize_hierarchy_policy(incoming)

        _, member_ids, roles = await self._project_hierarchy_members(user, project.id)
        policy = self._ensure_reviewer_chain(policy, member_ids, roles)
        errors = validate_hierarchy_policy(policy, member_ids, roles)
        if errors:
            raise HTTPException(status_code=422, detail={"errors": errors})

        settings["execution"] = apply_policy_to_execution(execution, policy)
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return {**policy, "validation_errors": []}
