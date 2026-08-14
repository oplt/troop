"""Curated multi-agent pattern catalog, benchmarks, and release gating."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.modules.identity_access.models import User
from backend.modules.orchestration.agent_patterns import (
    compute_pattern_advantage,
    get_agent_pattern,
    list_agent_patterns,
)


class OrchestrationAgentPatternServiceMixin:
    def list_agent_patterns_catalog(self) -> list[dict[str, Any]]:
        return list_agent_patterns()

    def _agent_pattern_state(self, project) -> dict[str, Any]:
        execution = dict((project.settings_json or {}).get("execution") or {})
        return dict(execution.get("agent_patterns") or {})

    def _save_agent_pattern_state(self, project, state: dict[str, Any]) -> None:
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        execution["agent_patterns"] = state
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)

    async def list_project_agent_patterns(
        self, user: User, project_id: str
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        state = self._agent_pattern_state(project)
        patterns: list[dict[str, Any]] = []
        for item in list_agent_patterns():
            pid = item["id"]
            entry = dict(state.get(pid) or {})
            patterns.append(
                {
                    "pattern_id": pid,
                    "status": str(entry.get("status") or "disabled"),
                    "eval_ready": bool(entry.get("eval_ready")),
                    "applied_at": entry.get("applied_at"),
                    "enabled_at": entry.get("enabled_at"),
                    "last_eval_id": entry.get("last_eval_id"),
                    "last_advantage": entry.get("last_advantage"),
                }
            )
        return {"project_id": project.id, "patterns": patterns}

    async def apply_agent_pattern(
        self, user: User, project_id: str, pattern_id: str
    ) -> dict[str, Any]:
        pattern = get_agent_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Agent pattern not found")
        project = await self.get_project(user, project_id)
        state = self._agent_pattern_state(project)
        now = datetime.now(UTC)
        state[pattern_id] = {
            **dict(state.get(pattern_id) or {}),
            "status": "eval_pending",
            "eval_ready": False,
            "applied_at": now.isoformat(),
            "pattern_run_mode": pattern["pattern_run_mode"],
            "execution_overlay": dict(pattern.get("execution_overlay") or {}),
        }
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        execution["agent_patterns"] = state
        execution["active_agent_pattern_id"] = pattern_id
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.audit_repo.log(
            "orchestration.agent_pattern.applied",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
            metadata={"pattern_id": pattern_id, "pattern_name": pattern["name"]},
        )
        await self.db.commit()
        await self.db.refresh(project)
        return {
            "project_id": project.id,
            "pattern": pattern,
            "status": "eval_pending",
            "applied_execution": dict((project.settings_json or {}).get("execution") or {}),
        }

    def _pattern_run_payload(
        self,
        *,
        pattern: dict[str, Any],
        side: str,
        eval_id: str,
        agent_id: str,
        model_name: str | None,
    ) -> dict[str, Any]:
        overlay = dict(pattern.get("execution_overlay") or {})
        if side == "a":
            return {
                "run_mode": pattern["baseline_run_mode"],
                "worker_agent_id": agent_id,
                "model_name": model_name,
                "input_payload": {
                    "benchmark_eval_id": eval_id,
                    "benchmark_side": "a",
                    "agent_pattern_id": pattern["id"],
                    "benchmark_role": "baseline",
                },
            }
        payload: dict[str, Any] = {
            "benchmark_eval_id": eval_id,
            "benchmark_side": "b",
            "agent_pattern_id": pattern["id"],
            "benchmark_role": "pattern",
            **{
                k: v
                for k, v in overlay.items()
                if k not in {"agent_pattern_tools", "require_reviewer", "reviewer_agent_ids"}
            },
        }
        if overlay.get("agent_pattern_tools"):
            payload["agent_pattern_tools"] = list(overlay["agent_pattern_tools"])
        if overlay.get("max_specialist_invocations") is not None:
            payload["max_specialist_invocations"] = overlay["max_specialist_invocations"]
        run_mode = pattern["pattern_run_mode"]
        run_payload: dict[str, Any] = {
            "run_mode": run_mode,
            "model_name": model_name,
            "input_payload": payload,
        }
        if run_mode == "single_agent":
            run_payload["worker_agent_id"] = agent_id
        else:
            run_payload["orchestrator_agent_id"] = agent_id
            run_payload["worker_agent_id"] = agent_id
        if overlay.get("require_reviewer"):
            reviewer_ids = overlay.get("reviewer_agent_ids")
            if isinstance(reviewer_ids, list) and reviewer_ids:
                run_payload["reviewer_agent_id"] = str(reviewer_ids[0])
        return run_payload

    async def start_agent_pattern_benchmark(
        self,
        user: User,
        project_id: str,
        pattern_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        pattern = get_agent_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Agent pattern not found")
        task_id = str(payload.get("task_id") or "").strip()
        agent_id = str(payload.get("agent_id") or "").strip()
        if not task_id or not agent_id:
            raise HTTPException(status_code=400, detail="task_id and agent_id are required")
        await self.get_task(user, project_id, task_id)
        await self.get_agent(user, agent_id)
        record = await self.create_eval_record(
            user,
            project_id,
            {
                "name": f"Pattern benchmark: {pattern['name']}",
                "task_id": task_id,
                "agent_a_id": agent_id,
                "agent_b_id": agent_id,
                "model_a": payload.get("model_a"),
                "model_b": payload.get("model_b"),
            },
        )
        record.metadata_json = {
            **(record.metadata_json or {}),
            "benchmark_type": "agent_pattern",
            "agent_pattern_id": pattern_id,
            "run_mode_a": pattern["baseline_run_mode"],
            "run_mode_b": pattern["pattern_run_mode"],
        }
        await self.db.commit()
        launched = await self._start_pattern_benchmark_runs(
            user, project_id, record.id, pattern=pattern
        )
        state = self._agent_pattern_state(await self.get_project(user, project_id))
        entry = dict(state.get(pattern_id) or {})
        entry["status"] = "eval_pending"
        entry["last_eval_id"] = record.id
        state[pattern_id] = entry
        project = await self.get_project(user, project_id)
        self._save_agent_pattern_state(project, state)
        await self.db.commit()
        return {
            "eval_id": record.id,
            "pattern_id": pattern_id,
            "task_id": task_id,
            "runs": launched.get("runs", []),
        }

    async def _start_pattern_benchmark_runs(
        self,
        user: User,
        project_id: str,
        eval_id: str,
        *,
        pattern: dict[str, Any],
    ) -> dict[str, Any]:
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record or not record.task_id:
            raise HTTPException(status_code=404, detail="Eval record not found")
        if not record.agent_a_id:
            raise HTTPException(status_code=400, detail="Eval record needs agent_a_id")
        source = await self.get_task(user, project_id, record.task_id)
        meta = {
            **(source.metadata_json or {}),
            "benchmark_eval_id": record.id,
            "benchmark_source_task_id": source.id,
            "agent_pattern_id": pattern["id"],
        }
        task_a = await self.create_task(
            user,
            project_id,
            {
                "title": f"[Pattern baseline] {record.name}",
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
                "title": f"[Pattern] {record.name}",
                "description": source.description,
                "acceptance_criteria": source.acceptance_criteria,
                "priority": source.priority,
                "task_type": source.task_type,
                "status": "backlog",
                "assigned_agent_id": record.agent_b_id or record.agent_a_id,
                "metadata": {**meta, "benchmark_side": "b"},
            },
        )
        run_a_payload = self._pattern_run_payload(
            pattern=pattern,
            side="a",
            eval_id=record.id,
            agent_id=record.agent_a_id,
            model_name=record.model_a,
        )
        run_b_payload = self._pattern_run_payload(
            pattern=pattern,
            side="b",
            eval_id=record.id,
            agent_id=record.agent_b_id or record.agent_a_id,
            model_name=record.model_b or record.model_a,
        )
        run_a, _wa = await self.start_task_run(user, project_id, task_a.id, run_a_payload)
        run_b, _wb = await self.start_task_run(user, project_id, task_b.id, run_b_payload)
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

    async def score_agent_pattern_eval(
        self, user: User, project_id: str, eval_id: str
    ) -> dict[str, Any]:
        record = await self.score_eval_record(user, project_id, eval_id)
        meta = dict(record.metadata_json or {})
        pattern_id = str(meta.get("agent_pattern_id") or "").strip()
        if not pattern_id:
            raise HTTPException(status_code=400, detail="Eval is not an agent pattern benchmark")
        pattern = get_agent_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Agent pattern not found")
        run_metrics = dict(meta.get("benchmark_run_metrics") or {})
        a_m = run_metrics.get("a") or {}
        b_m = run_metrics.get("b") or {}
        advantage = compute_pattern_advantage(
            score_a=record.score_a,
            score_b=record.score_b,
            criteria_met_a=record.criteria_met_a,
            criteria_met_b=record.criteria_met_b,
            cost_a=float(a_m.get("cost_usd") or 0) if a_m else None,
            cost_b=float(b_m.get("cost_usd") or 0) if b_m else None,
            latency_a=float(a_m["latency_ms"]) if a_m.get("latency_ms") is not None else None,
            latency_b=float(b_m["latency_ms"]) if b_m.get("latency_ms") is not None else None,
        )
        meta["pattern_advantage"] = advantage
        record.metadata_json = meta
        project = await self.get_project(user, project_id)
        state = self._agent_pattern_state(project)
        entry = dict(state.get(pattern_id) or {})
        entry["last_eval_id"] = record.id
        entry["last_advantage"] = advantage
        entry["eval_ready"] = bool(advantage.get("released"))
        entry["status"] = "eval_pending"
        state[pattern_id] = entry
        self._save_agent_pattern_state(project, state)
        await self.db.commit()
        await self.db.refresh(record)
        return {"eval": record, "pattern_id": pattern_id, "advantage": advantage}

    async def enable_agent_pattern(
        self, user: User, project_id: str, pattern_id: str
    ) -> dict[str, Any]:
        pattern = get_agent_pattern(pattern_id)
        if pattern is None:
            raise HTTPException(status_code=404, detail="Agent pattern not found")
        project = await self.get_project(user, project_id)
        state = self._agent_pattern_state(project)
        entry = dict(state.get(pattern_id) or {})
        if not entry.get("eval_ready"):
            raise HTTPException(
                status_code=400,
                detail="Pattern cannot be enabled until evals show quality/latency/cost advantage",
            )
        advantage = entry.get("last_advantage") or {}
        now = datetime.now(UTC)
        entry["status"] = "released"
        entry["enabled_at"] = now.isoformat()
        state[pattern_id] = entry
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        execution["enabled_agent_pattern_id"] = pattern_id
        overlay = dict(pattern.get("execution_overlay") or {})
        execution["agent_pattern_id"] = pattern_id
        execution["agent_pattern_run_mode"] = pattern["pattern_run_mode"]
        for key, value in overlay.items():
            if key != "agent_pattern_tools":
                execution[key] = value
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        self._save_agent_pattern_state(project, state)
        await self.audit_repo.log(
            "orchestration.agent_pattern.enabled",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
            metadata={"pattern_id": pattern_id, "advantage": advantage},
        )
        await self.db.commit()
        await self.db.refresh(project)
        return {
            "project_id": project.id,
            "pattern_id": pattern_id,
            "status": "released",
            "enabled_at": now,
        }
