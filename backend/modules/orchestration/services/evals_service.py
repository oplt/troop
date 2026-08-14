from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from fastapi import HTTPException

from backend.core.logging import get_logger
from backend.modules.identity_access.models import User
from backend.modules.orchestration.models import (
    EvalRecord,
    ProviderConfig,
)
from backend.modules.orchestration.workflow_templates import BUILTIN_WORKFLOW_TEMPLATES
from backend.modules.team.models import AgentProfile

logger = get_logger(__name__)

from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
)

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)


class OrchestrationEvalsServiceMixin:
    async def pr_assistant_review(self, user: User, payload: dict[str, Any]) -> dict[str, Any]:
        repo = str(payload.get("repository_full_name") or "unknown/repo")
        pr_number = int(payload.get("pr_number") or 0)
        summary = str(payload.get("diff_summary") or payload.get("title") or "")
        findings = []
        if "TODO" in summary or "FIXME" in summary:
            findings.append("Found unresolved TODO/FIXME markers in PR summary.")
        if "secret" in summary.lower() or "token" in summary.lower():
            findings.append("Potential secret handling risk detected; review carefully.")
        verdict = "request_changes" if findings else "approve"
        return {
            "repository_full_name": repo,
            "pr_number": pr_number,
            "verdict": verdict,
            "findings": findings or ["No blocking findings in lightweight assistant review."],
        }

    async def list_custom_workflow_templates(
        self, user: User, project_id: str
    ) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        return list((project.settings_json or {}).get("custom_workflow_templates") or [])

    async def save_custom_workflow_template(
        self, user: User, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        current = list(settings.get("custom_workflow_templates") or [])
        item = {
            "id": str(payload.get("id") or uuid.uuid4()),
            "name": str(payload.get("name") or "Custom workflow"),
            "description": str(payload.get("description") or "Custom project workflow"),
            "stages": list(payload.get("stages") or []),
            "suggested_execution": dict(payload.get("suggested_execution") or {}),
            "forked_from": payload.get("forked_from"),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        current = [c for c in current if str(c.get("id")) != item["id"]]
        current.append(item)
        settings["custom_workflow_templates"] = current
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return item

    async def apply_workflow_template(
        self, user: User, project_id: str, template_id: str
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        requested_id = str(template_id or "").strip()
        template = next(
            (item for item in BUILTIN_WORKFLOW_TEMPLATES if item["id"] == requested_id), None
        )
        if template is None and requested_id.startswith("custom:"):
            custom_id = requested_id.removeprefix("custom:")
            custom = next(
                (
                    item
                    for item in list(
                        (project.settings_json or {}).get("custom_workflow_templates") or []
                    )
                    if str(item.get("id")) == custom_id
                ),
                None,
            )
            if custom is not None:
                template = {
                    "id": requested_id,
                    "name": str(custom.get("name") or "Custom workflow"),
                    "description": str(custom.get("description") or "Custom project workflow"),
                    "suggested_execution": dict(custom.get("suggested_execution") or {}),
                }
        if template is None:
            raise HTTPException(status_code=404, detail="Workflow template not found")

        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        suggested_execution = dict(template.get("suggested_execution") or {})
        execution.update(suggested_execution)
        applied_at = datetime.now(UTC)
        execution["workflow_template_id"] = template["id"]
        execution["workflow_template_name"] = template["name"]
        execution["workflow_template_applied_at"] = applied_at.isoformat()
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.audit_repo.log(
            "orchestration.workflow_template.applied",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
            metadata={"template_id": template["id"], "template_name": template["name"]},
        )
        await self.db.commit()
        await self.db.refresh(project)
        return {
            "project_id": project.id,
            "template": template,
            "applied_execution": dict((project.settings_json or {}).get("execution") or {}),
            "applied_at": applied_at,
        }

    async def list_agent_schedules(self, user: User, project_id: str) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        return list(
            ((project.settings_json or {}).get("execution") or {}).get("agent_schedules") or []
        )

    async def save_agent_schedule(
        self, user: User, project_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        rows = list(execution.get("agent_schedules") or [])
        item = {
            "id": str(payload.get("id") or uuid.uuid4()),
            "agent_id": str(payload.get("agent_id") or ""),
            "cron": str(payload.get("cron") or ""),
            "action": str(payload.get("action") or "triage"),
            "enabled": bool(payload.get("enabled", True)),
        }
        rows = [r for r in rows if str(r.get("id")) != item["id"]]
        rows.append(item)
        execution["agent_schedules"] = rows
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return item

    async def list_eval_records(self, user: User, project_id: str) -> list[EvalRecord]:
        await self.get_project(user, project_id)
        return await self.repo.list_eval_records(project_id)

    async def create_eval_record(
        self, user: User, project_id: str, payload: dict[str, Any]
    ) -> EvalRecord:
        await self.get_project(user, project_id)
        if payload.get("task_id"):
            await self.get_task(user, project_id, payload["task_id"])
        if payload.get("agent_a_id"):
            await self.get_agent(user, payload["agent_a_id"])
        if payload.get("agent_b_id"):
            await self.get_agent(user, payload["agent_b_id"])
        record = await self.repo.create_eval_record(
            project_id=project_id,
            name=payload["name"],
            task_id=payload.get("task_id"),
            agent_a_id=payload.get("agent_a_id"),
            agent_b_id=payload.get("agent_b_id"),
            model_a=payload.get("model_a"),
            model_b=payload.get("model_b"),
        )
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update_eval_record(
        self, user: User, project_id: str, eval_id: str, payload: dict[str, Any]
    ) -> EvalRecord:
        await self.get_project(user, project_id)
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record:
            raise HTTPException(status_code=404, detail="Eval record not found")
        for field in ("winner", "score_a", "score_b", "criteria_met_a", "criteria_met_b", "notes"):
            if field in payload and payload[field] is not None:
                setattr(record, field, payload[field])
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def score_eval_record(self, user: User, project_id: str, eval_id: str) -> EvalRecord:
        await self.get_project(user, project_id)
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record:
            raise HTTPException(status_code=404, detail="Eval record not found")
        run_metrics: dict[str, dict[str, float | int | None]] = {}
        for run_id, side in ((record.run_a_id, "a"), (record.run_b_id, "b")):
            if not run_id:
                continue
            try:
                run = await self.get_run(user, run_id)
            except HTTPException:
                continue
            run_metrics[side] = {
                "latency_ms": run.latency_ms,
                "cost_usd": run.estimated_cost_micros / 1_000_000,
                "tokens": run.token_total,
                "status": run.status,
            }
            if not run.task_id:
                continue
            result = await self.check_task_acceptance(user, project_id, run.task_id)
            passed = result["passed"]
            ratio = sum(1 for c in result["checks"] if c["passed"]) / max(len(result["checks"]), 1)
            score = round(ratio * 100, 1)
            if side == "a":
                record.criteria_met_a = passed
                record.score_a = score
            else:
                record.criteria_met_b = passed
                record.score_b = score
        meta = {**(record.metadata_json or {}), "benchmark_run_metrics": run_metrics}
        a_m = run_metrics.get("a") or {}
        b_m = run_metrics.get("b") or {}
        if a_m and b_m:
            ca, cb = float(a_m.get("cost_usd") or 0), float(b_m.get("cost_usd") or 0)
            la = a_m.get("latency_ms")
            lb = b_m.get("latency_ms")
            la_f = float(la) if la is not None else None
            lb_f = float(lb) if lb is not None else None
            cheaper = "a" if ca < cb else "b" if cb < ca else "tie"
            faster = (
                "a"
                if la_f is not None and lb_f is not None and la_f < lb_f
                else "b"
                if la_f is not None and lb_f is not None and lb_f < la_f
                else "tie"
            )
            meta["benchmark_efficiency"] = {"cheaper_side": cheaper, "faster_side": faster}
        record.metadata_json = meta
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def eval_leaderboard(self, user: User, project_id: str) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        records = await self.repo.list_eval_records(project_id)
        if not records:
            return []
        board: dict[str, dict[str, Any]] = {}

        def ensure(agent_id: str) -> dict[str, Any]:
            item = board.get(agent_id)
            if item is None:
                item = {
                    "agent_id": agent_id,
                    "agent_name": agent_id[:8],
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "total": 0,
                    "score_sum": 0.0,
                    "score_n": 0,
                    "cost_sum": 0.0,
                    "cost_n": 0,
                    "lat_sum": 0.0,
                    "lat_n": 0,
                }
                board[agent_id] = item
            return item

        for record in records:
            pairs = [
                ("a", record.agent_a_id, record.score_a),
                ("b", record.agent_b_id, record.score_b),
            ]
            metrics = (record.metadata_json or {}).get("benchmark_run_metrics") or {}
            for side, agent_id, score in pairs:
                if not agent_id:
                    continue
                row = ensure(agent_id)
                row["total"] += 1
                if score is not None:
                    row["score_sum"] += float(score)
                    row["score_n"] += 1
                side_metrics = metrics.get(side) if isinstance(metrics, dict) else None
                if isinstance(side_metrics, dict):
                    if side_metrics.get("cost_usd") is not None:
                        row["cost_sum"] += float(side_metrics["cost_usd"])
                        row["cost_n"] += 1
                    if side_metrics.get("latency_ms") is not None:
                        row["lat_sum"] += float(side_metrics["latency_ms"])
                        row["lat_n"] += 1
            if record.winner == "a" and record.agent_a_id:
                ensure(record.agent_a_id)["wins"] += 1
                if record.agent_b_id:
                    ensure(record.agent_b_id)["losses"] += 1
            elif record.winner == "b" and record.agent_b_id:
                ensure(record.agent_b_id)["wins"] += 1
                if record.agent_a_id:
                    ensure(record.agent_a_id)["losses"] += 1
            elif record.winner == "tie":
                if record.agent_a_id:
                    ensure(record.agent_a_id)["ties"] += 1
                if record.agent_b_id:
                    ensure(record.agent_b_id)["ties"] += 1

        for agent_id, row in board.items():
            agent = await self.db.get(AgentProfile, agent_id)
            if agent:
                row["agent_name"] = agent.name

        result = []
        for row in board.values():
            total = max(int(row["total"]), 1)
            result.append(
                {
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent_name"],
                    "wins": int(row["wins"]),
                    "losses": int(row["losses"]),
                    "ties": int(row["ties"]),
                    "total": int(row["total"]),
                    "win_rate": round(float(row["wins"]) / total, 4),
                    "avg_score": round(float(row["score_sum"]) / max(int(row["score_n"]), 1), 2),
                    "avg_cost_usd": round(float(row["cost_sum"]) / max(int(row["cost_n"]), 1), 6),
                    "avg_latency_ms": round(float(row["lat_sum"]) / max(int(row["lat_n"]), 1), 2),
                }
            )
        result.sort(
            key=lambda item: (item["win_rate"], item["wins"], item["avg_score"]), reverse=True
        )
        return result

    async def benchmark_historical_issues(
        self,
        user: User,
        project_id: str,
        *,
        agent_a_id: str,
        agent_b_id: str,
        model_a: str | None = None,
        model_b: str | None = None,
        days: int = 60,
        limit: int = 8,
    ) -> dict[str, Any]:
        await self.get_project(user, project_id)
        await self.get_agent(user, agent_a_id)
        await self.get_agent(user, agent_b_id)
        tasks = await self.repo.list_tasks(project_id, limit=0)
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 3650)))
        candidate_tasks = [
            t
            for t in tasks
            if t.github_issue_link_id
            and t.created_at >= since
            and t.status in {"completed", "approved", "synced_to_github", "archived"}
        ][: max(1, min(limit, 50))]
        created: list[dict[str, Any]] = []
        for task in candidate_tasks:
            record = await self.create_eval_record(
                user,
                project_id,
                {
                    "name": f"Historical benchmark: {task.title[:80]}",
                    "task_id": task.id,
                    "agent_a_id": agent_a_id,
                    "agent_b_id": agent_b_id,
                    "model_a": model_a,
                    "model_b": model_b,
                },
            )
            launched = await self.start_benchmark(user, project_id, record.id)
            created.append(
                {"eval_id": record.id, "task_id": task.id, "runs": launched.get("runs", [])}
            )
        return {"created": created, "count": len(created)}

    async def start_benchmark(self, user: User, project_id: str, eval_id: str) -> dict[str, Any]:
        await self.get_project(user, project_id)
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record:
            raise HTTPException(status_code=404, detail="Eval record not found")
        if not record.task_id:
            raise HTTPException(status_code=400, detail="Eval record needs a task_id to benchmark")
        if not record.agent_a_id or not record.agent_b_id:
            raise HTTPException(
                status_code=400,
                detail="Both agent_a_id and agent_b_id are required to start a benchmark",
            )
        source = await self.get_task(user, project_id, record.task_id)
        meta = {
            **(source.metadata_json or {}),
            "benchmark_eval_id": record.id,
            "benchmark_source_task_id": source.id,
        }
        task_a = await self.create_task(
            user,
            project_id,
            {
                "title": f"[Benchmark A] {record.name}",
                "description": source.description,
                "acceptance_criteria": source.acceptance_criteria,
                "priority": source.priority,
                "task_type": source.task_type,
                "status": "backlog",
                "assigned_agent_id": record.agent_a_id,
                "metadata": {**meta, "benchmark_side": "a"},
            },
        )
        task_b = await self.create_task(
            user,
            project_id,
            {
                "title": f"[Benchmark B] {record.name}",
                "description": source.description,
                "acceptance_criteria": source.acceptance_criteria,
                "priority": source.priority,
                "task_type": source.task_type,
                "status": "backlog",
                "assigned_agent_id": record.agent_b_id,
                "metadata": {**meta, "benchmark_side": "b"},
            },
        )
        run_a, _wa = await self.start_task_run(
            user,
            project_id,
            task_a.id,
            {
                "run_mode": "single_agent",
                "worker_agent_id": record.agent_a_id,
                "model_name": record.model_a,
                "input_payload": {"benchmark_eval_id": record.id, "benchmark_side": "a"},
            },
        )
        run_b, _wb = await self.start_task_run(
            user,
            project_id,
            task_b.id,
            {
                "run_mode": "single_agent",
                "worker_agent_id": record.agent_b_id,
                "model_name": record.model_b,
                "input_payload": {"benchmark_eval_id": record.id, "benchmark_side": "b"},
            },
        )
        record.run_a_id = run_a.id
        record.run_b_id = run_b.id
        record.metadata_json = {
            **(record.metadata_json or {}),
            "benchmark_task_a_id": task_a.id,
            "benchmark_task_b_id": task_b.id,
        }
        await self.db.commit()
        await self.db.refresh(record)
        return {
            "eval_id": record.id,
            "runs": [{"side": "a", "run_id": run_a.id}, {"side": "b", "run_id": run_b.id}],
        }

    async def test_run_agent(
        self, user: User, agent_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        agent = await self.get_agent(user, agent_id)
        inheritance = await self.resolve_agent_inheritance(agent)
        provider_config_id = payload.get("provider_config_id")
        provider = None
        if provider_config_id:
            provider = await self.db.get(ProviderConfig, provider_config_id)
        elif agent.provider_config_id:
            provider = await self.db.get(ProviderConfig, agent.provider_config_id)
        else:
            providers = await self.repo.list_providers(user.id, agent.project_id)
            provider = next((p for p in providers if p.is_default), None) or (
                providers[0] if providers else None
            )

        model_name = payload.get("model_name") or (provider.default_model if provider else None)
        task_prompt_parts = [f"Task title: {payload.get('task_title', 'Test task')}"]
        if payload.get("task_description"):
            task_prompt_parts.append(f"Task description: {payload['task_description']}")
        if payload.get("acceptance_criteria"):
            task_prompt_parts.append(f"Acceptance criteria: {payload['acceptance_criteria']}")
        if payload.get("task_labels"):
            task_prompt_parts.append(f"Task labels: {payload['task_labels']}")
        if payload.get("task_metadata"):
            task_prompt_parts.append(
                f"Task metadata: {json.dumps(payload['task_metadata'], indent=2)}"
            )
        base_prompt = "\n\n".join(task_prompt_parts)

        trace: list[dict[str, Any]] = [
            {
                "step": "build_prompt",
                "message": "Built dry-run task prompt.",
                "payload": {"chars": len(base_prompt)},
            },
        ]
        tool_calls = (payload.get("task_metadata") or {}).get("tool_calls", [])
        simulated_tool_results = [
            {
                "tool": call.get("tool"),
                "status": "simulated",
                "result": {"dry_run": True, "arguments": call.get("arguments", {})},
            }
            for call in tool_calls
            if isinstance(call, dict)
        ]
        if simulated_tool_results:
            trace.append(
                {
                    "step": "simulate_tools",
                    "message": "Simulated configured tool calls without side effects.",
                    "payload": {"tool_count": len(simulated_tool_results)},
                }
            )
        final_prompt = "\n\n".join(
            [
                base_prompt,
                "This is a dry-run test. Do not perform external side effects.",
                f"Simulated tool results:\n{json.dumps(simulated_tool_results, indent=2)}"
                if simulated_tool_results
                else "",
            ]
        )
        trace.append(
            {
                "step": "model_request",
                "message": f"Sending dry-run request to model ({model_name or 'local'}).",
                "payload": {"model_name": model_name},
            }
        )
        _, result = await self._execute_with_routing(
            None,
            provider=provider,
            agent=agent,
            system_prompt=inheritance["effective"].get("system_prompt")
            or agent.system_prompt
            or "You are a helpful software agent.",
            user_prompt=final_prompt,
            purpose="agent dry-run",
            append_metrics=False,
        )
        trace.append(
            {
                "step": "model_response",
                "message": "Received dry-run response.",
                "payload": {
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                },
            }
        )
        budget = inheritance["effective"].get("budget") or agent.budget_json or {}
        token_budget = budget.get("token_budget")
        if token_budget and result.total_tokens > int(token_budget):
            trace.append(
                {
                    "step": "budget_check",
                    "level": "warning",
                    "message": f"Token budget ({token_budget}) exceeded.",
                    "payload": {"token_budget": token_budget, "used": result.total_tokens},
                }
            )

        cost_usd = (
            self._estimate_cost_micros(
                provider, result.input_tokens, result.output_tokens, model_name=result.model_name
            )
            / 1_000_000
        )

        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "model_used": result.model_name,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "token_total": result.total_tokens,
            "latency_ms": result.latency_ms,
            "estimated_cost_usd": cost_usd,
            "output_text": result.output_text,
            "trace": trace,
            "simulated_tool_results": simulated_tool_results,
            "inheritance": inheritance,
        }
