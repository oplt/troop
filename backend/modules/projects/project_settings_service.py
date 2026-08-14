"""Project settings normalization and HITL gate configuration."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.hitl_policy import (
    MANDATORY_APPROVAL_GATES,
    normalize_approval_gates,
    normalize_autonomy_level,
)
from backend.modules.identity_access.models import User
from backend.modules.projects.orchestration_models import OrchestratorProject
from backend.modules.projects.project_settings import (
    apply_portfolio_defaults_to_project_settings,
    merge_nested_project_settings,
    normalize_portfolio_execution_policy,
    normalize_project_settings,
    project_execution_policy_summary,
)


class ProjectSettingsMixin:
    async def get_gate_config(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = self._project_execution_settings(project)
        return {
            "autonomy_level": normalize_autonomy_level(settings.get("autonomy_level", "assisted")),
            "approval_gates": normalize_approval_gates(settings.get("approval_gates")),
            "mandatory_approval_gates": sorted(MANDATORY_APPROVAL_GATES),
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
            execution["autonomy_level"] = normalize_autonomy_level(autonomy_level)
        if approval_gates is not None:
            execution["approval_gates"] = normalize_approval_gates(approval_gates)
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.audit_repo.log(
            "orchestration.project.approval_policy.updated",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
            metadata={
                "autonomy_level": execution.get("autonomy_level"),
                "approval_gates": execution.get("approval_gates"),
                "mandatory_approval_gates": sorted(MANDATORY_APPROVAL_GATES),
            },
        )
        await self.db.commit()
        await self.db.refresh(project)
        return await self.get_gate_config(user, project_id)


    def _normalize_project_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        normalize_policy_routing = getattr(self, "_normalize_policy_routing", None)
        return normalize_project_settings(
            settings,
            normalize_policy_routing=normalize_policy_routing,
        )


    def _normalize_portfolio_execution_policy(
        self, settings: dict[str, Any] | None
    ) -> dict[str, Any]:
        return normalize_portfolio_execution_policy(settings)


    def _apply_portfolio_defaults_to_project_settings(
        self,
        settings: dict[str, Any] | None,
        defaults: dict[str, Any],
        *,
        explicit_settings: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return apply_portfolio_defaults_to_project_settings(
            settings,
            defaults,
            explicit_settings=explicit_settings,
        )


    def _project_execution_policy_summary(
        self,
        project: OrchestratorProject,
        defaults: dict[str, Any],
    ) -> dict[str, Any]:
        normalize_policy_routing = getattr(self, "_normalize_policy_routing", None)
        return project_execution_policy_summary(
            project.settings_json or {},
            defaults,
            normalize_policy_routing=normalize_policy_routing,
        )


    def _merge_nested_project_settings(
        self,
        base: dict[str, Any],
        incoming: dict[str, Any],
    ) -> dict[str, Any]:
        return merge_nested_project_settings(base, incoming)


    def _project_execution_settings(self, project: OrchestratorProject) -> dict[str, Any]:
        return self._normalize_project_settings(project.settings_json).get("execution", {})
