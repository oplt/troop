from __future__ import annotations

import json
import logging
from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.identity_access.models import User
from backend.modules.orchestration._helpers import BlockedExecution, OPENAI_FAMILY_PROVIDER_TYPES
from backend.modules.orchestration.models import ProviderConfig, TaskRun
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.team.models import AgentProfile


logger = logging.getLogger(__name__)


GLOBAL_POLICY_ROUTING_RULES: list[dict[str, Any]] = [
    {
        "field": "task.labels",
        "operator": "contains",
        "value": "triage",
        "route_to": "cheap_model_slug",
    },
    {
        "field": "task.task_type",
        "operator": "equals",
        "value": "architecture",
        "route_to": "strong_model_slug",
    },
    {
        "field": "project.is_sensitive",
        "operator": "equals",
        "value": True,
        "route_to": "local_model_slug",
    },
]


class OrchestrationRoutingServiceMixin:
    def _global_policy_routing(self) -> dict[str, Any]:
        return {
            "cheap_model_slug": settings.OPENAI_DEFAULT_MODEL or "gpt-4.1-mini",
            "strong_model_slug": "gpt-4.1",
            "local_model_slug": "llama3.2",
            "rules": GLOBAL_POLICY_ROUTING_RULES,
        }

    def _normalize_policy_routing(self, value: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(self._global_policy_routing())
        incoming = dict(value or {})
        raw.update({key: incoming[key] for key in {"cheap_model_slug", "strong_model_slug", "local_model_slug"} if key in incoming})
        if isinstance(incoming.get("rules"), list):
            raw["rules"] = incoming["rules"]
        return raw

    def _normalize_execution_model_policy(self, execution: dict[str, Any]) -> dict[str, Any]:
        return {
            "enforce_project_model_policy": bool(execution.get("enforce_project_model_policy", False)),
            "offline_local_only_mode": bool(execution.get("offline_local_only_mode", False)),
            "allowed_provider_types": [
                str(item).strip().lower()
                for item in (execution.get("allowed_provider_types") or [])
                if str(item).strip()
            ],
            "allowed_model_slugs": [
                str(item).strip()
                for item in (execution.get("allowed_model_slugs") or [])
                if str(item).strip()
            ],
        }

    def _policy_field_value(
        self, project: OrchestratorProject | None, task: OrchestratorTask | None, field: str
    ) -> Any:
        if field == "task.priority":
            return task.priority if task else None
        if field == "task.task_type":
            return task.task_type if task else None
        if field == "task.labels":
            return list(task.labels_json or []) if task else []
        if field == "project.is_sensitive":
            settings_json = project.settings_json if project else {}
            return bool(settings_json.get("is_sensitive") or (settings_json.get("security") or {}).get("is_sensitive"))
        return None

    def _matches_policy_rule(self, actual: Any, operator: str, expected: Any) -> bool:
        if operator == "equals":
            return actual == expected
        if operator == "contains":
            if isinstance(actual, list):
                return expected in actual
            return isinstance(actual, str) and str(expected) in actual
        return False

    async def _policy_routed_target(
        self,
        *,
        project: OrchestratorProject | None,
        task: OrchestratorTask | None,
        provider: ProviderConfig | None,
    ) -> tuple[ProviderConfig | None, str | None, str | None]:
        policy = self._normalize_policy_routing(
            ((project.settings_json or {}).get("execution") or {}).get("policy_routing") if project else None
        )
        for rule in policy.get("rules", []):
            actual = self._policy_field_value(project, task, str(rule.get("field") or ""))
            if not self._matches_policy_rule(actual, str(rule.get("operator") or "equals"), rule.get("value")):
                continue
            route_key = str(rule.get("route_to") or "")
            model_name = policy.get(route_key)
            target_provider = provider
            if route_key == "local_model_slug":
                providers = await self.repo.list_providers(project.owner_id if project else "", project.id if project else None)
                target_provider = next((item for item in providers if item.provider_type == "ollama" and item.is_enabled), provider)
            return target_provider, model_name, route_key
        return provider, None, None

    async def _execute_with_routing(
        self,
        run: TaskRun | None,
        *,
        provider: ProviderConfig | None,
        agent: AgentProfile | None,
        system_prompt: str,
        user_prompt: str,
        response_format: str = "text",
        append_metrics: bool = True,
        purpose: str = "task execution",
    ):
        task = await self.db.get(OrchestratorTask, run.task_id) if run and run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id) if run else None
        target_provider = provider
        run_payload = run.input_payload_json if run else {}
        run_meta = (
            run_payload.get("orchestration_meta")
            if isinstance(run_payload.get("orchestration_meta"), dict)
            else {}
        )
        target_model = run.model_name if run else None
        policy_reason = None
        execution_settings = self._project_execution_settings(project) if project else {}
        exec_model_policy = self._normalize_execution_model_policy(execution_settings)
        enforce_project_model_policy = bool(exec_model_policy["enforce_project_model_policy"])
        offline_local_only_mode = bool(exec_model_policy["offline_local_only_mode"])
        allowed_provider_types = set(exec_model_policy["allowed_provider_types"])
        allowed_model_slugs = set(exec_model_policy["allowed_model_slugs"])
        if not target_model:
            target_provider, policy_model, policy_reason = await self._policy_routed_target(
                project=project,
                task=task,
                provider=provider,
            )
            if policy_model:
                target_model = policy_model
        effective_policy = (agent.model_policy_json if agent else {}) or {}
        if effective_policy.get("model") and (
            not target_model or run_meta.get("model_source") == "project_execution"
        ):
            target_model = str(effective_policy.get("model"))
            if run is not None:
                await self._emit_run_event(
                    run,
                    event_type="agent_model_routed",
                    message=f"Agent model policy selected {target_model} for {purpose}.",
                    payload={"source": "agent.model_policy.model"},
                )
        if not target_model:
            target_model = (
                effective_policy.get("model")
                or (target_provider.default_model if target_provider else None)
            )
        fallback_model = (
            effective_policy.get("fallback_model")
            or run_payload.get("fallback_model")
            or (target_provider.fallback_model if target_provider else None)
        )
        model_candidates = []
        for candidate in [target_model, fallback_model]:
            if candidate and candidate not in model_candidates:
                model_candidates.append(candidate)
        if not model_candidates:
            model_candidates = [None]
        if offline_local_only_mode and not target_model:
            model_candidates = [self._global_policy_routing().get("local_model_slug"), None]
        if enforce_project_model_policy and allowed_model_slugs:
            model_candidates = [
                candidate for candidate in model_candidates if candidate is None or candidate in allowed_model_slugs
            ]
            if not model_candidates:
                raise HTTPException(
                    status_code=422,
                    detail="No candidate model is allowed by execution.allowed_model_slugs.",
                )
        if not settings.ORCHESTRATION_PROVIDER_FAILOVER:
            model_candidates = model_candidates[:1]
        if (
            run is not None
            and project is not None
            and self.action_requires_approval(project, "use_expensive_model")
            and target_provider is not None
            and model_candidates
        ):
            expensive_threshold = float(
                execution_settings.get("expensive_model_cost_per_1k_usd") or 0.01
            )
            first_candidate = model_candidates[0]
            if first_candidate:
                est_for_1k = self._estimate_cost_micros(
                    target_provider, 1000, 1000, model_name=first_candidate
                ) / 1_000_000
                if est_for_1k >= expensive_threshold:
                    approval = await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id if task else None,
                        run_id=run.id,
                        issue_link_id=task.github_issue_link_id if task else None,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="expensive_model_use",
                        status="pending",
                        payload_json={
                            "model_name": first_candidate,
                            "estimated_cost_per_1k_usd": est_for_1k,
                            "threshold_per_1k_usd": expensive_threshold,
                            "purpose": purpose,
                        },
                    )
                    await self.db.commit()
                    raise BlockedExecution(
                        f"Model '{first_candidate}' exceeds expensive-model threshold and requires approval "
                        f"(approval_id={approval.id})."
                    )
        if policy_reason:
            if run is not None:
                await self._emit_run_event(
                    run,
                    event_type="policy_routed",
                    message=f"Policy routing selected {target_model} for {purpose}.",
                    payload={"reason": policy_reason, "model_name": target_model},
                )

        provider_chain: list[ProviderConfig | None] = [target_provider]
        if (
            settings.ORCHESTRATION_PROVIDER_FAILOVER
            and not settings.ORCHESTRATION_OFFLINE_MODE
            and project
            and run
            and target_provider is not None
        ):
            seen_ids = {target_provider.id}
            for p in await self.repo.list_providers(project.owner_id, project.id):
                if p.is_enabled and p.id not in seen_ids:
                    seen_ids.add(p.id)
                    provider_chain.append(p)
        if offline_local_only_mode:
            provider_chain = [
                p for p in provider_chain if p is None or p.provider_type in {"ollama", "local"}
            ]
            if not provider_chain:
                provider_chain = [None]
        if enforce_project_model_policy and allowed_provider_types:
            provider_chain = [
                p
                for p in provider_chain
                if p is None or p.provider_type.lower() in allowed_provider_types
            ]
            if not provider_chain:
                raise HTTPException(
                    status_code=422,
                    detail="No provider satisfies execution.allowed_provider_types policy.",
                )

        outer_errors: list[str] = []

        async def _attempt_llm(
            tp: ProviderConfig | None, cands: list[str | None]
        ) -> tuple[ProviderConfig | None, Any] | None:
            errors: list[str] = []
            for index, candidate in enumerate(cands):
                if tp and not await self._provider_model_exists(tp, candidate):
                    errors.append(f"Model '{candidate}' is not available on provider '{tp.name}'.")
                    continue
                if tp and index == 0 and tp.is_healthy is False and len(cands) > 1:
                    if run is not None:
                        await self._emit_run_event(
                            run,
                            event_type="model_fallback",
                            level="warning",
                            message=f"Primary model skipped because provider {tp.name} is unhealthy.",
                            payload={"provider_id": tp.id, "model_name": candidate},
                        )
                    errors.append(f"Skipped unhealthy provider {tp.name}")
                    continue
                try:
                    result = await execute_prompt(
                        tp,
                        model_name=candidate,
                        system_prompt=system_prompt,
                        user_prompt=user_prompt,
                        response_format=response_format,
                    )
                except Exception as exc:
                    errors.append(str(exc))
                    if index + 1 < len(cands):
                        if run is not None:
                            await self._emit_run_event(
                                run,
                                event_type="model_fallback",
                                level="warning",
                                message=f"Model {candidate} failed; trying fallback.",
                                payload={"error": str(exc), "failed_model": candidate},
                            )
                        continue
                    outer_errors.extend(errors)
                    return None
                if run is not None:
                    run.model_name = result.model_name
                    run.provider_config_id = tp.id if tp else None
                if append_metrics and run is not None:
                    await self._apply_result_metrics(
                        run,
                        tp,
                        [result],
                        agent=agent,
                        append=True,
                    )
                if run is not None:
                    micros = self._estimate_cost_micros(
                        tp,
                        result.input_tokens,
                        result.output_tokens,
                        model_name=result.model_name,
                    )
                    await self._emit_run_event(
                        run,
                        event_type="llm_response",
                        message=(
                            f"Model response ({result.model_name or 'unknown'}): "
                            f"{result.input_tokens} in / {result.output_tokens} out tokens ({purpose})"
                        ),
                        payload={
                            "purpose": purpose,
                            "model_name": result.model_name,
                            "latency_ms": result.latency_ms,
                        },
                        input_tokens=result.input_tokens,
                        output_tokens=result.output_tokens,
                        cost_usd_micros=micros,
                    )
                if index > 0:
                    if run is not None:
                        await self._emit_run_event(
                            run,
                            event_type="model_fallback_used",
                            message=f"Fallback model {result.model_name} completed {purpose}.",
                            payload={"attempt_errors": errors[:-1] if len(errors) > 1 else errors},
                        )
                return tp, result
            outer_errors.extend(errors)
            return None

        for prov_index, current_provider in enumerate(provider_chain):
            target_provider = current_provider
            if prov_index == 0:
                candidate_list = model_candidates
            else:
                tm2 = (run.model_name if run else None) or effective_policy.get("model") or (
                    target_provider.default_model if target_provider else None
                )
                fb2 = (
                    effective_policy.get("fallback_model")
                    or run_payload.get("fallback_model")
                    or (target_provider.fallback_model if target_provider else None)
                )
                candidate_list = []
                for c in [tm2, fb2]:
                    if c and c not in candidate_list:
                        candidate_list.append(c)
                if not candidate_list:
                    candidate_list = [None]
                if not settings.ORCHESTRATION_PROVIDER_FAILOVER:
                    candidate_list = candidate_list[:1]

            pair = await _attempt_llm(target_provider, candidate_list)
            if pair:
                return pair[0], pair[1]
            if prov_index + 1 < len(provider_chain) and run is not None:
                await self._emit_run_event(
                    run,
                    event_type="provider_failover",
                    level="warning",
                    message="Provider models failed; attempting failover provider from the project chain.",
                    payload={
                        "failed_provider_id": current_provider.id if current_provider else None,
                    },
                )

        raise HTTPException(status_code=502, detail="; ".join(outer_errors) or "No provider model available")

    def _extract_required_tools(self, task: OrchestratorTask | None) -> list[str]:
        if task is None:
            return []
        metadata = task.metadata_json or {}
        required = [str(item).strip() for item in metadata.get("required_tools", []) if str(item).strip()]
        label_required = [
            label.split("tool:", 1)[1].strip()
            for label in (task.labels_json or [])
            if isinstance(label, str) and label.startswith("tool:")
        ]
        combined = []
        for item in [*required, *label_required]:
            if item and item not in combined:
                combined.append(item)
        return combined

    def _agent_task_filter_patterns(self, agent: AgentProfile) -> list[str]:
        meta = agent.metadata_json or {}
        raw = meta.get("task_filters") or []
        if isinstance(raw, str):
            return [raw.strip()] if raw.strip() else []
        return [str(x).strip() for x in raw if str(x).strip()]

    def _task_matches_filter_pattern(self, task: OrchestratorTask, pattern: str) -> bool:
        if not pattern:
            return False
        labels = task.labels_json or []
        label_blob = " ".join(str(x) for x in labels) if isinstance(labels, list) else ""
        hay = " ".join(
            [
                task.title or "",
                task.description or "",
                task.task_type or "",
                label_blob,
            ]
        ).lower()
        try:
            if any(char in pattern for char in r"^$[]().*+?{}\|"):
                return re.search(pattern, hay, re.IGNORECASE) is not None
        except re.error:
            return pattern.lower() in hay
        return pattern.lower() in hay

    def _agent_eligible_for_task_by_filters(self, agent: AgentProfile, task: OrchestratorTask) -> bool:
        patterns = self._agent_task_filter_patterns(agent)
        if not patterns:
            return True
        return any(self._task_matches_filter_pattern(task, p) for p in patterns)

    def _required_tools_satisfied(self, agent: AgentProfile | None, required: list[str]) -> bool:
        if not required:
            return True
        if agent is None:
            return False
        allowed = set(agent.allowed_tools_json or [])
        return all(tool in allowed for tool in required)

    def _tool_allowed_for_agent_permissions(self, tool_name: str, agent: AgentProfile | None) -> None:
        if not agent:
            return
        perm = str((agent.model_policy_json or {}).get("permissions") or "code-write")
        if perm not in self._PERMISSION_RANK:
            return
        if perm == "merge-blocked" and tool_name in self._MERGE_BLOCKED_TOOLS:
            raise BlockedExecution(
                f"Tool '{tool_name}' is blocked for merge-blocked agents (no PR/label mutations)."
            )
        need = self._TOOL_MIN_PERMISSION.get(tool_name, "code-write")
        need_rank = self._PERMISSION_RANK.get(need, 3)
        have_rank = self._PERMISSION_RANK.get(perm, 3)
        if have_rank < need_rank:
            raise BlockedExecution(
                f"Tool '{tool_name}' requires permission at least '{need}' (agent is '{perm}')."
            )

    async def _candidate_workers(
        self, project_id: str, *, manager=None, explicit_worker=None, task: OrchestratorTask | None = None
    ) -> list:
        if explicit_worker is not None:
            return [explicit_worker]
        memberships = await self.repo.list_project_memberships(project_id)
        allowed_agent_ids: set[str] | None = None
        if task is not None:
            repo_pool = await self._task_repo_pool_config(task)
            configured = [str(item).strip() for item in (repo_pool.get("worker_agent_ids") or []) if str(item).strip()]
            if configured:
                allowed_agent_ids = set(configured)
        workers = []
        for membership in memberships:
            agent = await self._load_agent_for_run(membership.agent_id)
            if agent is None or not agent.is_active:
                continue
            if allowed_agent_ids is not None and agent.id not in allowed_agent_ids:
                continue
            if manager and not self._is_agent_descendant(manager, agent) and manager.id != agent.id:
                continue
            workers.append(agent)
        return workers

    async def _route_sub_tasks_to_agents(
        self,
        project_id: str,
        sub_tasks: list[dict[str, Any]],
        candidate_workers: list,
        *,
        manager: AgentProfile | None = None,
        parent_task: OrchestratorTask | None = None,
    ) -> list[dict[str, Any]]:
        routed = []
        project = await self.db.get(OrchestratorProject, project_id)
        exe = self._project_execution_settings(project) if project else {}
        workers = list(candidate_workers)
        if manager:
            allowed = [w for w in workers if self._delegation_edge_allowed(manager, w)]
            if allowed:
                workers = allowed
        queue_depths = await self.repo.count_active_runs_by_worker(
            project_id,
            [agent.id for agent in workers],
        ) if workers else {}
        for item in self._normalize_subtask_graph(sub_tasks, parent_task=parent_task):
            required_capabilities = {
                str(value).strip()
                for value in item.get("required_capabilities", []) + item.get("required_tools", [])
                if str(value).strip()
            }
            chosen = None
            ranked: list[AgentProfile] = []
            if workers:
                shadow = SimpleNamespace(
                    id=str(item.get("title") or item.get("id") or "subtask"),
                    metadata_json={"required_tools": list(item.get("required_tools") or [])},
                    labels_json=[],
                    title=str(item.get("title") or ""),
                    description=str(item.get("description") or ""),
                    task_type="general",
                    due_date=parent_task.due_date if parent_task else None,
                )
                ranked = await self._rank_worker_candidates(
                    project_id,
                    shadow,
                    workers,
                    execution_settings=exe,
                )
                if required_capabilities:
                    for agent in ranked:
                        if required_capabilities.intersection(set(agent.capabilities_json or [])):
                            chosen = agent
                            break
                else:
                    chosen = ranked[0] if ranked else None
            matched_caps = (
                sorted(required_capabilities.intersection(set(chosen.capabilities_json or [])))
                if chosen is not None
                else []
            )
            routing_reason = (
                f"matched capabilities {matched_caps} with queue depth {queue_depths.get(chosen.id, 0)}"
                if chosen is not None and matched_caps
                else f"best available worker with queue depth {queue_depths.get(chosen.id, 0)}"
                if chosen is not None
                else "no capable worker available"
            )
            routed.append(
                {
                    **item,
                    "assigned_agent_id": chosen.id if chosen else None,
                    "assigned_agent_name": chosen.name if chosen else None,
                    "queue_depth": queue_depths.get(chosen.id, 0) if chosen else None,
                    "routing_reason": routing_reason,
                    "selected_provider_config_id": chosen.provider_config_id if chosen else None,
                    "selected_model_name": (
                        str((chosen.model_policy_json or {}).get("model") or "").strip() or None
                        if chosen is not None
                        else None
                    ),
                }
            )
        return routed

    def _partition_subtasks(self, sub_tasks: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        parallel = [item for item in sub_tasks if item.get("parallelizable")]
        sequential = [item for item in sub_tasks if not item.get("parallelizable")]
        return parallel, sequential

    async def _execute_subtask_branch(
        self,
        run: TaskRun,
        child_run: TaskRun,
        provider: ProviderConfig | None,
        sub_task: dict[str, Any],
        *,
        project: OrchestratorProject,
        manager,
    ) -> dict[str, Any]:
        worker = await self._load_agent_for_run(sub_task.get("assigned_agent_id"))
        await self._emit_run_event(
            run,
            event_type="branch_started",
            message=f"Starting delegated branch '{sub_task.get('title', 'Untitled')}'.",
            payload={
                "child_run_id": child_run.id,
                "branch_id": sub_task.get("branch_id"),
                "branch_title": sub_task.get("title"),
                "assigned_agent_id": sub_task.get("assigned_agent_id"),
                "trace": self._workflow_trace_payload(run),
            },
        )
        child_run.status = "in_progress"
        child_run.started_at = datetime.now(UTC)
        if worker is None:
            child_run.status = "blocked"
            child_run.error_message = "no_capable_worker"
            await self._emit_run_event(
                run,
                event_type="branch_unassigned",
                level="warning",
                message=f"No capable worker found for sub-task '{sub_task.get('title', 'Untitled')}'.",
                payload=sub_task,
            )
            return {
                **sub_task,
                "status": "blocked",
                "reason": "no_capable_worker",
                "blocker_reason": "No capable worker found.",
                "child_run_id": child_run.id,
            }
        branch_plan = {
            "tool_calls": sub_task.get("tool_calls", []),
            "summary": sub_task.get("description") or sub_task.get("title") or "Sub-task execution",
        }
        tool_results = await self._execute_tool_calls(
            run,
            project=project,
            task=await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None,
            tool_calls=branch_plan["tool_calls"],
            allowed_tools=(worker.allowed_tools_json if worker else []),
            agent=worker,
        )
        prompt = "\n\n".join(
            [
                f"Sub-task title: {sub_task.get('title', 'Untitled')}",
                f"Sub-task description: {sub_task.get('description', '')}",
                f"Required tools: {sub_task.get('required_tools', [])}",
                f"Manager context: {sub_task.get('manager_notes', '')}",
                f"Tool results: {json.dumps(tool_results, default=str)}" if tool_results else "",
            ]
        )
        _, result = await self._execute_with_routing(
            child_run,
            provider=provider,
            agent=worker,
            system_prompt=(worker.system_prompt if worker else "You are a specialist worker."),
            user_prompt=prompt,
            purpose="delegated sub-task",
            response_format=self._structured_output_response_format(worker),
        )
        contract = self._worker_result_contract(sub_task, result.output_text, result.output_json)
        child_run.output_payload_json = contract
        child_run.completed_at = datetime.now(UTC)
        child_run.status = "completed" if contract["status"] == "completed" else contract["status"]
        if contract["status"] == "blocked":
            child_run.error_message = contract["blocker_reason"] or "blocked"
        await self._write_artifact(
            child_run,
            kind="branch_output",
            title=f"Branch output · {sub_task.get('title', 'Untitled')}",
            content=result.output_text[:12000],
            metadata={"parent_run_id": run.id, "branch_id": sub_task.get("branch_id")},
        )
        await self._emit_run_event(
            run,
            event_type="worker_response",
            message=f"Worker {worker.name} completed sub-task '{sub_task.get('title', 'Untitled')}'.",
            payload={
                "agent_id": worker.id,
                "branch_title": sub_task.get("title"),
                "branch_id": sub_task.get("branch_id"),
                "child_run_id": child_run.id,
                "status": contract["status"],
            },
        )
        return {
            **sub_task,
            "status": contract["status"],
            "agent_id": worker.id,
            "agent_name": worker.name,
            "summary": contract["summary"],
            "output": result.output_text,
            "changed_files": contract["changed_files"],
            "risks": contract["risks"],
            "evidence_refs": contract["evidence_refs"],
            "blocker_reason": contract["blocker_reason"],
            "completion_status": contract["completion_status"],
            "child_run_id": child_run.id,
        }

    async def _debate_participants(
        self,
        project_id: str,
        preferred_ids: list[str | None],
        *,
        task: OrchestratorTask | None = None,
    ) -> list:
        chosen = []
        for agent_id in preferred_ids:
            if not agent_id:
                continue
            agent = await self._load_agent_for_run(agent_id)
            if agent and agent not in chosen:
                chosen.append(agent)
        if len(chosen) >= 2:
            return chosen[:2]
        task_ns = task or SimpleNamespace(
            id="debate",
            metadata_json={},
            labels_json=[],
            title="",
            description="",
            task_type="general",
            due_date=None,
        )
        candidates = await self._candidate_workers(project_id, task=task)
        if task is not None:
            candidates = [a for a in candidates if self._agent_eligible_for_task_by_filters(a, task)]
        ranked = await self._rank_worker_candidates(project_id, task_ns, candidates)
        for agent in ranked:
            if agent not in chosen:
                chosen.append(agent)
            if len(chosen) >= 2:
                break
        return chosen[:2]

    async def _select_best_agent_for_task(
        self,
        project_id: str,
        *,
        task: OrchestratorTask,
        exclude_agent_ids: list[str | None] | None = None,
    ) -> AgentProfile | None:
        exclude = {item for item in (exclude_agent_ids or []) if item}
        project = await self.db.get(OrchestratorProject, project_id)
        exe = self._project_execution_settings(project) if project else {}
        candidates = [
            agent
            for agent in await self._candidate_workers(project_id, task=task)
            if agent.id not in exclude and self._agent_eligible_for_task_by_filters(agent, task)
        ]
        if not candidates:
            return None
        required = set(self._extract_required_tools(task))
        ranked = await self._rank_worker_candidates(project_id, task, candidates, execution_settings=exe)
        if required:
            eligible = [agent for agent in ranked if required.issubset(set(agent.allowed_tools_json or []))]
            return eligible[0] if eligible else None
        return ranked[0]

    async def _select_debate_pair(
        self,
        project_id: str,
        task: OrchestratorTask,
        *,
        exclude_agent_ids: list[str | None] | None = None,
    ) -> list[AgentProfile]:
        exclude = {item for item in (exclude_agent_ids or []) if item}
        project = await self.db.get(OrchestratorProject, project_id)
        exe = self._project_execution_settings(project) if project else {}
        candidates = [
            agent
            for agent in await self._candidate_workers(project_id, task=task)
            if agent.id not in exclude and self._agent_eligible_for_task_by_filters(agent, task)
        ]
        if len(candidates) <= 2:
            return candidates[:2]
        required = set(self._extract_required_tools(task))
        ranked = await self._rank_worker_candidates(project_id, task, candidates, execution_settings=exe)
        if required:
            ranked = [a for a in ranked if required.issubset(set(a.allowed_tools_json or []))] or ranked
        if len(ranked) < 2:
            return ranked[:2]
        first = ranked[0]
        second = next((a for a in ranked[1:] if a.id != first.id), ranked[1])
        return [first, second]

    async def _project_default_manager(
        self, project_id: str, *, project: OrchestratorProject | None = None
    ) -> AgentProfile | None:
        if project is None:
            project = await self.db.get(OrchestratorProject, project_id)
        if project is not None:
            manager_id = self._project_execution_settings(project).get("manager_agent_id")
            if manager_id:
                manager = await self._load_agent_for_run(str(manager_id))
                if manager and manager.is_active:
                    return manager
        memberships = await self.repo.list_project_memberships(project_id)
        manager_membership = next(
            (item for item in memberships if item.is_default_manager or item.role in {"manager", "team_lead"}),
            None,
        )
        if manager_membership is None:
            return None
        return await self._load_agent_for_run(manager_membership.agent_id)

    def _delegation_edge_allowed(self, manager: AgentProfile | None, worker: AgentProfile | None) -> bool:
        if manager is None or worker is None:
            return True
        if manager.id != worker.id and not self._is_agent_descendant(manager, worker):
            return False
        rules = (manager.model_policy_json or {}).get("delegation_rules") or {}
        allowed = rules.get("allowed_delegate_to")
        if not allowed or not isinstance(allowed, list):
            return True
        allowed_set = {str(x).strip() for x in allowed if str(x).strip()}
        if not allowed_set:
            return True
        return worker.slug in allowed_set or worker.id in allowed_set

    def _brainstorm_pair_allowed(self, agent_a: AgentProfile, agent_b: AgentProfile) -> bool:
        def one_way(left: AgentProfile, right: AgentProfile) -> bool:
            rules = (left.model_policy_json or {}).get("delegation_rules") or {}
            raw = rules.get("allowed_brainstorm_with")
            if not raw or not isinstance(raw, list):
                return True
            s = {str(x).strip() for x in raw if str(x).strip()}
            if not s:
                return True
            return right.slug in s or right.id in s

        return one_way(agent_a, agent_b) and one_way(agent_b, agent_a)

    async def _apply_blocked_handoff_suggestion(
        self,
        task: OrchestratorTask,
        run: TaskRun | None,
        reason: str | None,
    ) -> None:
        project = await self.db.get(OrchestratorProject, task.project_id)
        if not project:
            return
        meta = dict(task.metadata_json or {})
        worker_id = run.worker_agent_id if run and run.worker_agent_id else task.assigned_agent_id
        worker = await self._load_agent_for_run(worker_id) if worker_id else None
        handoff_id: str | None = None
        handoff_via: str | None = None
        execution = self._project_execution_settings(project)
        blocked_handoff = dict(execution.get("blocked_handoff") or {})
        blocked_mode = str(blocked_handoff.get("mode") or "escalation_path").strip().lower()
        member_ids = {m.agent_id for m in await self.repo.list_project_memberships(project.id)}
        if blocked_mode == "configured_agent":
            target_id = blocked_handoff.get("target_agent_id")
            if target_id:
                target = await self.repo.get_agent(project.owner_id, str(target_id))
                if target and target.is_active and target.id in member_ids:
                    handoff_id = target.id
                    handoff_via = "configured_agent"
        if handoff_id is None and blocked_mode == "sibling_with_capacity" and worker:
            candidates = [
                agent
                for agent in await self._candidate_workers(project.id, task=task)
                if agent.id != worker.id and agent.parent_agent_id == worker.parent_agent_id
            ]
            if candidates:
                ranked = await self._rank_worker_candidates(
                    project.id,
                    task,
                    candidates,
                    execution_settings=execution,
                )
                if ranked:
                    handoff_id = ranked[0].id
                    handoff_via = "sibling_with_capacity"
        if handoff_id is None and worker:
            esc = (worker.model_policy_json or {}).get("escalation_path")
            if esc:
                target = await self.repo.get_agent_by_slug(project.owner_id, str(esc).strip())
                if target and target.is_active:
                    if target.id in member_ids:
                        handoff_id = target.id
                        handoff_via = "escalation_path"
        if handoff_id is None and bool(blocked_handoff.get("fallback_to_manager", True)):
            mgr = execution.get("manager_agent_id")
            if mgr:
                handoff_id = str(mgr)
                handoff_via = "project_manager"
        if handoff_id:
            meta["suggested_handoff_agent_id"] = handoff_id
            meta["handoff_suggested_via"] = handoff_via
            if reason:
                meta["handoff_blocked_reason"] = str(reason)[:2000]
            task.metadata_json = meta
            if hasattr(task, "_sa_instance_state"):
                orm_attributes.flag_modified(task, "metadata_json")

    async def _rank_worker_candidates(
        self,
        project_id: str,
        task: Any,
        candidates: list[AgentProfile],
        *,
        execution_settings: dict[str, Any] | None = None,
    ) -> list[AgentProfile]:
        if not candidates:
            return []
        project = await self.db.get(OrchestratorProject, project_id)
        exe = execution_settings
        if exe is None:
            exe = self._project_execution_settings(project) if project else {}
        routing_mode = str(exe.get("routing_mode") or "capability_based").lower()
        sibling_mode = str(exe.get("sibling_load_balance") or "queue_depth").lower()
        skip_unhealthy = bool(exe.get("skip_unhealthy_worker_providers", True))

        required = set(self._extract_required_tools(task))
        queue_depths = await self.repo.count_active_runs_by_worker(project_id, [a.id for a in candidates])
        health_snapshots = await self._provider_health_snapshots(candidates)

        now = datetime.now(UTC)
        due = getattr(task, "due_date", None)
        hours_to_due: float | None = None
        if due is not None:
            hours_to_due = (due - now).total_seconds() / 3600.0

        def sla_multiplier() -> float:
            if routing_mode in {"sla_priority", "priority_sla"}:
                if hours_to_due is None:
                    return 2.0 if getattr(task, "priority", "normal") in {"high", "urgent"} else 1.0
                if hours_to_due <= 0:
                    return 5.0
                priority_boost = 2.0 if getattr(task, "priority", "normal") == "urgent" else 1.5 if getattr(task, "priority", "normal") == "high" else 1.0
                return priority_boost * max(1.0, min(72.0, 24.0 / max(hours_to_due, 0.25)))
            if routing_mode == "throughput":
                return 0.75
            return 1.0

        m = sla_multiplier()
        task_id = str(getattr(task, "id", "") or "task")

        def tie_key(agent: AgentProfile) -> tuple[Any, ...]:
            if sibling_mode == "round_robin":
                digest = hashlib.md5(f"{task_id}:{agent.parent_agent_id or ''}:{agent.id}".encode()).hexdigest()
                return (int(digest[:8], 16) % 10000,)
            return (agent.name,)

        scored: list[tuple[tuple[Any, ...], AgentProfile]] = []
        for agent in candidates:
            allowed = set(agent.allowed_tools_json or [])
            tool_hits = len(required & allowed) if required else 0
            qd = queue_depths.get(agent.id, 0)
            weighted_qd = qd * m
            unhealthy_penalty = 0
            health_rank = 0
            if agent.provider_config_id:
                snap = health_snapshots.get(agent.provider_config_id)
                if snap and snap[1] is not None:
                    if snap[0] is False:
                        unhealthy_penalty = 10_000 if skip_unhealthy or routing_mode == "model_availability" else 100
                        health_rank = 1
                    else:
                        health_rank = -1
            estimated_cost = self._agent_estimated_run_cost(agent)
            if routing_mode == "cost_aware":
                key = (-tool_hits, estimated_cost, weighted_qd + unhealthy_penalty, *tie_key(agent))
            elif routing_mode == "model_availability":
                key = (-tool_hits, health_rank, weighted_qd + unhealthy_penalty, *tie_key(agent))
            elif routing_mode == "user_pinned":
                key = (weighted_qd + unhealthy_penalty, -tool_hits, *tie_key(agent))
            else:
                key = (-tool_hits, weighted_qd + unhealthy_penalty, *tie_key(agent))
            scored.append((key, agent))
        scored.sort(key=lambda item: item[0])
        return [pair[1] for pair in scored]

    def _agent_estimated_run_cost(self, agent: AgentProfile) -> float:
        model_name = (agent.model_policy_json or {}).get("model")
        if not model_name:
            return 0.0
        for item in getattr(self, "_cached_model_capabilities", []) or []:
            if item.model_slug == model_name:
                return float(item.cost_per_1k_input or 0.0) + float(item.cost_per_1k_output or 0.0)
        return 0.0

    def _reviewer_chain_for_project(self, project: OrchestratorProject | None) -> list[str]:
        if project is None:
            return []
        execution = self._project_execution_settings(project)
        return [str(item).strip() for item in execution.get("reviewer_agent_ids") or [] if str(item).strip()]
