"""Run-start budget and rate-limit enforcement."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.modules.orchestration.models import ProviderConfig
from backend.modules.projects.orchestration_models import OrchestratorTask
from backend.modules.team.models import AgentProfile


class ExecutionRunBudgetMixin:
    async def _enforce_orchestration_run_rate_limit(self, user_id: str) -> None:
        limit = settings.ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE
        if limit <= 0:
            return
        # Local dev: SPA + parallel starts + retries exhaust a per-minute cap quickly; prod/staging still enforce.
        if settings.APP_ENV == "dev":
            return
        key = f"rate_limit:orch_run:{user_id}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        if count > limit:
            # Reject without consuming a slot — otherwise every 429 response still bumped the counter (bad UX / lockout).
            await redis_client.decr(key)
            ttl = await redis_client.ttl(key)
            retry_after = max(1, int(ttl)) if ttl is not None and int(ttl) > 0 else 60
            raise HTTPException(
                status_code=429,
                detail=f"Orchestration run rate limit exceeded ({limit} starts per rolling minute). Retry in ~{retry_after}s.",
                headers={"Retry-After": str(retry_after)},
            )

    async def _enforce_agent_token_budget(
        self,
        *,
        owner_id: str,
        agent_id: str | None,
    ) -> None:
        if not agent_id:
            return
        agent = await self.db.get(AgentProfile, agent_id)
        if agent is None:
            return
        # Local providers are non-billable in this stack; do not block run starts on token budgets.
        if await self._is_local_agent_budget_exempt(agent):
            return
        budget = (agent.budget_json or {}).get("token_budget")
        if not budget:
            return
        try:
            cap = int(budget)
        except (TypeError, ValueError):
            return
        since = datetime.now(UTC) - timedelta(days=max(1, settings.AGENT_TOKEN_BUDGET_WINDOW_DAYS))
        used = await self.repo.sum_token_usage_for_agent(owner_id, agent_id, since)
        if used >= cap:
            raise HTTPException(
                status_code=429,
                detail="Agent token budget for the configured window is exhausted.",
            )

    async def _enforce_agent_cost_budget(
        self,
        *,
        owner_id: str,
        agent_id: str | None,
    ) -> None:
        if not agent_id:
            return
        agent = await self.db.get(AgentProfile, agent_id)
        if agent is None:
            return
        if await self._is_local_agent_budget_exempt(agent):
            return
        raw_cap = (agent.budget_json or {}).get("cost_cap_usd")
        if raw_cap is None:
            return
        try:
            cap_usd = float(raw_cap)
        except (TypeError, ValueError):
            return
        if cap_usd <= 0:
            return
        since = datetime.now(UTC) - timedelta(days=max(1, settings.AGENT_TOKEN_BUDGET_WINDOW_DAYS))
        used_micros = await self.repo.sum_estimated_cost_micros_for_agent(owner_id, agent_id, since)
        if used_micros / 1_000_000 >= cap_usd:
            raise HTTPException(
                status_code=429,
                detail="Agent cost budget (cost_cap_usd) for the configured window is exhausted.",
            )

    async def _is_local_agent_budget_exempt(self, agent: AgentProfile) -> bool:
        if agent.provider_config_id:
            provider = await self.db.get(ProviderConfig, agent.provider_config_id)
            if provider is not None and provider.provider_type in {"local", "ollama"}:
                return True
        if agent.project_id:
            providers = await self.repo.list_providers(agent.owner_id, agent.project_id)
            default_provider = next(
                (item for item in providers if item.is_default and item.is_enabled), None
            )
            if default_provider is not None and default_provider.provider_type in {
                "local",
                "ollama",
            }:
                return True
        # When no explicit provider is pinned, orchestration falls back to runtime default.
        return settings.AI_DEFAULT_PROVIDER == "local"

    async def _run_selection_meta(
        self,
        *,
        project_id: str,
        task: OrchestratorTask,
        payload: dict[str, Any],
        execution_settings: dict[str, Any],
        run_mode: str,
        worker_agent_id: str | None,
        orchestrator_agent_id: str | None,
        worker_source: str | None,
        model_name: str | None,
        model_source: str,
    ) -> dict[str, Any]:
        worker_rationale = ""
        if worker_source == "payload":
            worker_rationale = "The worker agent was set explicitly in the run request payload."
        elif worker_source == "pinned":
            agent = await self.db.get(AgentProfile, worker_agent_id) if worker_agent_id else None
            nm = agent.name if agent else "the pinned agent"
            worker_rationale = (
                f"This run uses a pinned worker ({nm}) from task or project execution settings "
                "(or the run payload), after membership and task_filter checks."
            )
        elif worker_source == "task":
            agent = await self.db.get(AgentProfile, worker_agent_id) if worker_agent_id else None
            nm = agent.name if agent else "the assigned agent"
            worker_rationale = f"This run uses the task's assigned worker agent ({nm})."
        elif worker_source == "auto" and worker_agent_id:
            agent = await self.db.get(AgentProfile, worker_agent_id)
            required = set(self._extract_required_tools(task))
            tools = set(agent.allowed_tools_json or []) if agent else set()
            overlap = required & tools
            depths = await self.repo.count_active_runs_by_worker(project_id, [worker_agent_id])
            qd = depths.get(worker_agent_id, 0)
            nm = agent.name if agent else "An agent"
            parts = [
                f"{nm} was auto-selected from this project's eligible agents.",
            ]
            if required:
                parts.append(f"The task lists these required_tools: {', '.join(sorted(required))}.")
                if overlap:
                    parts.append(
                        f"This agent's allowed_tools cover {len(overlap)} of them ({', '.join(sorted(overlap))})."
                    )
                else:
                    parts.append(
                        "No agent covered all required_tools; the lowest queue-depth eligible agent was used."
                    )
            else:
                parts.append(
                    "No required_tools filter; chose lowest active-run load, then name order."
                )
            parts.append(f"Queued depth for this agent was {qd} other in-flight runs.")
            rm = execution_settings.get("routing_mode") or "capability_based"
            sb = execution_settings.get("sibling_load_balance") or "queue_depth"
            su = bool(execution_settings.get("skip_unhealthy_worker_providers", True))
            parts.append(
                f"Project routing_mode={rm}, sibling_load_balance={sb}, "
                f"skip_unhealthy_worker_providers={su}."
            )
            worker_rationale = " ".join(parts)
        elif worker_source == "debate_pair" and worker_agent_id:
            agent = await self.db.get(AgentProfile, worker_agent_id)
            nm = agent.name if agent else "Agent A"
            worker_rationale = (
                f"{nm} leads the debate side as the first seat in the auto-ranked debate pair "
                "(capability overlap, queue depth, then name)."
            )
        elif not worker_agent_id:
            worker_rationale = (
                "No worker agent is attached to this run (orchestration-only / planner mode)."
            )
        else:
            worker_rationale = "Worker routing metadata is unavailable for this run."

        if model_source == "payload":
            model_rationale = "The model name was set explicitly on the run API request."
        elif model_source == "project_execution":
            model_rationale = "Uses execution.model_name from the orchestration project settings (org-wide default for this project)."
        else:
            model_rationale = (
                "No explicit model on the run or project; the worker uses provider defaults or policy routing "
                "when the first LLM call is made."
            )

        return {
            "agent_selection_reason": worker_rationale,
            "model_selection_reason": model_rationale,
            "routing_inputs": {
                "run_mode": run_mode,
                "worker_agent_id": worker_agent_id,
                "orchestrator_agent_id": orchestrator_agent_id,
                "model_name": model_name,
                "worker_source": worker_source,
                "model_source": model_source,
                "required_tools": self._extract_required_tools(task),
                "task_priority": getattr(task, "priority", None),
                "task_due_date": getattr(task, "due_date", None),
            },
            "routing_policy_snapshot": {
                "routing_mode": execution_settings.get("routing_mode") or "capability_based",
                "sibling_load_balance": execution_settings.get("sibling_load_balance")
                or "queue_depth",
                "skip_unhealthy_worker_providers": bool(
                    execution_settings.get("skip_unhealthy_worker_providers", True)
                ),
                "project_model_name": execution_settings.get("model_name"),
            },
            "worker_agent_id_source": worker_source,
            "model_source": model_source,
            "worker_agent_rationale": worker_rationale,
            "model_rationale": model_rationale,
            "run_mode": run_mode,
            "orchestrator_agent_id": orchestrator_agent_id,
            "worker_agent_id": worker_agent_id,
            "model_name": model_name,
            "routing_mode": execution_settings.get("routing_mode") or "capability_based",
            "sibling_load_balance": execution_settings.get("sibling_load_balance") or "queue_depth",
            "skip_unhealthy_worker_providers": bool(
                execution_settings.get("skip_unhealthy_worker_providers", True)
            ),
        }
