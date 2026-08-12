"""Durable workflow graph runner wired to workforce orchestration primitives.

Uses WorkflowVersion.nodes_json / edges_json / entry_node_id and persists
WorkflowRun + WorkflowStepRun. Node execution connects to existing durable
systems:

- tool → ToolExecutionService (authorize + native dispatch)
- skill → SkillVersion resolution into run vars
- agent → TaskRun via TaskRunStarter (freeze + Celery enqueue)
- approval / human_input → auto-created ApprovalRequest + consumption gates
- parallel → branch status in parallel_branches with join policies
- delay → durable resume_at + Celery resume hook
- subworkflow → nested WorkflowRun with parent pause until child completes
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import (
    Skill,
    SkillVersion,
    WorkflowDefinition,
    WorkflowRun,
    WorkflowStepRun,
    WorkflowVersion,
)

SUPPORTED_NODE_TYPES = frozenset(
    {
        "agent",
        "skill",
        "tool",
        "router",
        "condition",
        "parallel",
        "approval",
        "human_input",
        "subworkflow",
        "delay",
        "trigger",
    }
)

_TASK_RUN_TERMINAL = frozenset({"completed", "failed", "cancelled"})
_SIMPLE_PARALLEL_TYPES = frozenset({"tool", "skill", "condition", "trigger"})


def _utcnow() -> datetime:
    return datetime.now(UTC)


class WorkflowRuntimeService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_definition(self, owner_id: str, workflow_id: str) -> WorkflowDefinition:
        result = await self.db.execute(
            select(WorkflowDefinition).where(
                WorkflowDefinition.id == workflow_id,
                (WorkflowDefinition.owner_id == owner_id)
                | (WorkflowDefinition.is_template.is_(True)),
            )
        )
        item = result.scalar_one_or_none()
        if item is None:
            raise ValueError("workflow not found")
        return item

    async def get_version(self, version_id: str) -> WorkflowVersion | None:
        result = await self.db.execute(
            select(WorkflowVersion).where(WorkflowVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    def validate_graph(
        self,
        *,
        nodes: list[Any],
        edges: list[Any],
        entry_node_id: str | None,
    ) -> list[str]:
        errors: list[str] = []
        node_ids = {n.get("id") for n in nodes if isinstance(n, dict) and n.get("id")}
        if not nodes:
            errors.append("nodes is required")
        if not entry_node_id:
            errors.append("entry_node_id is required")
        elif entry_node_id not in node_ids:
            errors.append(f"entry node `{entry_node_id}` missing from nodes")
        for node in nodes:
            if not isinstance(node, dict):
                errors.append("node must be object")
                continue
            ntype = node.get("type")
            if ntype not in SUPPORTED_NODE_TYPES:
                errors.append(f"unsupported node type: {ntype}")
        for edge in edges:
            if not isinstance(edge, dict):
                errors.append("edge must be object")
                continue
            if edge.get("from") not in node_ids or edge.get("to") not in node_ids:
                errors.append(f"edge references unknown nodes: {edge}")
        return errors

    async def start_run(
        self,
        owner_id: str,
        workflow_id: str,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        input_json: dict[str, Any] | None = None,
    ) -> WorkflowRun:
        run, version = await self._create_run_record(
            owner_id,
            workflow_id,
            project_id=project_id,
            task_id=task_id,
            input_json=input_json,
        )
        await self._advance(run, version)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _create_run_record(
        self,
        owner_id: str,
        workflow_id: str,
        *,
        project_id: str | None = None,
        task_id: str | None = None,
        input_json: dict[str, Any] | None = None,
    ) -> tuple[WorkflowRun, WorkflowVersion]:
        definition = await self.get_definition(owner_id, workflow_id)
        if not definition.current_version_id:
            raise ValueError("workflow has no published version")
        version = await self.get_version(definition.current_version_id)
        if version is None:
            raise ValueError("workflow version missing")
        nodes = list(version.nodes_json or [])
        edges = list(version.edges_json or [])
        errors = self.validate_graph(nodes=nodes, edges=edges, entry_node_id=version.entry_node_id)
        if errors:
            raise ValueError({"errors": errors})

        run = WorkflowRun(
            id=str(uuid4()),
            workflow_id=definition.id,
            workflow_version_id=version.id,
            project_id=project_id,
            task_id=task_id,
            status="running",
            current_node_id=version.entry_node_id,
            context_json={
                "input": input_json or {},
                "completed": [],
                "vars": dict(input_json or {}),
            },
            result_json={},
            created_by=owner_id,
        )
        self.db.add(run)
        await self.db.flush()
        return run, version

    async def resume_run(
        self,
        owner_id: str,
        run_id: str,
        *,
        approval_request_id: str | None = None,
        human_input: dict | None = None,
        actor_user_id: str | None = None,
        approval_granted: bool = False,  # deprecated; ignored
    ) -> WorkflowRun:
        result = await self.db.execute(select(WorkflowRun).where(WorkflowRun.id == run_id))
        run = result.scalar_one_or_none()
        if run is None:
            raise ValueError("run not found")
        definition = await self.get_definition(owner_id, run.workflow_id)
        if definition.owner_id != owner_id and not definition.is_template:
            raise ValueError("access denied")
        if run.status not in {"paused", "waiting_approval", "waiting_input"}:
            raise ValueError(f"run not resumable from status={run.status}")
        version = await self.get_version(run.workflow_version_id)
        if version is None:
            raise ValueError("workflow version missing")
        ctx = dict(run.context_json or {})
        vars_ = dict(ctx.get("vars") or {})

        node = None
        if run.current_node_id and version.nodes_json:
            node = next(
                (
                    n
                    for n in version.nodes_json
                    if isinstance(n, dict) and n.get("id") == run.current_node_id
                ),
                None,
            )
        ntype = str((node or {}).get("type") or "")

        if ntype == "approval":
            if not approval_request_id:
                raise ValueError(
                    "approval_request_id required — client-asserted "
                    "approval_granted is not accepted"
                )
            await self._consume_approval_for_node(
                approval_request_id,
                run=run,
                node_id=run.current_node_id,
                vars_=vars_,
                actor_user_id=actor_user_id,
            )
        elif ntype == "tool" and vars_.get("pending_tool"):
            if not approval_request_id:
                raise ValueError(
                    "approval_request_id required for pending tool execution — "
                    "client-asserted approval_granted is not accepted"
                )
            await self._consume_approval_for_node(
                approval_request_id,
                run=run,
                node_id=run.current_node_id,
                vars_=vars_,
                actor_user_id=actor_user_id,
                pending_tool=True,
            )
        elif ntype == "human_input":
            if not isinstance(human_input, dict) or not human_input:
                raise ValueError("human_input payload required for human_input nodes")
            vars_["human_input"] = human_input
            vars_["human_input_by"] = actor_user_id
        elif approval_granted:
            raise ValueError(
                "approval_granted is not accepted; submit approval_request_id or human_input"
            )

        ctx["vars"] = vars_
        run.context_json = ctx
        run.status = "running"
        await self._advance(run, version)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _create_workflow_approval_request(
        self,
        *,
        run: WorkflowRun,
        node_id: str,
        approval_type: str,
        action_key: str,
        args_hash: str | None = None,
        reason: str | None = None,
        extra_payload: dict[str, Any] | None = None,
    ) -> str:
        from backend.modules.orchestration.models import ApprovalRequest

        payload: dict[str, Any] = {
            "workflow_run_id": run.id,
            "workflow_node_id": node_id,
            "action_key": action_key,
            "owner_id": run.created_by,
        }
        if args_hash:
            payload["arguments_hash"] = args_hash
        if extra_payload:
            payload.update(extra_payload)

        approval = ApprovalRequest(
            id=str(uuid4()),
            project_id=run.project_id,
            task_id=run.task_id,
            approval_type=approval_type,
            status="pending",
            requested_by_user_id=run.created_by,
            reason=reason,
            payload_json=payload,
        )
        self.db.add(approval)
        await self.db.flush()
        return approval.id

    async def _consume_approval_for_node(
        self,
        approval_request_id: str,
        *,
        run: WorkflowRun,
        node_id: str | None,
        vars_: dict[str, Any],
        actor_user_id: str | None,
        pending_tool: bool = False,
    ) -> None:
        from sqlalchemy.orm.attributes import flag_modified

        from backend.modules.orchestration.models import ApprovalRequest
        from backend.modules.orchestration.tool_execution_context import arguments_hash

        approval = await self.db.get(ApprovalRequest, approval_request_id)
        if approval is None or approval.status != "approved":
            raise ValueError("approval_request_id must reference an approved ApprovalRequest")
        if approval.project_id and run.project_id and approval.project_id != run.project_id:
            raise ValueError("approval does not match workflow run project")
        payload = dict(approval.payload_json or {})
        if payload.get("_consumed_at") or payload.get("consumed_at"):
            raise ValueError("approval_request already consumed")

        if str(payload.get("workflow_run_id") or "") != run.id:
            raise ValueError("approval workflow_run_id does not match workflow run")
        if str(payload.get("workflow_node_id") or "") != str(node_id or ""):
            raise ValueError("approval workflow_node_id does not match current node")

        if pending_tool:
            pending = dict(vars_.get("pending_tool") or {})
            tool_slug = str(pending.get("tool_slug") or "")
            params = dict(pending.get("params") or {})
            expected_hash = arguments_hash(params)
            action = str(
                payload.get("action_key") or payload.get("action") or approval.approval_type or ""
            )
            exact_tools = {
                tool_slug,
                f"tool:{tool_slug}",
                f"execute:{tool_slug}",
                f"tool_execution:{tool_slug}",
            }
            if action not in exact_tools and approval.approval_type not in exact_tools:
                raise ValueError("approval action_key does not match pending tool")
            grant_hash = str(payload.get("arguments_hash") or "")
            if not grant_hash or grant_hash != expected_hash:
                raise ValueError("approval arguments_hash does not match pending tool params")

        payload["_consumed_at"] = _utcnow().isoformat()
        payload["consumed_at"] = payload["_consumed_at"]
        payload["consumed_workflow_node_id"] = node_id
        approval.payload_json = payload
        flag_modified(approval, "payload_json")

        if pending_tool:
            pending = dict(vars_.get("pending_tool") or {})
            pending["approval_request_id"] = approval_request_id
            pending["approval_consumed"] = True
            pending["approved_by"] = approval.approved_by_user_id or actor_user_id
            vars_["pending_tool"] = pending
        else:
            vars_["approval_granted"] = True
            vars_["approval_request_id"] = approval_request_id
            vars_["approval_node_id"] = node_id
            vars_["approved_by"] = approval.approved_by_user_id or actor_user_id

    async def _resolve_skill_version(self, config: dict[str, Any]) -> SkillVersion | None:
        skill_version_id = config.get("skill_version_id")
        skill_id = config.get("skill_id")
        if skill_version_id:
            return await self.db.get(SkillVersion, str(skill_version_id))
        if not skill_id:
            return None
        skill = await self.db.get(Skill, str(skill_id))
        if skill and skill.current_version_id:
            version = await self.db.get(SkillVersion, skill.current_version_id)
            if version is not None:
                return version
        result = await self.db.execute(
            select(SkillVersion)
            .where(
                SkillVersion.skill_id == str(skill_id),
                SkillVersion.is_published.is_(True),
            )
            .order_by(SkillVersion.version_number.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def _execute_tool_node(
        self,
        *,
        run: WorkflowRun,
        node: dict[str, Any],
        node_id: str,
        vars_: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        """Returns (step_status, output_json, run_status_if_pause)."""
        from backend.modules.orchestration.tool_execution_context import arguments_hash
        from backend.modules.workforce.services.tool_execution_service import ToolExecutionService

        config = dict(node.get("config") or {})
        pending = vars_.get("pending_tool")
        if isinstance(pending, dict) and pending.get("node_id") == node_id:
            if not pending.get("approval_consumed"):
                approval_id = pending.get("approval_request_id") or vars_.get(
                    "pending_approval_request_id"
                )
                if not approval_id:
                    args_hash = arguments_hash(dict(pending.get("params") or {}))
                    approval_id = await self._create_workflow_approval_request(
                        run=run,
                        node_id=node_id,
                        approval_type=f"tool:{pending.get('tool_slug')}",
                        action_key=f"tool:{pending.get('tool_slug')}",
                        args_hash=args_hash,
                        reason=f"Workflow tool `{pending.get('tool_slug')}` requires approval",
                        extra_payload={"tool_slug": pending.get("tool_slug")},
                    )
                vars_["pending_approval_request_id"] = approval_id
                pending["approval_request_id"] = approval_id
                vars_["pending_tool"] = pending
                return (
                    "paused",
                    {
                        "pending_tool": pending,
                        "approval_request_id": approval_id,
                    },
                    "waiting_approval",
                )
            tool_slug = str(pending.get("tool_slug") or "")
            params = dict(pending.get("params") or {})
            context = dict(pending.get("context") or {})
            context["approval_granted"] = True
            context["approval_request_id"] = pending.get("approval_request_id")
            vars_.pop("pending_tool", None)
            vars_.pop("pending_approval_request_id", None)
        else:
            tool_slug = str(config.get("tool") or config.get("tool_slug") or "")
            params = dict(config.get("params") or vars_)
            context = {
                "owner_id": run.created_by,
                "project_id": run.project_id,
                "task_id": run.task_id,
                "workflow_run_id": run.id,
                "workflow_node_id": node_id,
            }

        if not tool_slug:
            return (
                "failed",
                {"error": "tool node missing config.tool or config.tool_slug"},
                "failed",
            )

        executor = ToolExecutionService(self.db)
        result = await executor.execute(
            str(run.created_by or ""),
            tool_slug,
            params,
            context,
        )
        if result.get("status") == "approval_required":
            args_hash = arguments_hash(params)
            approval_id = await self._create_workflow_approval_request(
                run=run,
                node_id=node_id,
                approval_type=f"tool:{tool_slug}",
                action_key=f"tool:{tool_slug}",
                args_hash=args_hash,
                reason=f"Workflow tool `{tool_slug}` requires approval",
                extra_payload={"tool_slug": tool_slug},
            )
            vars_["pending_tool"] = {
                "node_id": node_id,
                "tool_slug": tool_slug,
                "params": params,
                "context": {
                    k: v
                    for k, v in context.items()
                    if k not in {"approval_granted", "approval_request_id"}
                },
                "auth": {
                    "decision": result.get("decision"),
                    "resolution": (result.get("resolution") or {}),
                },
                "approval_request_id": approval_id,
            }
            vars_["pending_approval_request_id"] = approval_id
            return (
                "paused",
                {
                    "approval_required": True,
                    "tool_slug": tool_slug,
                    "approval_request_id": approval_id,
                },
                "waiting_approval",
            )
        if result.get("status") in {"denied", "failed"}:
            return "failed", {"denied": True, "tool_slug": tool_slug, "result": result}, "failed"
        vars_[f"tool_result_{node_id}"] = result
        return "succeeded", {"tool_slug": tool_slug, "result": result}, None

    async def _execute_agent_node(
        self,
        *,
        run: WorkflowRun,
        node: dict[str, Any],
        node_id: str,
        vars_: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        config = dict(node.get("config") or {})
        agent_id = config.get("agent_id")
        agent_runs = dict(vars_.get("_agent_runs") or {})
        existing_id = agent_runs.get(node_id)

        if existing_id:
            from backend.modules.orchestration.models import TaskRun

            task_run = await self.db.get(TaskRun, str(existing_id))
            if task_run is None:
                agent_runs.pop(node_id, None)
                vars_["_agent_runs"] = agent_runs
            elif task_run.status in _TASK_RUN_TERMINAL:
                output = {
                    "task_run_id": task_run.id,
                    "task_run_status": task_run.status,
                }
                if task_run.status != "completed":
                    return "failed", output, "failed"
                return "succeeded", output, None
            else:
                return (
                    "paused",
                    {"task_run_id": task_run.id, "task_run_status": task_run.status},
                    "paused",
                )

        if agent_id and run.project_id and run.task_id:
            from backend.modules.identity_access.models import User
            from backend.modules.orchestration.task_run_starter import TaskRunStarter

            user = await self.db.get(User, str(run.created_by or ""))
            if user is None:
                return (
                    "failed",
                    {"error": "workflow run owner user not found for agent TaskRun"},
                    "failed",
                )
            input_payload = dict(config.get("input") or config.get("input_payload") or {})
            input_payload.update(
                {
                    "workflow_run_id": run.id,
                    "workflow_node_id": node_id,
                }
            )
            starter = TaskRunStarter(self.db)
            task_run, _warnings = await starter.start(
                user,
                project_id=str(run.project_id),
                task_id=str(run.task_id),
                worker_agent_id=str(agent_id),
                orchestrator_agent_id=config.get("orchestrator_agent_id"),
                run_mode=str(config.get("run_mode") or "single_agent"),
                input_payload=input_payload,
            )
            agent_runs[node_id] = task_run.id
            vars_["_agent_runs"] = agent_runs
            return (
                "paused",
                {"task_run_id": task_run.id, "task_run_status": task_run.status},
                "paused",
            )

        handoff = {
            "delegated_to": "orchestration",
            "agent_id": agent_id,
            "project_id": run.project_id,
            "task_id": run.task_id,
        }
        if not agent_id:
            handoff["reason"] = "agent_id missing from node config"
        elif not run.project_id or not run.task_id:
            handoff["reason"] = "workflow run missing project_id or task_id"
        return "succeeded", handoff, None

    async def _execute_subworkflow_node(
        self,
        *,
        run: WorkflowRun,
        node: dict[str, Any],
        node_id: str,
        vars_: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        config = dict(node.get("config") or {})
        workflow_id = config.get("workflow_id")
        sub_runs = dict(vars_.get("_subworkflow_runs") or {})
        child_run_id = sub_runs.get(node_id)

        if child_run_id:
            child = await self.db.get(WorkflowRun, str(child_run_id))
            if child is None:
                sub_runs.pop(node_id, None)
                vars_["_subworkflow_runs"] = sub_runs
            elif child.status == "completed":
                return "succeeded", {"child_run_id": child.id, "child_status": child.status}, None
            elif child.status in {"failed", "cancelled"}:
                return (
                    "failed",
                    {"child_run_id": child.id, "child_status": child.status},
                    "failed",
                )
            else:
                return (
                    "paused",
                    {"child_run_id": child.id, "child_status": child.status},
                    "paused",
                )

        if not workflow_id:
            return "failed", {"error": "subworkflow node missing config.workflow_id"}, "failed"

        child_run, _version = await self._create_run_record(
            str(run.created_by or ""),
            str(workflow_id),
            project_id=run.project_id,
            task_id=run.task_id,
            input_json=dict(vars_),
        )
        await self._advance(child_run, _version)
        sub_runs[node_id] = child_run.id
        vars_["_subworkflow_runs"] = sub_runs
        if child_run.status == "completed":
            return (
                "succeeded",
                {"child_run_id": child_run.id, "child_status": child_run.status},
                None,
            )
        if child_run.status in {"failed", "cancelled"}:
            return (
                "failed",
                {"child_run_id": child_run.id, "child_status": child_run.status},
                "failed",
            )
        return (
            "paused",
            {"child_run_id": child_run.id, "child_status": child_run.status},
            "paused",
        )

    def _evaluate_parallel_join(self, policy: str, statuses: list[str]) -> str:
        succeeded = sum(1 for s in statuses if s == "succeeded")
        failed = sum(1 for s in statuses if s == "failed")
        total = len(statuses)
        if policy == "any_success":
            return "succeeded" if succeeded > 0 else "failed"
        if policy == "best_effort":
            if succeeded > 0:
                return "succeeded"
            return "failed" if failed == total and total > 0 else "paused"
        if failed > 0 or succeeded < total:
            return "failed"
        return "succeeded"

    async def _execute_simple_node(
        self,
        *,
        run: WorkflowRun,
        node: dict[str, Any],
        node_id: str,
        vars_: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        ntype = str(node.get("type") or "")
        if ntype == "tool":
            return await self._execute_tool_node(run=run, node=node, node_id=node_id, vars_=vars_)
        if ntype == "skill":
            config = dict(node.get("config") or {})
            version_row = await self._resolve_skill_version(config)
            if version_row is None:
                return "failed", {"error": "skill version not found"}, "failed"
            skill_payload = {
                "skill_id": version_row.skill_id,
                "skill_version_id": version_row.id,
                "version_number": version_row.version_number,
                "instructions_markdown": version_row.instructions_markdown,
                "required_tools": list(version_row.required_tools_json or []),
                "capabilities": list(version_row.capabilities_json or []),
            }
            vars_["skill_payload"] = skill_payload
            return (
                "succeeded",
                {"skill_version_id": version_row.id, "skill_id": version_row.skill_id},
                None,
            )
        if ntype == "condition":
            from backend.modules.workforce.services.workflow_conditions import (
                condition_from_config,
                evaluate_condition,
            )

            config = dict(node.get("config") or {})
            cond = condition_from_config(config)
            result = evaluate_condition(cond, vars_) if cond else False
            vars_["_last_condition"] = result
            return "succeeded", {"branch": result, "condition": cond}, None
        if ntype == "trigger":
            config = dict(node.get("config") or {})
            trigger_type = str(config.get("trigger_type") or config.get("type") or "manual")
            metadata = {
                "trigger_type": trigger_type,
                "source": config.get("source"),
                "schedule": config.get("schedule"),
                "webhook_key": config.get("webhook_key"),
                "event": config.get("event"),
                "metadata": dict(config.get("metadata") or {}),
            }
            vars_[f"trigger_{node_id}"] = metadata
            return "succeeded", metadata, None
        return "failed", {"error": f"unsupported simple node type `{ntype}`"}, "failed"

    async def _execute_parallel_node(
        self,
        *,
        run: WorkflowRun,
        node: dict[str, Any],
        node_id: str,
        nodes: dict[str, dict[str, Any]],
        vars_: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        config = dict(node.get("config") or {})
        join_policy = str(config.get("join_policy") or config.get("policy") or "all_success")
        children = list(config.get("children") or [])

        all_branches = dict(vars_.get("parallel_branches") or {})
        branch_state = dict(all_branches.get(node_id) or {})
        if not branch_state:
            branch_state = {
                "join_policy": join_policy,
                "branches": {cid: {"status": "pending", "output": {}} for cid in children},
            }

        branches = dict(branch_state.get("branches") or {})
        any_paused = False

        for child_id in children:
            child_entry = dict(branches.get(child_id) or {"status": "pending", "output": {}})
            status = str(child_entry.get("status") or "pending")
            if status in {"succeeded", "failed"}:
                continue

            child_node = nodes.get(child_id)
            if child_node is None:
                child_entry["status"] = "failed"
                child_entry["output"] = {"error": "child node not found"}
                branches[child_id] = child_entry
                continue

            child_type = str(child_node.get("type") or "")
            if child_type not in _SIMPLE_PARALLEL_TYPES:
                child_entry["status"] = "paused"
                child_entry["output"] = {
                    "reason": f"child type `{child_type}` requires async branch execution"
                }
                branches[child_id] = child_entry
                any_paused = True
                continue

            step_status, output, pause = await self._execute_simple_node(
                run=run,
                node=child_node,
                node_id=child_id,
                vars_=vars_,
            )
            if pause:
                child_entry["status"] = "paused"
                any_paused = True
            elif step_status == "failed":
                child_entry["status"] = "failed"
            else:
                child_entry["status"] = "succeeded"
            child_entry["output"] = output
            branches[child_id] = child_entry

        branch_state["branches"] = branches
        all_branches[node_id] = branch_state
        vars_["parallel_branches"] = all_branches

        output = {"parallel_branches": branch_state, "join_policy": join_policy}
        if any_paused:
            return "paused", output, "paused"

        statuses = [str(b.get("status") or "") for b in branches.values()]
        joined = self._evaluate_parallel_join(join_policy, statuses)
        output["join_result"] = joined
        if joined == "succeeded":
            return "succeeded", output, None
        if joined == "failed":
            return "failed", output, "failed"
        return "paused", output, "paused"

    def _execute_router_node(
        self,
        *,
        node: dict[str, Any],
        node_id: str,
        edges: list[dict[str, Any]],
        vars_: dict[str, Any],
    ) -> tuple[str, dict[str, Any], str | None]:
        from backend.modules.workforce.services.workflow_conditions import evaluate_condition

        config = dict(node.get("config") or {})
        rules = list(config.get("rules") or [])
        outgoing = [e for e in edges if e.get("from") == node_id]
        selected: str | None = None
        matched_rule: dict[str, Any] | None = None

        for rule in rules:
            if not isinstance(rule, dict):
                continue
            condition = rule.get("condition") if isinstance(rule.get("condition"), dict) else rule
            if (
                isinstance(condition, dict)
                and condition.get("operator")
                and evaluate_condition(condition, vars_)
            ):
                selected = str(rule.get("to") or rule.get("target") or "")
                matched_rule = rule
                break

        if not selected:
            for edge in outgoing:
                when = edge.get("when")
                if when is None:
                    continue
                if isinstance(when, dict) and when.get("operator"):
                    if evaluate_condition(when, vars_):
                        selected = str(edge.get("to") or "")
                        break
                elif bool(when):
                    selected = str(edge.get("to") or "")
                    break

        if not selected and outgoing:
            selected = str(outgoing[0].get("to") or "")

        if selected:
            vars_["_router_target"] = selected

        return (
            "succeeded",
            {
                "selected": selected,
                "rules_evaluated": len(rules),
                "matched_rule": matched_rule,
            },
            None,
        )

    def _schedule_delay_resume(
        self,
        *,
        run: WorkflowRun,
        node_id: str,
        resume_at: datetime,
    ) -> None:
        try:
            from backend.workers.orchestration import queue_workflow_delay_resume

            queue_workflow_delay_resume(
                run_id=run.id,
                node_id=node_id,
                owner_id=str(run.created_by or ""),
                resume_at_iso=resume_at.isoformat(),
            )
        except Exception:
            pass

    def _pause_run(
        self,
        *,
        run: WorkflowRun,
        cursor: str,
        ctx: dict[str, Any],
        completed: list[str],
        vars_: dict[str, Any],
        run_status: str,
    ) -> None:
        run.status = run_status
        run.current_node_id = cursor
        ctx.update({"completed": completed, "vars": vars_})
        run.context_json = ctx

    async def _advance(self, run: WorkflowRun, version: WorkflowVersion) -> None:
        nodes = {
            n["id"]: n for n in (version.nodes_json or []) if isinstance(n, dict) and n.get("id")
        }
        edges = [e for e in (version.edges_json or []) if isinstance(e, dict)]
        ctx = dict(run.context_json or {})
        completed = list(ctx.get("completed") or [])
        vars_ = dict(ctx.get("vars") or {})
        cursor = run.current_node_id
        steps = 0
        max_steps = max(1, len(nodes) * 3)

        while cursor and steps < max_steps:
            steps += 1
            node = nodes.get(cursor)
            if node is None:
                run.status = "failed"
                run.result_json = {"error": f"missing node {cursor}"}
                break

            step = WorkflowStepRun(
                id=str(uuid4()),
                workflow_run_id=run.id,
                node_id=cursor,
                node_type=str(node.get("type") or "agent"),
                status="running",
                input_json={"vars": vars_, "node": node},
                started_at=_utcnow(),
            )
            self.db.add(step)
            await self.db.flush()

            ntype = str(node.get("type") or "")
            pause_status: str | None = None

            if ntype == "approval":
                if vars_.get("approval_granted") and vars_.get("approval_request_id"):
                    consumed = list(vars_.get("_consumed_approval_ids") or [])
                    approval_id = str(vars_.get("approval_request_id"))
                    if approval_id in consumed:
                        step.status = "paused"
                        step.finished_at = _utcnow()
                        self._pause_run(
                            run=run,
                            cursor=cursor,
                            ctx=ctx,
                            completed=completed,
                            vars_=vars_,
                            run_status="waiting_approval",
                        )
                        return
                    if vars_.get("approval_node_id") and vars_.get("approval_node_id") != cursor:
                        step.status = "paused"
                        step.finished_at = _utcnow()
                        self._pause_run(
                            run=run,
                            cursor=cursor,
                            ctx=ctx,
                            completed=completed,
                            vars_=vars_,
                            run_status="waiting_approval",
                        )
                        return
                    step.status = "succeeded"
                    step.output_json = {"approved": True, "approval_request_id": approval_id}
                    step.finished_at = _utcnow()
                    consumed.append(approval_id)
                    vars_["_consumed_approval_ids"] = consumed
                    vars_.pop("approval_granted", None)
                    vars_.pop("approval_request_id", None)
                    vars_.pop("approval_node_id", None)
                    vars_.pop("pending_approval_request_id", None)
                else:
                    approval_id = vars_.get("pending_approval_request_id")
                    if not approval_id:
                        approval_id = await self._create_workflow_approval_request(
                            run=run,
                            node_id=cursor,
                            approval_type="workflow_approval",
                            action_key="workflow_approval",
                            reason=str(
                                (node.get("config") or {}).get("reason")
                                or "Workflow approval required"
                            ),
                        )
                        vars_["pending_approval_request_id"] = approval_id
                    step.status = "paused"
                    step.output_json = {
                        "waiting": True,
                        "approval_request_id": approval_id,
                    }
                    step.finished_at = _utcnow()
                    self._pause_run(
                        run=run,
                        cursor=cursor,
                        ctx=ctx,
                        completed=completed,
                        vars_=vars_,
                        run_status="waiting_approval",
                    )
                    return
            elif ntype == "human_input":
                human_payload = vars_.get("human_input")
                if isinstance(human_payload, dict) and human_payload:
                    step.status = "succeeded"
                    step.output_json = {
                        "human_input": human_payload,
                        "submitted_by": vars_.get("human_input_by"),
                    }
                    step.finished_at = _utcnow()
                    vars_.pop("human_input", None)
                    vars_.pop("human_input_by", None)
                    vars_.pop("approval_granted", None)
                else:
                    step.status = "paused"
                    step.finished_at = _utcnow()
                    self._pause_run(
                        run=run,
                        cursor=cursor,
                        ctx=ctx,
                        completed=completed,
                        vars_=vars_,
                        run_status="waiting_input",
                    )
                    return
            elif ntype == "condition":
                from backend.modules.workforce.services.workflow_conditions import (
                    condition_from_config,
                    evaluate_condition,
                )

                config = dict(node.get("config") or {})
                cond = condition_from_config(config)
                expr = evaluate_condition(cond, vars_) if cond else False
                step.status = "succeeded"
                step.output_json = {"branch": bool(expr), "condition": cond}
                step.finished_at = _utcnow()
                vars_["_last_condition"] = bool(expr)
            elif ntype == "delay":
                config = dict(node.get("config") or {})
                delay_state = dict(vars_.get("_delay_resume") or {})
                resume_at_str = (
                    delay_state.get("resume_at") if delay_state.get("node_id") == cursor else None
                )
                if resume_at_str:
                    resume_at = datetime.fromisoformat(resume_at_str)
                    if _utcnow() >= resume_at:
                        step.status = "succeeded"
                        step.output_json = {"delayed": True, "resume_at": resume_at_str}
                        step.finished_at = _utcnow()
                        vars_.pop("_delay_resume", None)
                    else:
                        step.status = "paused"
                        step.finished_at = _utcnow()
                        self._pause_run(
                            run=run,
                            cursor=cursor,
                            ctx=ctx,
                            completed=completed,
                            vars_=vars_,
                            run_status="paused",
                        )
                        return
                else:
                    seconds = float(config.get("seconds") or config.get("delay_seconds") or 0)
                    if seconds > 0:
                        resume_at = _utcnow() + timedelta(seconds=seconds)
                        vars_["_delay_resume"] = {
                            "node_id": cursor,
                            "resume_at": resume_at.isoformat(),
                        }
                        step.status = "paused"
                        step.output_json = {"resume_at": resume_at.isoformat(), "seconds": seconds}
                        step.finished_at = _utcnow()
                        self._schedule_delay_resume(run=run, node_id=cursor, resume_at=resume_at)
                        self._pause_run(
                            run=run,
                            cursor=cursor,
                            ctx=ctx,
                            completed=completed,
                            vars_=vars_,
                            run_status="paused",
                        )
                        return
                    step.status = "succeeded"
                    step.output_json = {"delayed": False, "seconds": 0}
                    step.finished_at = _utcnow()
            elif ntype == "parallel":
                step.status, step.output_json, pause_status = await self._execute_parallel_node(
                    run=run,
                    node=node,
                    node_id=cursor,
                    nodes=nodes,
                    vars_=vars_,
                )
                step.finished_at = _utcnow()
                if pause_status:
                    self._pause_run(
                        run=run,
                        cursor=cursor,
                        ctx=ctx,
                        completed=completed,
                        vars_=vars_,
                        run_status=pause_status,
                    )
                    return
                if step.status == "failed":
                    run.status = "failed"
                    run.result_json = step.output_json
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
            elif ntype == "router":
                step.status, step.output_json, pause_status = self._execute_router_node(
                    node=node,
                    node_id=cursor,
                    edges=edges,
                    vars_=vars_,
                )
                step.finished_at = _utcnow()
            elif ntype == "trigger":
                step.status, step.output_json, pause_status = await self._execute_simple_node(
                    run=run,
                    node=node,
                    node_id=cursor,
                    vars_=vars_,
                )
                step.finished_at = _utcnow()
                if step.status == "failed":
                    run.status = "failed"
                    run.result_json = step.output_json
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
            elif ntype == "tool":
                step.status, step.output_json, pause_status = await self._execute_tool_node(
                    run=run,
                    node=node,
                    node_id=cursor,
                    vars_=vars_,
                )
                step.finished_at = _utcnow()
                if pause_status:
                    self._pause_run(
                        run=run,
                        cursor=cursor,
                        ctx=ctx,
                        completed=completed,
                        vars_=vars_,
                        run_status=pause_status,
                    )
                    return
                if step.status == "failed":
                    run.status = "failed"
                    run.result_json = step.output_json
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
            elif ntype == "skill":
                config = dict(node.get("config") or {})
                version_row = await self._resolve_skill_version(config)
                if version_row is None:
                    step.status = "failed"
                    step.output_json = {"error": "skill version not found"}
                    step.finished_at = _utcnow()
                    run.status = "failed"
                    run.result_json = step.output_json
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
                skill_payload = {
                    "skill_id": version_row.skill_id,
                    "skill_version_id": version_row.id,
                    "version_number": version_row.version_number,
                    "instructions_markdown": version_row.instructions_markdown,
                    "required_tools": list(version_row.required_tools_json or []),
                    "capabilities": list(version_row.capabilities_json or []),
                }
                vars_["skill_payload"] = skill_payload
                step.status = "succeeded"
                step.output_json = {
                    "skill_version_id": version_row.id,
                    "skill_id": version_row.skill_id,
                }
                step.finished_at = _utcnow()
            elif ntype == "agent":
                step.status, step.output_json, pause_status = await self._execute_agent_node(
                    run=run,
                    node=node,
                    node_id=cursor,
                    vars_=vars_,
                )
                step.finished_at = _utcnow()
                if pause_status:
                    self._pause_run(
                        run=run,
                        cursor=cursor,
                        ctx=ctx,
                        completed=completed,
                        vars_=vars_,
                        run_status=pause_status,
                    )
                    return
                if step.status == "failed":
                    run.status = "failed"
                    run.result_json = step.output_json
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
            elif ntype == "subworkflow":
                step.status, step.output_json, pause_status = await self._execute_subworkflow_node(
                    run=run,
                    node=node,
                    node_id=cursor,
                    vars_=vars_,
                )
                step.finished_at = _utcnow()
                if pause_status:
                    self._pause_run(
                        run=run,
                        cursor=cursor,
                        ctx=ctx,
                        completed=completed,
                        vars_=vars_,
                        run_status=pause_status,
                    )
                    return
                if step.status == "failed":
                    run.status = "failed"
                    run.result_json = step.output_json
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
            else:
                step.status = "succeeded"
                step.output_json = {
                    "node_type": ntype,
                    "message": f"Node type `{ntype}` recorded without dedicated executor",
                }
                step.finished_at = _utcnow()

            completed.append(cursor)
            next_id = self._next_node(cursor, edges, vars_)
            cursor = next_id
            run.current_node_id = cursor
            if cursor is None:
                run.status = "completed"
                run.result_json = {"completed_nodes": completed, "vars": vars_}
                break

        ctx.update({"completed": completed, "vars": vars_})
        run.context_json = ctx
        if run.status == "running" and cursor is None:
            run.status = "completed"
            run.result_json = {"completed_nodes": completed, "vars": vars_}

    def _next_node(
        self, current: str, edges: list[dict[str, Any]], vars_: dict[str, Any]
    ) -> str | None:
        router_target = vars_.pop("_router_target", None)
        if router_target:
            return str(router_target)

        candidates = [e for e in edges if e.get("from") == current]
        if not candidates:
            return None
        cond = vars_.get("_last_condition")
        if cond is not None:
            for edge in candidates:
                when = edge.get("when")
                if when is None:
                    continue
                if bool(when) == bool(cond):
                    return edge.get("to")
        return candidates[0].get("to")
