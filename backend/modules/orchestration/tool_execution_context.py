"""Server-owned tool execution context — never trust model tool-call payloads."""

from __future__ import annotations

import os
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.models import TaskRun
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.team.models import AgentProfile

# Low-risk tools that may optionally fail-open when TOOL_POLICY_FAIL_OPEN=1
_LOW_RISK_TOOLS = {
    "web_search",
    "web_fetch",
    "knowledge_search",
    "repo_search",
    "fs_read",
}


def policy_fail_open_enabled() -> bool:
    return os.getenv("TOOL_POLICY_FAIL_OPEN", "").lower() in {"1", "true", "yes"}


async def build_tool_execution_context(
    db: AsyncSession,
    *,
    project: OrchestratorProject,
    task: OrchestratorTask | None,
    run: TaskRun,
    tool_name: str,
) -> dict[str, Any]:
    """Construct authorization context from durable server state only."""
    agent_id = getattr(run, "agent_id", None) or getattr(run, "worker_agent_id", None)
    allowed_tools: list[str] = []
    if agent_id:
        agent = await db.get(AgentProfile, agent_id)
        if agent is not None:
            allowed_tools = [str(t) for t in (agent.allowed_tools_json or []) if t]

    approval_granted = await _has_durable_tool_approval(
        db,
        owner_id=str(project.owner_id),
        tool_name=tool_name,
        run_id=getattr(run, "id", None),
        task_id=task.id if task else None,
        project_id=project.id,
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
        "approval_granted": approval_granted,
    }


async def _has_durable_tool_approval(
    db: AsyncSession,
    *,
    owner_id: str,
    tool_name: str,
    run_id: str | None,
    task_id: str | None,
    project_id: str | None,
) -> bool:
    """Look for an approved ApprovalRequest covering this tool/action."""
    try:
        from backend.modules.orchestration.models import ApprovalRequest
    except Exception:
        return False

    clauses = [ApprovalRequest.status == "approved"]
    if project_id:
        clauses.append(ApprovalRequest.project_id == project_id)
    stmt = (
        select(ApprovalRequest)
        .where(*clauses)
        .order_by(ApprovalRequest.created_at.desc())
        .limit(50)
    )
    result = await db.execute(stmt)
    rows = list(result.scalars().all())
    for row in rows:
        payload = getattr(row, "payload_json", None) or {}
        if not isinstance(payload, dict):
            payload = {}
        action = str(
            payload.get("action")
            or payload.get("tool")
            or payload.get("action_key")
            or getattr(row, "approval_type", "")
            or ""
        )
        if run_id and row.run_id and row.run_id != run_id:
            continue
        if task_id and row.task_id and row.task_id != task_id:
            continue
        if action in {tool_name, f"tool:{tool_name}", f"execute:{tool_name}"}:
            return True
        if run_id and row.run_id == run_id and action in {"tool_execution", "tool", "approval"}:
            # Run-scoped generic approval for the pending tool
            if payload.get("tool") in {None, "", tool_name}:
                return True
    _ = owner_id
    return False


def may_fail_open(tool_name: str) -> bool:
    if not policy_fail_open_enabled():
        return False
    if tool_name.startswith("mcp.") or tool_name.startswith("a2a."):
        return False
    if tool_name.startswith("github_"):
        return False
    return tool_name in _LOW_RISK_TOOLS
