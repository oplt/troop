"""Server-owned tool execution context — never trust model tool-call payloads."""

from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm.attributes import flag_modified

from backend.modules.orchestration.models import ApprovalRequest, TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.team.models import AgentProfile

# Low-risk tools that may optionally fail-open when TOOL_POLICY_FAIL_OPEN=1
# and may accept approvals without arguments_hash (still consume once).
_LOW_RISK_TOOLS = {
    "web_search",
    "web_fetch",
    "knowledge_search",
    "repo_search",
    "fs_read",
}


@dataclass(frozen=True)
class ToolExecutionContext:
    """Neutral immutable context for tool dispatch (TaskRun or WorkflowRun)."""

    owner_id: str
    project_id: str
    triggered_by_user_id: str | None = None
    task_id: str | None = None
    task_run_id: str | None = None
    workflow_run_id: str | None = None
    workflow_node_id: str | None = None
    company_id: str | None = None
    department_id: str | None = None
    agent_id: str | None = None
    skill_version_ids: tuple[str, ...] = ()
    approval_request_id: str | None = None
    approval_granted: bool = False
    arguments_hash: str | None = None
    allowed_tools: tuple[str, ...] = ()
    skill_required_tools: tuple[str, ...] = ()
    extras: dict[str, Any] = field(default_factory=dict)

    @property
    def id(self) -> str | None:
        """Event/query id: prefer TaskRun, else WorkflowRun (never invent a TaskRun)."""
        return self.task_run_id or self.workflow_run_id

    def to_auth_dict(self) -> dict[str, Any]:
        payload = {
            "owner_id": self.owner_id,
            "project_id": self.project_id,
            "task_id": self.task_id,
            "company_id": self.company_id,
            "department_id": self.department_id,
            "agent_id": self.agent_id,
            "run_id": self.task_run_id,
            "task_run_id": self.task_run_id,
            "workflow_run_id": self.workflow_run_id,
            "workflow_node_id": self.workflow_node_id,
            "allowed_tools": list(self.allowed_tools),
            "skill_required_tools": list(self.skill_required_tools),
            "skill_version_ids": list(self.skill_version_ids),
            "arguments_hash": self.arguments_hash,
            "approval_granted": self.approval_granted,
            "approval_request_id": self.approval_request_id,
        }
        payload.update(self.extras)
        return payload


def policy_fail_open_enabled() -> bool:
    return os.getenv("TOOL_POLICY_FAIL_OPEN", "").lower() in {"1", "true", "yes"}


def is_low_risk_tool(tool_name: str) -> bool:
    if tool_name.startswith("mcp.") or tool_name.startswith("a2a."):
        return False
    if tool_name.startswith("github_"):
        return False
    return tool_name in _LOW_RISK_TOOLS


def arguments_hash(arguments: dict[str, Any] | None) -> str:
    payload = arguments if isinstance(arguments, dict) else {}
    encoded = json.dumps(payload, sort_keys=True, default=str, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


def skill_version_ids_from_run(run: TaskRun) -> list[str]:
    checkpoint = dict(run.checkpoint_json or {})
    snapshot = checkpoint.get("skill_version_snapshot") or {}
    ids = snapshot.get("skill_version_ids") or []
    return [str(v) for v in ids if v]


def required_tools_from_run(run: TaskRun) -> list[str]:
    checkpoint = dict(run.checkpoint_json or {})
    snapshot = checkpoint.get("skill_version_snapshot") or {}
    tools = snapshot.get("required_tools") or []
    return [str(t) for t in tools if t]


async def build_tool_execution_context(
    db: AsyncSession,
    *,
    project: OrchestratorProject,
    task: OrchestratorTask | None,
    run: TaskRun,
    tool_name: str,
    arguments: dict[str, Any] | None = None,
    consume_approval: bool = False,
    require_arguments_hash: bool | None = None,
) -> dict[str, Any]:
    """Construct authorization context from durable server state only.

    SkillVersions may *request* tools; AgentProfile declares tools; ToolGrant /
    ActionPolicy authorize. Approvals are one-time grants bound to tool+args.
    """
    agent_id = getattr(run, "agent_id", None) or getattr(run, "worker_agent_id", None)
    declared_tools: list[str] = []
    if agent_id:
        agent = await db.get(AgentProfile, agent_id)
        if agent is not None:
            declared_tools = [str(t) for t in (agent.allowed_tools_json or []) if t]

    skill_required = required_tools_from_run(run)
    # Declared tools are the hard ceiling; skill-required never grants by itself.
    allowed_tools = list(declared_tools)

    args_hash = arguments_hash(arguments)
    # High-risk / governed tools always require an exact arguments_hash on the grant.
    if require_arguments_hash is None:
        require_arguments_hash = not is_low_risk_tool(tool_name)

    approval_granted = await consume_or_check_tool_approval(
        db,
        owner_id=str(project.owner_id),
        tool_name=tool_name,
        arguments_hash=args_hash,
        run_id=getattr(run, "id", None),
        task_id=task.id if task else None,
        project_id=project.id,
        agent_id=agent_id,
        consume=consume_approval,
        require_arguments_hash=require_arguments_hash,
    )

    return {
        "owner_id": str(project.owner_id),
        "project_id": project.id,
        "task_id": task.id if task else None,
        "company_id": getattr(project, "company_id", None),
        "department_id": getattr(project, "department_id", None),
        "agent_id": agent_id,
        "run_id": getattr(run, "id", None),
        "allowed_tools": allowed_tools,
        "skill_required_tools": skill_required,
        "skill_version_ids": skill_version_ids_from_run(run),
        "arguments_hash": args_hash,
        "approval_granted": approval_granted,
    }


async def consume_or_check_tool_approval(
    db: AsyncSession,
    *,
    owner_id: str,
    tool_name: str,
    arguments_hash: str,
    run_id: str | None,
    task_id: str | None,
    project_id: str | None,
    agent_id: str | None,
    consume: bool,
    require_arguments_hash: bool = True,
) -> bool:
    """Match one unconsumed ApprovalRequest grant for exact tool + arguments_hash.

    For governed/high-risk tools, ``arguments_hash`` on the grant is mandatory.
    Missing hash → not valid for a new high-risk call.
    """
    clauses = [ApprovalRequest.status == "approved"]
    if project_id:
        clauses.append(ApprovalRequest.project_id == project_id)
    if run_id:
        clauses.append(ApprovalRequest.run_id == run_id)

    result = await db.execute(
        select(ApprovalRequest)
        .where(*clauses)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(50)
    )
    rows = list(result.scalars().all())
    for row in rows:
        payload = dict(row.payload_json or {})
        if payload.get("_consumed_at") or payload.get("consumed_at"):
            continue

        payload_owner = str(
            payload.get("owner_id") or row.requested_by_user_id or row.approved_by_user_id or ""
        )
        if (
            payload_owner
            and payload_owner != owner_id
            and str(row.requested_by_user_id or "") not in {"", owner_id}
            and not row.project_id
        ):
            continue

        action = str(
            payload.get("action_key")
            or payload.get("action")
            or payload.get("tool")
            or row.approval_type
            or ""
        )
        exact_tools = {
            tool_name,
            f"tool:{tool_name}",
            f"execute:{tool_name}",
            f"tool_execution:{tool_name}",
        }
        if action not in exact_tools and row.approval_type not in exact_tools:
            continue
        if task_id and row.task_id and row.task_id != task_id:
            continue
        if agent_id and payload.get("agent_id") and str(payload.get("agent_id")) != agent_id:
            continue

        grant_hash = str(payload.get("arguments_hash") or "").strip()
        if require_arguments_hash:
            if not grant_hash or grant_hash != arguments_hash:
                continue
        elif grant_hash and grant_hash != arguments_hash:
            continue

        if consume:
            payload["_consumed_at"] = datetime.now(UTC).isoformat()
            payload["consumed_at"] = payload["_consumed_at"]
            payload["consumed_for_tool"] = tool_name
            payload["consumed_arguments_hash"] = arguments_hash
            row.payload_json = payload
            flag_modified(row, "payload_json")
            await db.flush()
        return True
    return False


def may_fail_open(tool_name: str) -> bool:
    if not policy_fail_open_enabled():
        return False
    return is_low_risk_tool(tool_name)
