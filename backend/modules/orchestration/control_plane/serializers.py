"""Control-plane DTO serializers."""

from __future__ import annotations

from typing import Any

from backend.modules.orchestration.models import (
    AgentProfile,
    ApprovalRequest,
    Brainstorm,
    ModelCapability,
    OrchestratorTask,
    ProviderConfig,
    TaskRun,
)


class ControlPlaneSerializersMixin:
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

    def serialize_task(self, item: OrchestratorTask, approvals: list[ApprovalRequest] | None = None) -> dict[str, Any]:
        """Return the public task contract shared by REST, GraphQL, and workers."""
        return self._serialize_task(item, approvals or [])

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

    def serialize_run(self, item: TaskRun) -> dict[str, Any]:
        """Return the public run contract without exposing private serializer details."""
        return self._serialize_run(item)

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

    def serialize_brainstorm(self, item: Brainstorm) -> dict[str, Any]:
        """Return the public brainstorm contract used by API adapters."""
        return self._serialize_brainstorm(item)

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
