from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException
from sqlalchemy import select

from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import (
    _provider_type_aliases,
)
from backend.modules.orchestration.models import ModelCapability, ProviderConfig, TaskRun
from backend.modules.orchestration.providers import (
    discover_provider_capabilities,
    execute_prompt,
    test_provider,
)
from backend.modules.orchestration.security import encrypt_secret, mask_secret
from backend.modules.projects.orchestration_models import OrchestratorProject

logger = logging.getLogger(__name__)


class OrchestrationProvidersServiceMixin:
    async def list_providers(self, user: User, project_id: str | None = None):
        return await self.repo.list_providers(user.id, project_id)

    async def create_provider(self, user: User, payload: dict[str, Any]):
        if payload.get("is_default"):
            for provider in await self.repo.list_providers(user.id, payload.get("project_id")):
                provider.is_default = False
        data = dict(payload)
        api_key = data.pop("api_key", None)
        metadata = data.pop("metadata", None) or {}
        provider = await self.repo.create_provider(
            owner_id=user.id,
            project_id=data.get("project_id"),
            name=data["name"],
            provider_type=data["provider_type"],
            base_url=data.get("base_url"),
            encrypted_api_key=encrypt_secret(api_key) if api_key else None,
            api_key_hint=mask_secret(api_key) if api_key else None,
            organization=data.get("organization"),
            default_model=data["default_model"],
            fallback_model=data.get("fallback_model"),
            temperature=data.get("temperature", 0.2),
            max_tokens=data.get("max_tokens", 4096),
            timeout_seconds=data.get("timeout_seconds", 120),
            is_default=bool(data.get("is_default", False)),
            is_enabled=bool(data.get("is_enabled", True)),
            metadata_json=metadata,
        )
        await self.db.commit()
        await self.db.refresh(provider)
        provider_id = provider.id
        try:
            await self._refresh_provider_models(provider)
            await self.db.commit()
        except Exception as exc:
            await self.db.rollback()
            provider = await self.repo.get_provider(user.id, provider_id)
            if provider is not None:
                provider.metadata_json = {
                    **(provider.metadata_json or {}),
                    "last_discovery_error": str(exc),
                }
                await self.db.commit()
        if provider is not None:
            await self.db.refresh(provider)
        return provider

    async def update_provider(self, user: User, provider_id: str, updates: dict[str, Any]):
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        if updates.get("is_default"):
            for item in await self.repo.list_providers(user.id, provider.project_id):
                item.is_default = False
        for field, value in updates.items():
            if field == "api_key":
                provider.encrypted_api_key = encrypt_secret(value) if value else None
                provider.api_key_hint = mask_secret(value)
            elif field == "metadata":
                provider.metadata_json = value
            else:
                setattr(provider, field, value)
        try:
            await self._refresh_provider_models(provider)
        except Exception as exc:
            provider.metadata_json = {
                **(provider.metadata_json or {}),
                "last_discovery_error": str(exc),
            }
        await self._validate_provider_models(provider)
        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def delete_provider(self, user: User, provider_id: str) -> None:
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")

        connected_projects = await self.repo.list_projects_using_provider(user.id, provider_id)
        if provider.project_id and all(project.id != provider.project_id for project in connected_projects):
            project = await self.db.get(OrchestratorProject, provider.project_id)
            if project and project.owner_id == user.id:
                connected_projects.append(project)

        if connected_projects:
            project_names = [project.name for project in connected_projects]
            project_list = ", ".join(project_names)
            raise HTTPException(
                status_code=409,
                detail={
                    "message": (
                        "Provider is connected to project"
                        f"{'s' if len(project_names) != 1 else ''}: {project_list}. "
                        "Remove the project connection before deleting it."
                    ),
                    "projects": project_names,
                },
            )

        await self.repo.delete_provider(provider)
        await self.db.commit()

    async def test_provider(self, user: User, provider_id: str):
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        result = await self._healthcheck_provider(provider)
        await self.db.commit()
        return result

    async def list_provider_models_for_user(self, user: User, provider_id: str) -> dict[str, Any]:
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        models = await self._refresh_provider_models(provider)
        await self.db.commit()
        return {
            "provider_id": provider.id,
            "provider_type": provider.provider_type,
            "models": models,
        }

    async def list_model_capabilities(self) -> list[ModelCapability]:
        return await self.repo.list_model_capabilities()

    async def compare_providers(self, user: User, payload: dict[str, Any]) -> dict[str, Any]:
        provider_a = await self.repo.get_provider(user.id, payload["provider_a_id"])
        provider_b = await self.repo.get_provider(user.id, payload["provider_b_id"])
        if not provider_a or not provider_b:
            raise HTTPException(status_code=404, detail="One or more providers were not found")
        prompt_parts = [f"Task title: {payload['task_title']}"]
        if payload.get("task_description"):
            prompt_parts.append(f"Task description: {payload['task_description']}")
        if payload.get("acceptance_criteria"):
            prompt_parts.append(f"Acceptance criteria: {payload['acceptance_criteria']}")
        if payload.get("task_metadata"):
            prompt_parts.append(
                f"Task metadata: {json.dumps(payload['task_metadata'], indent=2, default=str)}"
            )
        prompt_parts.append(
            "Produce a concise execution proposal with key steps, risks, and expected output."
        )
        final_prompt = "\n\n".join(prompt_parts)
        result_a = await execute_prompt(
            provider_a,
            model_name=payload.get("model_a") or provider_a.default_model,
            system_prompt="You are an AI task execution planner.",
            user_prompt=final_prompt,
        )
        result_b = await execute_prompt(
            provider_b,
            model_name=payload.get("model_b") or provider_b.default_model,
            system_prompt="You are an AI task execution planner.",
            user_prompt=final_prompt,
        )
        return {
            "prompt_preview": final_prompt[:3000],
            "result_a": {
                "provider_id": provider_a.id,
                "provider_name": provider_a.name,
                "provider_type": provider_a.provider_type,
                "model_name": result_a.model_name,
                "latency_ms": result_a.latency_ms,
                "input_tokens": result_a.input_tokens,
                "output_tokens": result_a.output_tokens,
                "token_total": result_a.total_tokens,
                "estimated_cost_usd": self._estimate_cost_micros(
                    provider_a, result_a.input_tokens, result_a.output_tokens, model_name=result_a.model_name
                )
                / 1_000_000,
                "output_text": result_a.output_text,
                "is_healthy": bool(provider_a.is_healthy),
            },
            "result_b": {
                "provider_id": provider_b.id,
                "provider_name": provider_b.name,
                "provider_type": provider_b.provider_type,
                "model_name": result_b.model_name,
                "latency_ms": result_b.latency_ms,
                "input_tokens": result_b.input_tokens,
                "output_tokens": result_b.output_tokens,
                "token_total": result_b.total_tokens,
                "estimated_cost_usd": self._estimate_cost_micros(
                    provider_b, result_b.input_tokens, result_b.output_tokens, model_name=result_b.model_name
                )
                / 1_000_000,
                "output_text": result_b.output_text,
                "is_healthy": bool(provider_b.is_healthy),
            },
        }

    def _estimate_cost_micros(
        self,
        provider: ProviderConfig | None,
        input_tokens: int,
        output_tokens: int,
        *,
        model_name: str | None = None,
    ) -> int:
        # Ollama and built-in local heuristic are not metered like cloud APIs; using generic defaults
        # ($/1k from capability fallbacks) falsely trips expensive-model approval for models like qwen3:4b.
        if provider is not None and str(getattr(provider, "provider_type", None) or "").strip().lower() in {
            "ollama",
            "local",
        }:
            return 0
        capability = None
        if model_name:
            capability = next(
                (
                    item
                    for item in getattr(self, "_cached_model_capabilities", [])
                    if item.model_slug == model_name
                    and (
                        provider is None
                        or item.provider_id == getattr(provider, "id", None)
                        or item.provider_type in _provider_type_aliases(provider.provider_type)
                    )
                ),
                None,
            )
        if capability:
            cost_in = float(capability.cost_per_1k_input)
            cost_out = float(capability.cost_per_1k_output)
        elif provider and provider.metadata_json:
            cost_in = float(provider.metadata_json.get("cost_per_1k_input", 1.0))
            cost_out = float(provider.metadata_json.get("cost_per_1k_output", 2.0))
        else:
            cost_in, cost_out = 1.0, 2.0
        micros = int((input_tokens / 1000.0 * cost_in + output_tokens / 1000.0 * cost_out) * 1_000_000)
        return micros

    async def _model_capabilities(self) -> list[ModelCapability]:
        items = await self.repo.list_model_capabilities()
        self._cached_model_capabilities = items
        return items

    async def _model_capability(self, model_name: str, provider_type: str | None = None) -> ModelCapability | None:
        items = await self._model_capabilities()
        aliases = _provider_type_aliases(provider_type) if provider_type else None
        for item in items:
            if item.model_slug != model_name:
                continue
            if aliases is None or item.provider_type in aliases:
                return item
        return None

    @staticmethod
    def _jsonify(value: Any) -> Any:
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, dict):
            return {k: OrchestrationProvidersServiceMixin._jsonify(v) for k, v in value.items()}
        if isinstance(value, list):
            return [OrchestrationProvidersServiceMixin._jsonify(v) for v in value]
        return value

    def _normalize_discovered_models(self, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        _jsonify = self._jsonify

        normalized: list[dict[str, Any]] = []
        for item in models:
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            normalized.append(
                {
                    "name": name,
                    "size": item.get("size"),
                    "modified_at": _jsonify(item.get("modified_at")),
                    "digest": item.get("digest"),
                    "details": _jsonify(item.get("details") or {}),
                }
            )
        return normalized

    async def _refresh_provider_models(self, provider: ProviderConfig) -> list[dict[str, Any]]:
        try:
            discovered = await discover_provider_capabilities(provider)
        except Exception:
            provider.metadata_json = {
                **(provider.metadata_json or {}),
                "discovered_models": [],
            }
            raise
        normalized = self._normalize_discovered_models(
            [
                {
                    "name": item["model_slug"],
                    "display_name": item.get("display_name"),
                    "modified_at": item.get("last_verified_at"),
                    "details": {
                        "supports_tools": item.get("supports_tools"),
                        "supports_vision": item.get("supports_vision"),
                        "context_window": item.get("context_window"),
                        "max_output_tokens": item.get("max_output_tokens"),
                        "input_cost_per_1k": item.get("input_cost_per_1k"),
                        "output_cost_per_1k": item.get("output_cost_per_1k"),
                        "latency_p50": item.get("latency_p50"),
                        "health_status": item.get("health_status"),
                        "source_for_each_field": item.get("source_for_each_field"),
                        "override_reason": item.get("override_reason"),
                        "source": item.get("source"),
                    },
                }
                for item in discovered
            ]
        )
        provider.metadata_json = {
            **(provider.metadata_json or {}),
            "discovered_models": normalized,
            "last_discovery_error": None,
        }
        existing = {
            item.model_slug: item
            for item in await self.repo.list_model_capabilities(provider_id=provider.id, active_only=False)
        }
        seen: set[str] = set()
        for item in discovered:
            seen.add(item["model_slug"])
            metadata = self._jsonify({
                "context_window": item.get("context_window"),
                "max_output_tokens": item.get("max_output_tokens"),
                "input_cost_per_1k": item.get("input_cost_per_1k"),
                "output_cost_per_1k": item.get("output_cost_per_1k"),
                "input_cost_per_1m": item.get("input_cost_per_1m"),
                "output_cost_per_1m": item.get("output_cost_per_1m"),
                "latency_p50": item.get("latency_p50"),
                "health_status": item.get("health_status"),
                "source_for_each_field": item.get("source_for_each_field") or {},
                "last_verified_at": item.get("last_verified_at"),
                "override_reason": item.get("override_reason"),
                "source": item.get("source"),
                "raw": item.get("raw") or {},
            })
            existing_item = existing.get(item["model_slug"])
            if existing_item:
                existing_item.provider_type = provider.provider_type
                existing_item.display_name = item.get("display_name")
                existing_item.supports_tools = bool(item.get("supports_tools"))
                existing_item.supports_vision = bool(item.get("supports_vision"))
                existing_item.max_context_tokens = int(item.get("context_window") or 0)
                existing_item.cost_per_1k_input = float(item.get("input_cost_per_1k") or 0.0)
                existing_item.cost_per_1k_output = float(item.get("output_cost_per_1k") or 0.0)
                existing_item.metadata_json = metadata
                existing_item.is_active = True
            else:
                await self.repo.create_model_capability(
                    provider_id=provider.id,
                    provider_type=provider.provider_type,
                    model_slug=item["model_slug"],
                    display_name=item.get("display_name"),
                    supports_tools=bool(item.get("supports_tools")),
                    supports_vision=bool(item.get("supports_vision")),
                    max_context_tokens=int(item.get("context_window") or 0),
                    cost_per_1k_input=float(item.get("input_cost_per_1k") or 0.0),
                    cost_per_1k_output=float(item.get("output_cost_per_1k") or 0.0),
                    metadata_json=metadata,
                    is_active=True,
                )
        for model_slug, item in existing.items():
            if model_slug not in seen:
                item.is_active = False
        return normalized

    async def _provider_model_exists(self, provider: ProviderConfig, model_name: str | None) -> bool:
        if not model_name:
            return True
        if model_name in {provider.default_model, provider.fallback_model}:
            return True
        if str(provider.provider_type or "").strip().lower() in {"ollama", "local"}:
            return True
        capability = await self._model_capability(model_name, provider.provider_type)
        if capability:
            return True
        discovered = {
            str(item.get("name") or "").strip()
            for item in (provider.metadata_json or {}).get("discovered_models", [])
        }
        return model_name in discovered

    async def _validate_provider_models(self, provider: ProviderConfig) -> None:
        if not await self._provider_model_exists(provider, provider.default_model):
            raise HTTPException(
                status_code=422,
                detail=f"Default model '{provider.default_model}' is not available for provider type '{provider.provider_type}'.",
            )
        if provider.fallback_model and not await self._provider_model_exists(provider, provider.fallback_model):
            raise HTTPException(
                status_code=422,
                detail=f"Fallback model '{provider.fallback_model}' is not available for provider type '{provider.provider_type}'.",
            )

    async def _healthcheck_provider(self, provider: ProviderConfig) -> dict[str, Any]:
        try:
            await self._refresh_provider_models(provider)
        except Exception:
            pass
        checked_at = datetime.now(UTC)
        try:
            result = await test_provider(provider)
            provider.last_healthcheck_status = result["status"]
            provider.last_healthcheck_latency_ms = int(result["latency_ms"])
            provider.last_healthcheck_at = checked_at
            provider.is_healthy = True
            provider.metadata_json = {
                **(provider.metadata_json or {}),
                "last_discovery_error": None,
            }
            provider.updated_at = checked_at
            return result
        except Exception as exc:
            provider.last_healthcheck_status = "unhealthy"
            provider.last_healthcheck_latency_ms = None
            provider.last_healthcheck_at = checked_at
            provider.is_healthy = False
            provider.metadata_json = {
                **(provider.metadata_json or {}),
                "last_healthcheck_error": str(exc),
            }
            provider.updated_at = checked_at
            return {"status": "unhealthy", "error": str(exc), "latency_ms": None}

    async def run_provider_health_checks(self) -> list[dict[str, Any]]:
        await self._ensure_catalog_seeded()
        providers = await self.repo.list_all_providers(enabled_only=True)
        results: list[dict[str, Any]] = []
        for provider in providers:
            result = await self._healthcheck_provider(provider)
            results.append({"provider_id": provider.id, "provider_name": provider.name, **result})
        await self.db.commit()
        return results

    async def _provider_health_snapshots(
        self, agents: list[AgentProfile]
    ) -> dict[str, tuple[bool, datetime | None]]:
        ids = list({a.provider_config_id for a in agents if a.provider_config_id})
        if not ids:
            return {}
        result = await self.db.execute(
            select(ProviderConfig.id, ProviderConfig.is_healthy, ProviderConfig.last_healthcheck_at).where(
                ProviderConfig.id.in_(ids)
            )
        )
        return {row[0]: (bool(row[1]), row[2]) for row in result.all()}

    async def _resolve_provider_for_run(
        self, run: TaskRun, agent: AgentProfile | None
    ) -> ProviderConfig | None:
        project = await self.db.get(OrchestratorProject, run.project_id)
        execution_settings = self._project_execution_settings(project) if project else {}
        offline_local_only_mode = bool(execution_settings.get("offline_local_only_mode"))

        async def _local_provider_for_project() -> ProviderConfig | None:
            if project is None:
                return None
            providers = await self.repo.list_providers(project.owner_id, project.id)
            return next(
                (
                    item
                    for item in providers
                    if item.is_enabled and item.provider_type in {"ollama", "local"}
                ),
                None,
            )

        if run.provider_config_id:
            provider = await self.db.get(ProviderConfig, run.provider_config_id)
            if provider:
                if offline_local_only_mode and provider.provider_type not in {"ollama", "local"}:
                    return await _local_provider_for_project()
                return provider
        if project is not None:
            if execution_settings.get("provider_config_id"):
                provider = await self.db.get(ProviderConfig, execution_settings["provider_config_id"])
                if provider:
                    if offline_local_only_mode and provider.provider_type not in {"ollama", "local"}:
                        return await _local_provider_for_project()
                    return provider
        if agent and agent.provider_config_id:
            provider = await self.db.get(ProviderConfig, agent.provider_config_id)
            if provider:
                if offline_local_only_mode and provider.provider_type not in {"ollama", "local"}:
                    return await _local_provider_for_project()
                return provider

        # Default provider: prefer the orchestration project the run belongs to, then the agent's
        # home project_id (if any), then user-global (project_id NULL). Agents are often linked to
        # a project only via membership with agent.project_id left unset; listing only by
        # agent.project_id skipped workspace defaults and produced stub LLM output.
        owner_id = project.owner_id if project is not None else (agent.owner_id if agent else None)
        if owner_id:
            scope_ids: list[str | None] = []
            if project is not None:
                scope_ids.append(project.id)
            if agent and agent.project_id and agent.project_id not in scope_ids:
                scope_ids.append(agent.project_id)
            scope_ids.append(None)

            for lookup_project_id in scope_ids:
                providers = await self.repo.list_providers(owner_id, lookup_project_id)
                default = next((item for item in providers if item.is_default), None) or next(
                    (item for item in providers if item.is_enabled), None
                )
                if default:
                    if offline_local_only_mode and default.provider_type not in {"ollama", "local"}:
                        picked = await _local_provider_for_project()
                        if picked:
                            return picked
                        continue
                    return default
        if offline_local_only_mode:
            return await _local_provider_for_project()
        return None
