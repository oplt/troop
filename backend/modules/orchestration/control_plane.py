from __future__ import annotations

import re
from collections import defaultdict
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.identity_access.models import User
from backend.modules.orchestration.control_plane_runtime import (
    AgentRuntimeProfile,
    build_agent_runtime_profile,
)
from backend.modules.orchestration.models import (
    AgentProfile,
    ApprovalRequest,
    Brainstorm,
    ModelCapability,
    OrchestratorTask,
    ProjectAgentMembership,
    ProviderConfig,
    SkillPack,
    TaskArtifact,
    TaskRun,
)
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.service import OrchestrationService


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"


def _now() -> datetime:
    return datetime.now(UTC)


def _task_is_active(status: str) -> bool:
    return status not in {"completed", "approved", "archived", "synced_to_github"}


@dataclass
class ControlPlaneEvent:
    event_type: str
    project_id: str | None
    member_id: str | None
    task_id: str | None
    run_id: str | None
    status: str | None
    payload: dict[str, Any]
    emitted_at: datetime


class ControlPlanePubSub:
    def __init__(self) -> None:
        self._queues: set[Any] = set()

    async def publish(self, event: ControlPlaneEvent) -> None:
        for queue in list(self._queues):
            await queue.put(event)

    async def subscribe(self):
        import asyncio

        queue: asyncio.Queue[ControlPlaneEvent] = asyncio.Queue()
        self._queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues.discard(queue)


control_plane_pubsub = ControlPlanePubSub()


class HierarchyControlPlaneService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.service = OrchestrationService(db)

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
                    "workload_count": sum(1 for item in agent_tasks if _task_is_active(item.status)),
                    "active_task_count": sum(1 for item in agent_tasks if _task_is_active(item.status)),
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

    async def list_model_profiles(self, user: User, project_id: str | None) -> list[dict[str, Any]]:
        providers = await self.service.list_providers(user, project_id)
        capabilities = await self.service.list_model_capabilities()
        result: list[dict[str, Any]] = []
        for provider in providers:
            if provider.default_model:
                result.append(
                    self._serialize_provider_model(
                        provider,
                        provider.default_model,
                        capabilities,
                        is_fallback=False,
                    )
                )
            if provider.fallback_model:
                result.append(
                    self._serialize_provider_model(
                        provider,
                        provider.fallback_model,
                        capabilities,
                        is_fallback=True,
                    )
                )
        return result

    async def get_runtime_profile(self, user: User, agent_id: str) -> AgentRuntimeProfile:
        agent = await self.service.get_agent(user, agent_id)
        provider = None
        if agent.provider_config_id:
            provider = await self.repo.get_provider(user.id, agent.provider_config_id)
        capabilities = await self.service.list_model_capabilities()
        skills = await self.repo.list_skill_packs()
        return build_agent_runtime_profile(
            agent,
            provider=provider,
            model_capabilities=capabilities,
            skills=skills,
        )

    async def create_team_member(self, user: User, payload: dict[str, Any]) -> AgentProfile:
        name = str(payload["name"]).strip()
        role = str(payload.get("role") or "specialist").strip()
        slug = _slugify(str(payload.get("slug") or f"{name}-{role}"))
        model_profile = dict(payload.get("model_profile") or {})
        agent = await self.service.create_agent(
            user,
            {
                "project_id": payload["project_id"],
                "parent_agent_id": payload.get("parent_member_id"),
                "provider_config_id": model_profile.get("provider_config_id"),
                "name": name,
                "slug": slug,
                "description": payload.get("objective"),
                "role": role,
                "system_prompt": payload.get("instructions") or "",
                "mission_markdown": payload.get("objective") or "",
                "allowed_tools": list(payload.get("tool_access") or []),
                "skills": list(payload.get("skills") or []),
                "model_policy": {
                    "model": model_profile.get("model_slug"),
                    "fallback_model": (payload.get("fallback_model_profile") or {}).get("model_slug"),
                    "routes": payload.get("routing_policy") or [],
                },
                "memory_policy": payload.get("memory_policy") or {"scope": payload.get("memory_scope") or "project"},
                "metadata": {
                    "objective": payload.get("objective") or "",
                    "autonomy_level": payload.get("autonomy_level") or "medium",
                    "approval_policy": payload.get("approval_policy") or "manager_review",
                    "memory_scope": payload.get("memory_scope") or "project",
                },
            },
        )
        await self.service.add_project_agent(
            user,
            payload["project_id"],
            {
                "agent_id": agent.id,
                "role": "manager" if payload.get("is_manager") else "member",
                "is_default_manager": bool(payload.get("is_manager")),
            },
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="member.created",
                project_id=payload["project_id"],
                member_id=agent.id,
                task_id=None,
                run_id=None,
                status="created",
                payload={"name": agent.name},
                emitted_at=_now(),
            )
        )
        return agent

    async def update_team_member(self, user: User, member_id: str, payload: dict[str, Any]) -> AgentProfile:
        existing = await self.service.get_agent(user, member_id)
        model_profile = dict(payload.get("model_profile") or {})
        updates = {
            "parent_agent_id": payload.get("parent_member_id", existing.parent_agent_id),
            "provider_config_id": model_profile.get("provider_config_id", existing.provider_config_id),
            "name": payload.get("name"),
            "role": payload.get("role"),
            "description": payload.get("objective"),
            "system_prompt": payload.get("instructions"),
            "mission_markdown": payload.get("objective"),
            "allowed_tools": payload.get("tool_access"),
            "skills": payload.get("skills"),
            "is_active": payload.get("is_active"),
            "model_policy": {
                **(existing.model_policy_json or {}),
                **({"model": model_profile["model_slug"]} if model_profile.get("model_slug") else {}),
                **(
                    {"fallback_model": (payload.get("fallback_model_profile") or {}).get("model_slug")}
                    if (payload.get("fallback_model_profile") or {}).get("model_slug")
                    else {}
                ),
                **({"routes": payload.get("routing_policy")} if payload.get("routing_policy") is not None else {}),
            },
            "memory_policy": payload.get("memory_policy")
            or {
                **(existing.memory_policy_json or {}),
                **({"scope": payload.get("memory_scope")} if payload.get("memory_scope") else {}),
            },
            "metadata": {
                **(existing.metadata_json or {}),
                **({"objective": payload.get("objective")} if payload.get("objective") is not None else {}),
                **({"autonomy_level": payload.get("autonomy_level")} if payload.get("autonomy_level") else {}),
                **({"approval_policy": payload.get("approval_policy")} if payload.get("approval_policy") else {}),
                **({"memory_scope": payload.get("memory_scope")} if payload.get("memory_scope") else {}),
            },
        }
        clean_updates = {key: value for key, value in updates.items() if value is not None}
        agent = await self.service.update_agent(user, member_id, clean_updates)
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="member.updated",
                project_id=agent.project_id,
                member_id=agent.id,
                task_id=None,
                run_id=None,
                status="updated",
                payload={"name": agent.name},
                emitted_at=_now(),
            )
        )
        return agent

    async def remove_team_member(self, user: User, project_id: str, member_id: str) -> bool:
        membership = await self.repo.get_project_membership(project_id, member_id)
        agent = await self.service.get_agent(user, member_id)
        if not membership:
            raise HTTPException(status_code=404, detail="Project member not found")
        await self.db.delete(membership)
        if agent.project_id == project_id:
            agent.is_active = False
        await self.db.commit()
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="member.removed",
                project_id=project_id,
                member_id=member_id,
                task_id=None,
                run_id=None,
                status="removed",
                payload={"member_id": member_id},
                emitted_at=_now(),
            )
        )
        return True

    async def create_task(self, user: User, payload: dict[str, Any]) -> OrchestratorTask:
        task = await self.service.create_task(
            user,
            payload["project_id"],
            {
                "title": payload["title"],
                "description": payload.get("description"),
                "assigned_agent_id": payload.get("assigned_member_id"),
                "reviewer_agent_id": payload.get("reviewer_member_id"),
                "acceptance_criteria": payload.get("acceptance_criteria"),
                "priority": payload.get("priority") or "normal",
                "task_type": payload.get("task_type") or "general",
                "labels": payload.get("labels") or [],
                "metadata": payload.get("metadata") or {},
            },
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.created",
                project_id=payload["project_id"],
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"title": task.title},
                emitted_at=_now(),
            )
        )
        return task

    async def assign_task(self, user: User, project_id: str, task_id: str, member_id: str) -> OrchestratorTask:
        task = await self.service.update_task(
            user,
            project_id,
            task_id,
            {"assigned_agent_id": member_id, "status": "planned"},
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.assigned",
                project_id=project_id,
                member_id=member_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"title": task.title},
                emitted_at=_now(),
            )
        )
        return task

    async def update_task_status(self, user: User, project_id: str, task_id: str, status: str) -> OrchestratorTask:
        task = await self.service.update_task(user, project_id, task_id, {"status": status})
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.status",
                project_id=project_id,
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"title": task.title},
                emitted_at=_now(),
            )
        )
        return task

    async def request_task_revision(
        self,
        user: User,
        project_id: str,
        task_id: str,
        notes: str,
    ) -> OrchestratorTask:
        await self.service.add_task_comment(user, project_id, task_id, notes)
        task = await self.service.update_task(user, project_id, task_id, {"status": "planned"})
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.revision_requested",
                project_id=project_id,
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"notes": notes},
                emitted_at=_now(),
            )
        )
        return task

    async def approve_task_output(
        self,
        user: User,
        project_id: str,
        task_id: str,
        summary: str | None,
    ) -> OrchestratorTask:
        updates: dict[str, Any] = {"status": "approved"}
        if summary:
            updates["result_summary"] = summary
        task = await self.service.update_task(user, project_id, task_id, updates)
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="task.approved",
                project_id=project_id,
                member_id=task.assigned_agent_id,
                task_id=task.id,
                run_id=None,
                status=task.status,
                payload={"summary": summary or ""},
                emitted_at=_now(),
            )
        )
        return task

    async def launch_task_run(
        self,
        user: User,
        project_id: str,
        task_id: str,
        member_id: str | None,
    ) -> TaskRun:
        run = await self.service.start_task_run(
            user,
            project_id,
            task_id,
            {
                "run_mode": "single_agent",
                "worker_agent_id": member_id,
            },
        )
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="run.started",
                project_id=project_id,
                member_id=member_id,
                task_id=task_id,
                run_id=run.id,
                status=run.status,
                payload={"run_mode": run.run_mode},
                emitted_at=_now(),
            )
        )
        return run

    async def start_brainstorm(
        self,
        user: User,
        project_id: str,
        topic: str,
        participant_ids: list[str],
        task_id: str | None = None,
    ) -> dict[str, Any]:
        brainstorm = await self.service.create_brainstorm(
            user,
            {
                "project_id": project_id,
                "task_id": task_id,
                "topic": topic,
                "participant_agent_ids": participant_ids,
            },
        )
        run = await self.service.start_brainstorm(user, brainstorm.id)
        await control_plane_pubsub.publish(
            ControlPlaneEvent(
                event_type="brainstorm.started",
                project_id=project_id,
                member_id=None,
                task_id=task_id,
                run_id=run.id,
                status=run.status,
                payload={"brainstorm_id": brainstorm.id, "topic": topic},
                emitted_at=_now(),
            )
        )
        return {"brainstorm": brainstorm, "run": run}

    async def list_task_artifacts(self, user: User, project_id: str, task_id: str) -> list[TaskArtifact]:
        await self.service.get_task(user, project_id, task_id)
        return await self.repo.list_task_artifacts(task_id)

    def _derive_member_status(
        self,
        agent: AgentProfile,
        runs: list[TaskRun],
        tasks: list[OrchestratorTask],
        approvals: list[ApprovalRequest],
    ) -> str:
        if not agent.is_active:
            return "disabled"
        if any(run.status == "blocked" for run in runs):
            return "blocked"
        if any(task.status == "needs_review" for task in tasks) or approvals:
            return "needs_review"
        if any(run.status == "in_progress" for run in runs):
            return "running"
        if any(run.status == "queued" for run in runs):
            return "queued"
        return "idle"

    def _serialize_task(self, item: OrchestratorTask, approvals: list[ApprovalRequest]) -> dict[str, Any]:
        return {
            "id": item.id,
            "title": item.title,
            "description": item.description,
            "status": item.status,
            "priority": item.priority,
            "task_type": item.task_type,
            "acceptance_criteria": item.acceptance_criteria,
            "result_summary": item.result_summary,
            "labels": list(item.labels_json or []),
            "updated_at": item.updated_at,
            "pending_approval_count": len([approval for approval in approvals if approval.status == "pending"]),
        }

    def _serialize_run(self, item: TaskRun) -> dict[str, Any]:
        return {
            "id": item.id,
            "status": item.status,
            "run_mode": item.run_mode,
            "model_name": item.model_name,
            "token_total": item.token_total,
            "estimated_cost_micros": item.estimated_cost_micros,
            "latency_ms": item.latency_ms,
            "error_message": item.error_message,
            "created_at": item.created_at,
            "started_at": item.started_at,
            "completed_at": item.completed_at,
        }

    def _serialize_approval(self, item: ApprovalRequest) -> dict[str, Any]:
        return {
            "id": item.id,
            "task_id": item.task_id,
            "run_id": item.run_id,
            "approval_type": item.approval_type,
            "status": item.status,
            "reason": item.reason,
            "created_at": item.created_at,
        }

    def _serialize_brainstorm(self, item: Brainstorm) -> dict[str, Any]:
        return {
            "id": item.id,
            "topic": item.topic,
            "status": item.status,
            "participant_count": getattr(item, "participant_count", 0),
            "current_round": item.current_round,
            "consensus_status": item.consensus_status,
            "updated_at": item.updated_at,
        }

    def _serialize_provider_model(
        self,
        provider: ProviderConfig,
        model_slug: str,
        capabilities: list[ModelCapability],
        *,
        is_fallback: bool,
    ) -> dict[str, Any]:
        capability = next((item for item in capabilities if item.model_slug == model_slug), None)
        return {
            "id": f"{provider.id}:{model_slug}:{'fallback' if is_fallback else 'primary'}",
            "provider_config_id": provider.id,
            "provider_name": provider.name,
            "provider_type": provider.provider_type,
            "model_slug": model_slug,
            "display_name": capability.display_name if capability and capability.display_name else model_slug,
            "temperature": provider.temperature,
            "max_tokens": provider.max_tokens,
            "supports_tools": bool(capability.supports_tools) if capability else False,
            "supports_structured_output": bool(
                (capability.metadata_json or {}).get("supports_structured_output", capability.supports_tools)
            )
            if capability
            else False,
            "max_context_tokens": capability.max_context_tokens if capability else None,
            "is_fallback": is_fallback,
        }

    def _serialize_model_profile(
        self,
        agent: AgentProfile,
        provider: ProviderConfig | None,
        capabilities: list[ModelCapability],
    ) -> dict[str, Any] | None:
        model_slug = str((agent.model_policy_json or {}).get("model") or provider.default_model if provider else "")
        if not model_slug:
            return None
        return self._serialize_provider_model(provider, model_slug, capabilities, is_fallback=False) if provider else {
            "id": f"{agent.id}:{model_slug}:primary",
            "provider_config_id": None,
            "provider_name": None,
            "provider_type": None,
            "model_slug": model_slug,
            "display_name": model_slug,
            "temperature": None,
            "max_tokens": None,
            "supports_tools": False,
            "supports_structured_output": False,
            "max_context_tokens": None,
            "is_fallback": False,
        }

    def _serialize_fallback_model_profile(
        self,
        agent: AgentProfile,
        provider: ProviderConfig | None,
        capabilities: list[ModelCapability],
    ) -> dict[str, Any] | None:
        fallback_model_slug = str((agent.model_policy_json or {}).get("fallback_model") or provider.fallback_model if provider else "")
        if not fallback_model_slug:
            return None
        return self._serialize_provider_model(provider, fallback_model_slug, capabilities, is_fallback=True) if provider else {
            "id": f"{agent.id}:{fallback_model_slug}:fallback",
            "provider_config_id": None,
            "provider_name": None,
            "provider_type": None,
            "model_slug": fallback_model_slug,
            "display_name": fallback_model_slug,
            "temperature": None,
            "max_tokens": None,
            "supports_tools": False,
            "supports_structured_output": False,
            "max_context_tokens": None,
            "is_fallback": True,
        }
