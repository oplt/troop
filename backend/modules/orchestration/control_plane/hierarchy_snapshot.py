"""Hierarchy read-model aggregation."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.orchestration.control_plane.pubsub import task_is_active
from backend.modules.orchestration.control_plane_runtime import build_agent_runtime_profile
from backend.modules.orchestration.models import ApprovalRequest, OrchestratorTask, TaskRun


class ControlPlaneHierarchyMixin:
    async def get_hierarchy_snapshot(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.service.get_project(user, project_id)
        memberships = await self.service.list_project_agents(user, project_id)
        agents = await self.service.list_agents(user, project_id)
        tasks = await self.service.list_tasks(user, project_id)
        runs = await self.service.list_task_runs(user, project_id)
        approvals = await self.service.list_approvals(user)
        brainstorms = await self.service.list_brainstorms(user, project_id)
        providers = await self.service.list_providers(user, project_id)
        model_capabilities = await self.service.list_model_capabilities()
        skills = await self.repo.list_skill_packs()

        member_agent_ids = {item.agent_id for item in memberships}
        scoped_agents = [item for item in agents if item.id in member_agent_ids]
        from backend.modules.orchestration.skill_runtime import load_assigned_skill_versions

        assigned_by_agent: dict[str, list[dict[str, Any]]] = {}
        for agent in scoped_agents:
            assigned_by_agent[agent.id] = await load_assigned_skill_versions(self.db, agent.id)

        agents_by_id = {item.id: item for item in scoped_agents}
        memberships_by_agent = {item.agent_id: item for item in memberships}
        providers_by_id = {item.id: item for item in providers}
        task_groups: dict[str, list[OrchestratorTask]] = defaultdict(list)
        for task in tasks:
            if task.assigned_agent_id:
                task_groups[task.assigned_agent_id].append(task)
        run_groups: dict[str, list[TaskRun]] = defaultdict(list)
        for run in runs:
            if run.worker_agent_id:
                run_groups[run.worker_agent_id].append(run)
            if run.orchestrator_agent_id and run.orchestrator_agent_id != run.worker_agent_id:
                run_groups[run.orchestrator_agent_id].append(run)
        approvals_by_task: dict[str, list[ApprovalRequest]] = defaultdict(list)
        for approval in approvals:
            if approval.project_id == project_id:
                approvals_by_task[str(approval.task_id or "")].append(approval)

        manager_membership = next((item for item in memberships if item.is_default_manager), None)
        if manager_membership is None and memberships:
            manager_membership = memberships[0]
        manager_id = manager_membership.agent_id if manager_membership else None

        members: list[dict[str, Any]] = []
        for agent in scoped_agents:
            membership = memberships_by_agent.get(agent.id)
            metadata = dict(agent.metadata_json or {})
            agent_tasks = sorted(
                task_groups.get(agent.id, []),
                key=lambda item: (item.position, item.created_at),
            )
            agent_runs = sorted(
                run_groups.get(agent.id, []),
                key=lambda item: item.created_at,
                reverse=True,
            )
            pending_reviews = [
                item for item in approvals if item.project_id == project_id and item.status == "pending"
            ]
            status = self._derive_member_status(agent, agent_runs, agent_tasks, pending_reviews)
            runtime = build_agent_runtime_profile(
                agent,
                provider=providers_by_id.get(agent.provider_config_id or ""),
                model_capabilities=model_capabilities,
                skills=skills,
                assigned_skill_versions=assigned_by_agent.get(agent.id, []),
            )
            members.append(
                {
                    "id": agent.id,
                    "parent_id": None if agent.id == manager_id else (agent.parent_agent_id or manager_id),
                    "membership_id": membership.id if membership else None,
                    "name": agent.name,
                    "role": agent.role,
                    "objective": metadata.get("objective") or agent.description or agent.mission_markdown,
                    "skills": list(agent.skills_json or []),
                    "instructions": agent.system_prompt,
                    "tool_access": list(agent.allowed_tools_json or []),
                    "memory_scope": metadata.get("memory_scope")
                    or (agent.memory_policy_json or {}).get("scope")
                    or "project",
                    "memory_policy": dict(agent.memory_policy_json or {}),
                    "autonomy_level": metadata.get("autonomy_level") or "medium",
                    "approval_policy": metadata.get("approval_policy") or "manager_review",
                    "current_status": status,
                    "workload_count": sum(1 for item in agent_tasks if task_is_active(item.status)),
                    "active_task_count": sum(1 for item in agent_tasks if task_is_active(item.status)),
                    "is_active": agent.is_active,
                    "model_profile": self._serialize_model_profile(
                        agent,
                        providers_by_id.get(agent.provider_config_id or ""),
                        model_capabilities,
                    ),
                    "fallback_model_profile": self._serialize_fallback_model_profile(
                        agent,
                        providers_by_id.get(agent.provider_config_id or ""),
                        model_capabilities,
                    ),
                    "routing_policy": dict((agent.model_policy_json or {}).get("routes", {}))
                    if isinstance((agent.model_policy_json or {}).get("routes", {}), dict)
                    else {"routes": (agent.model_policy_json or {}).get("routes", [])},
                    "tasks": [self._serialize_task(item, approvals_by_task.get(item.id, [])) for item in agent_tasks],
                    "runs": [self._serialize_run(item) for item in agent_runs[:8]],
                    "runtime_profile": runtime.model_dump(),
                }
            )

        members.sort(key=lambda item: (item["id"] != manager_id, item["name"].lower()))
        return {
            "project": {
                "id": project.id,
                "name": project.name,
                "status": project.status,
                "goals_markdown": project.goals_markdown,
                "memory_scope": project.memory_scope,
                "updated_at": project.updated_at,
            },
            "manager_id": manager_id,
            "members": members,
            "pending_approvals": [self._serialize_approval(item) for item in approvals if item.project_id == project_id],
            "brainstorms": [self._serialize_brainstorm(item) for item in brainstorms],
        }

