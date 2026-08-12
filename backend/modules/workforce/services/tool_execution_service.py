"""Unified tool execution for workflows and orchestration callers."""

from __future__ import annotations

from typing import Any
from uuid import uuid4

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.tool_execution_context import arguments_hash
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

        from backend.modules.orchestration.models import TaskRun

        run = TaskRun(
            id=str(context.get("run_id") or context.get("workflow_run_id") or uuid4()),
            project_id=project.id,
            task_id=task.id if task else None,
            worker_agent_id=context.get("agent_id"),
            triggered_by_user_id=owner_id,
            status="running",
            run_mode="workflow_tool",
            input_payload_json={},
            output_payload_json={},
            checkpoint_json={},
        )

        toolbox = OrchestrationToolbox(
            db=self.db,
            repo=OrchestrationRepository(self.db),
            project=project,
            task=task,
            run=run,
        )
        try:
            result = await toolbox.execute({"tool": tool_slug, "arguments": params})
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
