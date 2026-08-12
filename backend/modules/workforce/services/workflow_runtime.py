"""Minimal durable workflow graph runner for workforce WorkflowDefinition graphs.

Uses WorkflowVersion.nodes_json / edges_json / entry_node_id and persists
WorkflowRun + WorkflowStepRun. Agent/tool nodes are recorded as delegated
steps — heavy execution remains in orchestration.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.models import (
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


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


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
        definition = await self.get_definition(owner_id, workflow_id)
        if not definition.current_version_id:
            raise ValueError("workflow has no published version")
        version = await self.get_version(definition.current_version_id)
        if version is None:
            raise ValueError("workflow version missing")
        nodes = list(version.nodes_json or [])
        edges = list(version.edges_json or [])
        errors = self.validate_graph(
            nodes=nodes, edges=edges, entry_node_id=version.entry_node_id
        )
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
        await self._advance(run, version)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def resume_run(
        self, owner_id: str, run_id: str, *, approval_granted: bool = False
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
        if approval_granted:
            vars_["approval_granted"] = True
        ctx["vars"] = vars_
        run.context_json = ctx
        run.status = "running"
        await self._advance(run, version)
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def _advance(self, run: WorkflowRun, version: WorkflowVersion) -> None:
        nodes = {
            n["id"]: n
            for n in (version.nodes_json or [])
            if isinstance(n, dict) and n.get("id")
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
            if ntype in {"approval", "human_input"}:
                if vars_.get("approval_granted") and ntype == "approval":
                    step.status = "succeeded"
                    step.output_json = {"approved": True}
                    step.finished_at = _utcnow()
                    vars_.pop("approval_granted", None)
                else:
                    step.status = "paused"
                    step.finished_at = _utcnow()
                    run.status = "waiting_approval" if ntype == "approval" else "waiting_input"
                    run.current_node_id = cursor
                    ctx.update({"completed": completed, "vars": vars_})
                    run.context_json = ctx
                    return
            elif ntype == "condition":
                expr = bool((node.get("config") or {}).get("when", True))
                step.status = "succeeded"
                step.output_json = {"branch": bool(expr)}
                step.finished_at = _utcnow()
                vars_["_last_condition"] = bool(expr)
            elif ntype == "delay":
                step.status = "succeeded"
                step.output_json = {"delayed": True}
                step.finished_at = _utcnow()
            elif ntype == "parallel":
                children = list((node.get("config") or {}).get("children") or [])
                step.status = "succeeded"
                step.output_json = {"children": children, "mode": "fan_out_recorded"}
                step.finished_at = _utcnow()
            else:
                step.status = "succeeded"
                step.output_json = {
                    "delegated": True,
                    "node_type": ntype,
                    "message": "Node recorded; execution delegated to orchestration runtime",
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
