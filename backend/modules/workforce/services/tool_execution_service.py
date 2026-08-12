"""Unified tool execution for workflows and orchestration callers."""

from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.tool_execution_context import (
    ToolExecutionContext,
    arguments_hash,
)
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask
from backend.modules.workforce.services.action_policy import DECISION_PROHIBITED
from backend.modules.workforce.services.tool_registry import ToolRegistryService

_NATIVE_EXECUTABLE = frozenset(
    {
        "web_search",
        "web_fetch",
        "fs_read",
        "knowledge_search",
        "repo_search",
        "code_execute",
        "fs_write",
        "db_query",
        "github_comment",
        "github_label_issue",
        "github_create_pr",
    }
)


class ToolExecutionService:
    """Authorize via ToolRegistry and execute native tools through OrchestrationToolbox."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db
        self.registry = ToolRegistryService(db)

    async def execute(
        self,
        owner_id: str,
        tool_slug: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        auth = await self.registry.authorize_tool(owner_id, tool_slug, context)
        if not auth.get("permitted"):
            return self._normalize(
                tool_slug,
                {"status": "denied", "reason": "not_permitted", **auth},
            )
        if auth.get("decision") == DECISION_PROHIBITED:
            return self._normalize(
                tool_slug,
                {"status": "denied", "reason": "prohibited", **auth},
            )
        if auth.get("decision") == "approval_required" and not context.get("approval_granted"):
            return self._normalize(
                tool_slug,
                {"status": "approval_required", **auth},
            )

        project_id = context.get("project_id")
        if project_id and (
            tool_slug in _NATIVE_EXECUTABLE or tool_slug.startswith(("github_", "mcp.", "a2a."))
        ):
            output = await self._execute_via_toolbox(
                owner_id=owner_id,
                tool_slug=tool_slug,
                params=params,
                context=context,
            )
            return self._normalize(tool_slug, output)

        provider_result = await self.registry.execute_tool(owner_id, tool_slug, params, context)
        return self._normalize(tool_slug, provider_result)

    async def _execute_via_toolbox(
        self,
        *,
        owner_id: str,
        tool_slug: str,
        params: dict[str, Any],
        context: dict[str, Any],
    ) -> dict[str, Any]:
        project_id = str(context.get("project_id") or "")
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            return {"status": "failed", "error": "project not found for tool execution"}

        task: OrchestratorTask | None = None
        task_id = context.get("task_id")
        if task_id:
            task = await self.db.get(OrchestratorTask, str(task_id))

        skill_ids = tuple(str(v) for v in (context.get("skill_version_ids") or []) if v)
        allowed = tuple(str(t) for t in (context.get("allowed_tools") or []) if t)
        required = tuple(str(t) for t in (context.get("skill_required_tools") or []) if t)
        tool_ctx = ToolExecutionContext(
            owner_id=owner_id,
            project_id=project.id,
            triggered_by_user_id=str(
                context.get("triggered_by_user_id") or context.get("owner_id") or owner_id
            ),
            task_id=task.id if task else None,
            task_run_id=(
                str(context["task_run_id"])
                if context.get("task_run_id")
                else (str(context["run_id"]) if context.get("run_id") and not context.get("workflow_run_id") else None)
            ),
            workflow_run_id=(
                str(context["workflow_run_id"]) if context.get("workflow_run_id") else None
            ),
            workflow_node_id=(
                str(context["workflow_node_id"]) if context.get("workflow_node_id") else None
            ),
            company_id=context.get("company_id") or getattr(project, "company_id", None),
            department_id=context.get("department_id") or getattr(project, "department_id", None),
            agent_id=context.get("agent_id"),
            skill_version_ids=skill_ids,
            approval_request_id=context.get("approval_request_id"),
            approval_granted=bool(context.get("approval_granted")),
            arguments_hash=context.get("arguments_hash") or arguments_hash(params),
            allowed_tools=allowed,
            skill_required_tools=required,
        )

        toolbox = OrchestrationToolbox(
            db=self.db,
            repo=OrchestrationRepository(self.db),
            project=project,
            task=task,
            run=None,
            context=tool_ctx,
        )
        try:
            result = await toolbox.dispatch(tool_slug, params)
            return {"status": "succeeded", "output": result}
        except ToolExecutionError as exc:
            message = str(exc)
            if message.startswith("APPROVAL_REQUIRED"):
                return {"status": "approval_required", "error": message}
            return {"status": "failed", "error": message}

    @staticmethod
    def _normalize(tool_slug: str, raw: dict[str, Any]) -> dict[str, Any]:
        status = str(raw.get("status") or "succeeded")
        if status == "delegated" and raw.get("output") is None:
            status = "succeeded" if "error" not in raw else "failed"
        output = raw.get("output")
        if output is None and status == "succeeded":
            output = {k: v for k, v in raw.items() if k not in {"status", "tool_slug", "evidence"}}
        evidence = raw.get("evidence")
        if evidence is None and isinstance(output, dict):
            evidence = output.get("evidence")
        return {
            "status": status,
            "tool_slug": tool_slug,
            "output": output,
            "evidence": evidence,
            **{
                k: v
                for k, v in raw.items()
                if k not in {"status", "tool_slug", "output", "evidence"}
            },
        }


def hash_tool_arguments(params: dict[str, Any] | None) -> str:
    return arguments_hash(params)
