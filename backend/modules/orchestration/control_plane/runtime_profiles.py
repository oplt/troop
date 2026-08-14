"""Agent runtime profile resolution."""

from __future__ import annotations

from typing import Any

from backend.modules.identity_access.models import User
from backend.modules.orchestration.control_plane_runtime import (
    AgentRuntimeProfile,
    build_agent_runtime_profile,
)


class ControlPlaneRuntimeProfilesMixin:
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

    async def get_runtime_profile(
        self, user: User, agent_id: str, *, run: Any | None = None
    ) -> AgentRuntimeProfile:
        from backend.modules.orchestration.skill_runtime import load_assigned_skill_versions
        from backend.modules.orchestration.skill_snapshot import get_frozen_skill_payloads

        agent = await self.service.get_agent(user, agent_id)
        provider = None
        if agent.provider_config_id:
            provider = await self.repo.get_provider(user.id, agent.provider_config_id)
        capabilities = await self.service.list_model_capabilities()
        skills = await self.repo.list_skill_packs()
        assigned = None
        if run is not None:
            frozen = get_frozen_skill_payloads(run)
            if frozen:
                assigned = frozen
        if not assigned:
            assigned = await load_assigned_skill_versions(self.service.db, agent.id)
        return build_agent_runtime_profile(
            agent,
            provider=provider,
            model_capabilities=capabilities,
            skills=skills,
            assigned_skill_versions=assigned if assigned is not None else [],
        )
