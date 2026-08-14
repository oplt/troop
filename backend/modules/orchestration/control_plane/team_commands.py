"""Team member CRUD on the control plane."""

from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.orchestration.control_plane.pubsub import (
    ControlPlaneEvent,
    _now,
    _slugify,
    control_plane_pubsub,
)
from backend.modules.orchestration.models import AgentProfile


class ControlPlaneTeamMixin:
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
                    "fallback_model": (payload.get("fallback_model_profile") or {}).get(
                        "model_slug"
                    ),
                    "routes": payload.get("routing_policy") or [],
                },
                "memory_policy": payload.get("memory_policy")
                or {"scope": payload.get("memory_scope") or "project"},
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

    async def update_team_member(
        self, user: User, member_id: str, payload: dict[str, Any]
    ) -> AgentProfile:
        existing = await self.service.get_agent(user, member_id)
        model_profile = dict(payload.get("model_profile") or {})
        updates = {
            "parent_agent_id": payload.get("parent_member_id", existing.parent_agent_id),
            "provider_config_id": model_profile.get(
                "provider_config_id", existing.provider_config_id
            ),
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
                **(
                    {"model": model_profile["model_slug"]}
                    if model_profile.get("model_slug")
                    else {}
                ),
                **(
                    {
                        "fallback_model": (payload.get("fallback_model_profile") or {}).get(
                            "model_slug"
                        )
                    }
                    if (payload.get("fallback_model_profile") or {}).get("model_slug")
                    else {}
                ),
                **(
                    {"routes": payload.get("routing_policy")}
                    if payload.get("routing_policy") is not None
                    else {}
                ),
            },
            "memory_policy": payload.get("memory_policy")
            or {
                **(existing.memory_policy_json or {}),
                **({"scope": payload.get("memory_scope")} if payload.get("memory_scope") else {}),
            },
            "metadata": {
                **(existing.metadata_json or {}),
                **(
                    {"objective": payload.get("objective")}
                    if payload.get("objective") is not None
                    else {}
                ),
                **(
                    {"autonomy_level": payload.get("autonomy_level")}
                    if payload.get("autonomy_level")
                    else {}
                ),
                **(
                    {"approval_policy": payload.get("approval_policy")}
                    if payload.get("approval_policy")
                    else {}
                ),
                **(
                    {"memory_scope": payload.get("memory_scope")}
                    if payload.get("memory_scope")
                    else {}
                ),
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
