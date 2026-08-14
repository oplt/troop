"""Run cost analytics, simulation, and scorecards."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any

from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.team.models import AgentProfile


class ExecutionRunAnalyticsMixin:
    async def get_run_cost_summary(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        event_micros = await self.repo.sum_run_event_cost_micros_for_run(run.id)
        return {
            "run_id": run.id,
            "project_id": run.project_id,
            "status": run.status,
            "estimated_cost_usd": run.estimated_cost_micros / 1_000_000,
            "event_cost_sum_usd": event_micros / 1_000_000,
            "token_input": run.token_input,
            "token_output": run.token_output,
            "token_total": run.token_total,
            "model_name": run.model_name,
        }

    async def get_runtime_info(self, user: User) -> dict[str, Any]:
        """Non-secret orchestration flags for admin UI (air-gapped / failover toggles)."""
        from backend.modules.orchestration.execution.durable_engine_review import (
            default_evidence_window_days,
            evaluate_durable_engine_triggers,
        )
        from backend.modules.orchestration.execution.durable_execution import durable_backend_status

        window_days = default_evidence_window_days()
        since = datetime.now(UTC) - timedelta(days=window_days)
        evidence = await self.repo.collect_durable_engine_evidence(user.id, since)
        evaluation = evaluate_durable_engine_triggers(evidence)
        backend = durable_backend_status()
        backend["migration_review_verdict"] = evaluation["verdict"]
        backend["migration_triggers_met"] = evaluation["triggers_met"]
        return {
            "orchestration_provider_failover": settings.ORCHESTRATION_PROVIDER_FAILOVER,
            "orchestration_durable_queue_backend": settings.ORCHESTRATION_DURABLE_QUEUE_BACKEND,
            "durable_signal_model": "checkpoint_signal_queue",
            "durable_query_model": "checkpoint_query_snapshot",
            "durable_backend": backend,
            "execution_topology": {
                "api_gateway": "FastAPI",
                "orchestration_service": "modular_monolith",
                "agent_execution_workers": "Celery workers",
                "github_integration": "github queue",
                "model_gateway": "model_gateway queue",
                "observability": "observability queue",
                "cpu_jobs": "cpu queue",
                "system_state": "Postgres",
                "transient_transport": "Redis",
            },
            "realtime_transport": {
                "protocol": "SSE",
                "project_stream": "/orchestration/projects/{project_id}/stream",
                "run_stream": "/orchestration/runs/{run_id}/stream",
                "delivery": "database-polled event cursor",
            },
            "celery_queues": {
                "orchestration": settings.CELERY_TASK_DEFAULT_QUEUE,
                "email": settings.CELERY_EMAIL_QUEUE,
                "github": settings.CELERY_QUEUE_GITHUB,
                "model_gateway": settings.CELERY_QUEUE_MODEL_GATEWAY,
                "observability": settings.CELERY_QUEUE_OBSERVABILITY,
                "cpu": settings.CELERY_QUEUE_CPU,
            },
        }

    async def get_durable_engine_review(
        self,
        user: User,
        *,
        days: int | None = None,
        include_benchmark: bool = False,
    ) -> dict[str, Any]:
        from backend.modules.orchestration.execution.durable_engine_review import (
            build_durable_engine_review,
            default_evidence_window_days,
        )

        window_days = max(7, min(int(days or default_evidence_window_days()), 365))
        since = datetime.now(UTC) - timedelta(days=window_days)
        evidence = await self.repo.collect_durable_engine_evidence(user.id, since)
        recovery_benchmark = None
        if include_benchmark:
            from backend.modules.orchestration.execution.durable_engine_review import (
                benchmark_durable_recovery_side_by_side,
            )

            recovery_benchmark = await benchmark_durable_recovery_side_by_side(self.repo)
        return build_durable_engine_review(
            evidence=evidence,
            recovery_benchmark=recovery_benchmark,
            window_days=window_days,
            owner_id=user.id,
        )

    async def run_durable_recovery_benchmark(self, user: User) -> dict[str, Any]:
        from backend.modules.orchestration.execution.durable_engine_review import (
            benchmark_durable_recovery_side_by_side,
        )

        _ = user
        return await benchmark_durable_recovery_side_by_side(self.repo)

    async def aggregate_cost_analytics(self, user: User, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        raw = await self.repo.aggregate_run_costs(user.id, since=since)
        by_agent = []
        for row in raw["by_agent"]:
            aid = row["agent_id"]
            agent = await self.db.get(AgentProfile, aid) if aid else None
            by_agent.append(
                {
                    "name": agent.name if agent else str(aid)[:8],
                    "cost_usd": row["cost_usd"],
                    "tokens": row["tokens"],
                    "runs": row["runs"],
                }
            )
        by_agent.sort(key=lambda item: item["cost_usd"], reverse=True)
        by_project = sorted(raw["by_project"], key=lambda item: item["cost_usd"], reverse=True)
        by_provider = sorted(raw["by_provider"], key=lambda item: item["cost_usd"], reverse=True)
        total_cost = raw["total_cost_micros"] / 1_000_000
        return {
            "period": f"last_{days}_days",
            "by_project": by_project,
            "by_agent": by_agent,
            "by_task": raw.get("by_task", []),
            "by_provider": by_provider,
            "most_expensive_runs": raw["most_expensive_runs"],
            "total_cost_usd": total_cost,
            "total_tokens": raw["total_tokens"],
        }

    async def run_agent_simulation(
        self,
        user: User,
        agent_id: str,
        *,
        scenarios: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        agent = await self.get_agent(user, agent_id)
        cases = scenarios or [
            {
                "title": "Bug triage",
                "description": "Identify likely root cause and first fix.",
                "acceptance_criteria": "Clear diagnosis + first patch.",
            },
            {
                "title": "Spec drafting",
                "description": "Write a concise API spec with risks.",
                "acceptance_criteria": "Endpoints + risks + rollout plan.",
            },
            {
                "title": "Review response",
                "description": "Review a patch proposal for correctness.",
                "acceptance_criteria": "Find at least one risk and test gap.",
            },
        ]
        results: list[dict[str, Any]] = []
        pass_count = 0
        for idx, case in enumerate(cases, start=1):
            probe = await self.test_run_agent(
                user,
                agent_id,
                {
                    "prompt": str(
                        case.get("description") or case.get("title") or "Simulation task"
                    ),
                    "max_output_tokens": 400,
                    "temperature": 0.2,
                    "simulate_tools": True,
                },
            )
            output = str(probe.get("output_text") or "")
            passed = len(output.strip()) >= 40
            if passed:
                pass_count += 1
            results.append(
                {
                    "scenario_index": idx,
                    "title": str(case.get("title") or f"Scenario {idx}"),
                    "passed": passed,
                    "latency_ms": int(probe.get("latency_ms") or 0),
                    "token_total": int(probe.get("token_total") or 0),
                    "estimated_cost_usd": float(probe.get("estimated_cost_usd") or 0),
                    "output_preview": output[:280],
                }
            )
        avg_cost = sum(float(item["estimated_cost_usd"]) for item in results) / max(len(results), 1)
        avg_latency = sum(int(item["latency_ms"]) for item in results) / max(len(results), 1)
        readiness = (
            "ready"
            if pass_count >= max(1, int(len(results) * 0.67)) and avg_cost < 0.5
            else "needs_tuning"
        )
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "readiness": readiness,
            "pass_rate": round(pass_count / max(len(results), 1), 3),
            "avg_cost_usd": round(avg_cost, 6),
            "avg_latency_ms": round(avg_latency, 1),
            "results": results,
        }

    async def agent_performance_scorecard(self, user: User, days: int = 30) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        runs = await self.repo.list_runs(user.id, None)
        by_agent: dict[str, dict[str, Any]] = {}
        for run in runs:
            if run.created_at < since:
                continue
            agent_id = run.worker_agent_id or run.orchestrator_agent_id
            if not agent_id:
                continue
            row = by_agent.setdefault(
                agent_id,
                {
                    "agent_id": agent_id,
                    "runs": 0,
                    "accepted": 0,
                    "latency": 0,
                    "cost": 0,
                    "escalations": 0,
                    "review_pass": 0,
                    "review_total": 0,
                },
            )
            row["runs"] += 1
            row["latency"] += int(run.latency_ms or 0)
            row["cost"] += float(run.estimated_cost_micros or 0) / 1_000_000
            if run.status == "completed":
                row["accepted"] += 1
            if run.run_mode == "review":
                row["review_total"] += 1
                if run.status == "completed":
                    row["review_pass"] += 1
            evs = await self.repo.list_run_events(run.id)
            row["escalations"] += sum(
                1 for e in evs if e.event_type in {"rule_escalation", "task_escalation"}
            )
        output: list[dict[str, Any]] = []
        for aid, row in by_agent.items():
            agent = await self.db.get(AgentProfile, aid)
            runs_n = max(int(row["runs"]), 1)
            acc_rate = float(row["accepted"]) / runs_n
            avg_cost = float(row["cost"]) / runs_n
            avg_lat = float(row["latency"]) / runs_n
            review_pass_rate = (
                float(row["review_pass"]) / max(int(row["review_total"]), 1)
                if row["review_total"]
                else 1.0
            )
            under = acc_rate < 0.6 or review_pass_rate < 0.6 or avg_cost > 2.0
            output.append(
                {
                    "agent_id": aid,
                    "agent_name": agent.name if agent else aid[:8],
                    "acceptance_rate": round(acc_rate, 3),
                    "avg_cost_usd": round(avg_cost, 6),
                    "avg_latency_ms": round(avg_lat, 2),
                    "review_pass_rate": round(review_pass_rate, 3),
                    "escalation_frequency": round(float(row["escalations"]) / runs_n, 3),
                    "underperforming": under,
                    "suggestion": "Tune prompts/skills and lower-risk routing."
                    if under
                    else "Performance within target.",
                }
            )
        output.sort(
            key=lambda item: (item["underperforming"], -item["acceptance_rate"]), reverse=True
        )
        return output
