from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.orchestration.execution.cpu_executor import execute_code_job_async
from backend.modules.orchestration.filesystem_tools import (
    FilesystemToolError,
    read_bounded_text,
    write_bounded_text,
)
from backend.modules.orchestration.models import (
    GithubConnection,
    GithubIssueLink,
    GithubRepository,
    OrchestratorProject,
    OrchestratorTask,
    ProjectDocument,
    ProjectDocumentChunk,
    RunEvent,
    TaskArtifact,
    TaskRun,
)
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.identity_access.models import User

PROJECT_ROOT = Path(__file__).resolve().parents[3]


class ToolExecutionError(RuntimeError):
    pass


class OrchestrationToolbox:
    def __init__(
        self,
        *,
        db: AsyncSession,
        repo: OrchestrationRepository,
        project: OrchestratorProject,
        task: OrchestratorTask | None,
        run: TaskRun | None = None,
        context: Any | None = None,
    ) -> None:
        self.db = db
        self.repo = repo
        self.project = project
        self.task = task
        # Prefer neutral ToolExecutionContext; keep TaskRun for legacy agent runs.
        if context is not None:
            self.ctx = context
            self.run = context if run is None else run
        else:
            self.run = run
            self.ctx = run

    @property
    def _actor_user_id(self) -> str | None:
        ctx = self.ctx
        if ctx is None:
            return None
        return getattr(ctx, "triggered_by_user_id", None) or getattr(ctx, "owner_id", None)

    @property
    def _event_run_id(self) -> str | None:
        ctx = self.ctx
        if ctx is None:
            return None
        return (
            getattr(ctx, "task_run_id", None)
            or getattr(ctx, "id", None)
            or getattr(ctx, "workflow_run_id", None)
        )

    async def execute(self, call: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(call.get("tool") or "").strip()
        arguments = call.get("arguments") or {}
        if not tool_name:
            raise ToolExecutionError("Tool call is missing a tool name")

        from backend.modules.orchestration.tool_execution_context import (
            ToolExecutionContext,
            build_tool_execution_context,
            may_fail_open,
        )
        from backend.modules.workforce.services.tool_registry import ToolRegistryService

        # Never trust model-supplied allowed_tools / approval_granted.
        if isinstance(self.run, TaskRun):
            context = await build_tool_execution_context(
                self.db,
                project=self.project,
                task=self.task,
                run=self.run,
                tool_name=tool_name,
                arguments=arguments if isinstance(arguments, dict) else {},
                consume_approval=False,
            )
        elif isinstance(self.ctx, ToolExecutionContext):
            context = self.ctx.to_auth_dict()
        else:
            raise ToolExecutionError("Tool execution requires TaskRun or ToolExecutionContext")

        try:
            registry = ToolRegistryService(self.db)
            owner_id = context.get("owner_id")
            if not owner_id:
                raise ToolExecutionError("Tool execution requires a project owner")
            auth = await registry.authorize_tool(str(owner_id), tool_name, context)
            if not auth.get("permitted"):
                raise ToolExecutionError(
                    f"Tool `{tool_name}` is not permitted for this agent/context "
                    f"({(auth.get('resolution') or {}).get('matched_scope') or 'allowlist/grants'})"
                )
            decision = auth.get("decision")
            if decision == "prohibited":
                raise ToolExecutionError(
                    f"Tool `{tool_name}` is prohibited by action policy "
                    f"({(auth.get('resolution') or {}).get('matched_scope') or 'policy'})"
                )
            if decision == "approval_required":
                if isinstance(self.run, TaskRun):
                    granted = await build_tool_execution_context(
                        self.db,
                        project=self.project,
                        task=self.task,
                        run=self.run,
                        tool_name=tool_name,
                        arguments=arguments if isinstance(arguments, dict) else {},
                        consume_approval=True,
                        require_arguments_hash=True,
                    )
                    if not granted.get("approval_granted"):
                        raise ToolExecutionError(
                            f"APPROVAL_REQUIRED: Tool `{tool_name}` requires approval "
                            f"({(auth.get('resolution') or {}).get('matched_scope') or 'policy'})"
                        )
                    context["approval_granted"] = True
                elif not context.get("approval_granted"):
                    raise ToolExecutionError(
                        f"APPROVAL_REQUIRED: Tool `{tool_name}` requires approval "
                        f"({(auth.get('resolution') or {}).get('matched_scope') or 'policy'})"
                    )
        except ToolExecutionError:
            raise
        except Exception as exc:
            # Fail closed for governed / high-risk tools. Optional fail-open only for
            # explicitly allowlisted low-risk tools when TOOL_POLICY_FAIL_OPEN=1.
            if may_fail_open(tool_name):
                pass
            else:
                raise ToolExecutionError(
                    f"Tool `{tool_name}` authorization failed closed: {exc}"
                ) from exc

        from backend.modules.workforce.services.tool_execution_service import ToolExecutionService

        service = ToolExecutionService(self.db)
        owner_id = str(context.get("owner_id") or "")
        if not owner_id:
            raise ToolExecutionError("Tool execution requires a project owner")
        result = await service.execute(
            owner_id,
            tool_name,
            arguments if isinstance(arguments, dict) else {},
            context,
        )
        status = str(result.get("status") or "")
        if status == "approval_required":
            raise ToolExecutionError(
                f"APPROVAL_REQUIRED: Tool `{tool_name}` requires approval "
                f"({result.get('reason') or 'policy'})"
            )
        if status in {"denied", "failed", "error"}:
            raise ToolExecutionError(
                f"Tool `{tool_name}` {status}: {result.get('error') or result.get('reason')}"
            )
        output = result.get("output")
        if isinstance(output, dict):
            return output
        if output is not None:
            return {"result": output}
        if status in {"succeeded", "completed"}:
            return {k: v for k, v in result.items() if k not in {"status", "tool_slug", "evidence"}}
        return result

    async def dispatch(
        self, tool_name: str, arguments: dict[str, Any] | None = None
    ) -> dict[str, Any]:
        """Pure tool dispatch — no authorization (caller must authorize first)."""
        tool_name = str(tool_name or "").strip()
        arguments = arguments if isinstance(arguments, dict) else {}
        if not tool_name:
            raise ToolExecutionError("Tool call is missing a tool name")

        if tool_name == "github_comment":
            return await self._github_comment(arguments)
        if tool_name == "github_label_issue":
            return await self._github_label_issue(arguments)
        if tool_name == "github_create_pr":
            return await self._github_create_pr(arguments)
        if tool_name == "web_fetch":
            return await self._web_fetch(arguments)
        if tool_name == "web_search":
            return await self._web_search(arguments)
        if tool_name == "code_execute":
            return await self._code_execute(arguments)
        if tool_name == "fs_read":
            return await self._fs_read(arguments)
        if tool_name == "fs_write":
            return await self._fs_write(arguments)
        if tool_name == "db_query":
            return await self._db_query(arguments)
        if tool_name == "repo_search":
            return await self._repo_search(arguments)
        if tool_name == "knowledge_search":
            return await self._knowledge_search(arguments)
        if tool_name == "invoke_specialist":
            return await self._invoke_specialist(arguments)

        if tool_name.startswith("mcp.") or tool_name.startswith("a2a."):
            from backend.modules.orchestration.tool_execution_context import (
                build_tool_execution_context,
            )
            from backend.modules.workforce.services.tool_registry import ToolRegistryService

            context = await build_tool_execution_context(
                self.db,
                project=self.project,
                task=self.task,
                run=self.run,
                tool_name=tool_name,
                arguments=arguments,
                consume_approval=False,
            )
            owner_id = context.get("owner_id")
            if not owner_id:
                raise ToolExecutionError("MCP/A2A tools require a project owner")
            registry = ToolRegistryService(self.db)
            result = await registry.execute_tool(
                str(owner_id),
                tool_name,
                arguments,
                context,
            )
            if result.get("status") == "approval_required":
                raise ToolExecutionError(
                    f"APPROVAL_REQUIRED: {tool_name} requires approval before execution"
                )
            if result.get("status") in {"denied", "failed", "error"}:
                raise ToolExecutionError(
                    f"{tool_name} {result.get('status')}: {result.get('error') or result.get('decision')}"
                )
            return result

        raise ToolExecutionError(f"Unsupported tool: {tool_name}")

    def _workspace_root(self) -> Path:
        configured = (self.project.settings_json or {}).get("workspace_root")
        candidate = Path(configured).expanduser().resolve() if configured else PROJECT_ROOT
        if not candidate.exists():
            return PROJECT_ROOT
        return candidate

    def _resolve_scoped_path(self, relative_path: str) -> Path:
        root = self._workspace_root()
        resolved = (root / relative_path).resolve()
        if root != resolved and root not in resolved.parents:
            raise ToolExecutionError("Path escapes the project workspace scope")
        return resolved

    async def _resolve_issue_context(
        self, arguments: dict[str, Any]
    ) -> tuple[GithubConnection, GithubRepository, GithubIssueLink | None, int]:
        owner_id = self.project.owner_id
        project_id = self.project.id
        issue_link: GithubIssueLink | None = None
        issue_link_id = arguments.get("issue_link_id") or (
            self.task.github_issue_link_id if self.task else None
        )
        repository: GithubRepository | None = None
        if issue_link_id:
            issue_link = await self.repo.resolve_authorized_issue_link(
                owner_id,
                str(issue_link_id),
                project_id=project_id,
            )
            if issue_link is None:
                raise ToolExecutionError("GitHub resource is not authorized for this workspace")
            repository = await self.repo.resolve_authorized_repository(
                owner_id,
                project_id=project_id,
                repository_id=issue_link.repository_id,
            )
            issue_number = issue_link.issue_number
        else:
            issue_number = int(arguments.get("issue_number", 0))
            repository_id = arguments.get("repository_id")
            full_name = arguments.get("repository_full_name")
            if repository_id or full_name:
                repository = await self.repo.resolve_authorized_repository(
                    owner_id,
                    project_id=project_id,
                    repository_id=str(repository_id) if repository_id else None,
                    full_name=str(full_name) if full_name else None,
                )
        if repository is None:
            if issue_number <= 0:
                raise ToolExecutionError("GitHub tool call requires a repository and issue context")
            raise ToolExecutionError("GitHub resource is not authorized for this workspace")
        if issue_number <= 0:
            raise ToolExecutionError("GitHub tool call requires a repository and issue context")
        connection = await self.repo.get_github_connection(owner_id, repository.connection_id)
        if connection is None:
            raise ToolExecutionError("GitHub resource is not authorized for this workspace")
        return connection, repository, issue_link, issue_number

    async def _github_auth_headers(self, connection: GithubConnection) -> dict[str, str]:
        from fastapi import HTTPException

        from backend.modules.github.http_client import auth_headers as github_auth_headers

        try:
            return await github_auth_headers(connection)
        except HTTPException as exc:
            detail = exc.detail if isinstance(exc.detail, str) else "GitHub auth failed"
            raise ToolExecutionError(str(detail)) from exc

    async def _github_comment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        body = str(arguments.get("body") or "").strip()
        if not body:
            raise ToolExecutionError("GitHub comment body is required")
        close_issue = bool(arguments.get("close_issue", False))
        connection, repository, issue_link, issue_number = await self._resolve_issue_context(
            arguments
        )
        headers = await self._github_auth_headers(connection)
        async with managed_http_client(
            "github-tools", timeout_seconds=30.0, base_url=connection.api_url
        ) as client:
            response = await client.post(
                f"/repos/{repository.full_name}/issues/{issue_number}/comments",
                headers=headers,
                json={"body": body},
            )
            if response.status_code >= 400:
                raise ToolExecutionError(f"GitHub comment failed: {response.text[:300]}")
            if close_issue:
                close_response = await client.patch(
                    f"/repos/{repository.full_name}/issues/{issue_number}",
                    headers=headers,
                    json={"state": "closed"},
                )
                if close_response.status_code >= 400:
                    raise ToolExecutionError(
                        f"GitHub close issue failed: {close_response.text[:300]}"
                    )
        return {
            "repository": repository.full_name,
            "issue_number": issue_number,
            "comment_posted": True,
            "close_issue": close_issue,
            "issue_link_id": issue_link.id if issue_link else None,
        }

    async def _github_label_issue(self, arguments: dict[str, Any]) -> dict[str, Any]:
        labels = [str(item).strip() for item in arguments.get("labels", []) if str(item).strip()]
        if not labels:
            raise ToolExecutionError("At least one label is required")
        connection, repository, issue_link, issue_number = await self._resolve_issue_context(
            arguments
        )
        headers = await self._github_auth_headers(connection)
        async with managed_http_client(
            "github-tools", timeout_seconds=30.0, base_url=connection.api_url
        ) as client:
            response = await client.post(
                f"/repos/{repository.full_name}/issues/{issue_number}/labels",
                headers=headers,
                json={"labels": labels},
            )
            if response.status_code >= 400:
                raise ToolExecutionError(f"GitHub label update failed: {response.text[:300]}")
        if issue_link is not None:
            issue_link.labels_json = sorted(set([*(issue_link.labels_json or []), *labels]))
            await self.db.flush()
        return {
            "repository": repository.full_name,
            "issue_number": issue_number,
            "labels": labels,
            "issue_link_id": issue_link.id if issue_link else None,
        }

    async def _github_create_pr(self, arguments: dict[str, Any]) -> dict[str, Any]:
        title = str(arguments.get("title") or "").strip()
        head = str(arguments.get("head") or "").strip()
        base = str(arguments.get("base") or "").strip()
        if not title or not head or not base:
            raise ToolExecutionError("Pull request creation requires title, head, and base")
        repository_id = arguments.get("repository_id")
        repository_full_name = arguments.get("repository_full_name")
        repository = await self.repo.resolve_authorized_repository(
            self.project.owner_id,
            project_id=self.project.id,
            repository_id=str(repository_id) if repository_id else None,
            full_name=str(repository_full_name) if repository_full_name else None,
        )
        if repository is None:
            raise ToolExecutionError("GitHub resource is not authorized for this workspace")
        connection = await self.repo.get_github_connection(
            self.project.owner_id, repository.connection_id
        )
        if connection is None:
            raise ToolExecutionError("GitHub resource is not authorized for this workspace")
        headers = await self._github_auth_headers(connection)
        async with managed_http_client(
            "github-tools", timeout_seconds=30.0, base_url=connection.api_url
        ) as client:
            response = await client.post(
                f"/repos/{repository.full_name}/pulls",
                headers=headers,
                json={
                    "title": title,
                    "head": head,
                    "base": base,
                    "body": arguments.get("body") or "",
                    "draft": bool(arguments.get("draft", False)),
                },
            )
            if response.status_code >= 400:
                raise ToolExecutionError(f"GitHub PR creation failed: {response.text[:300]}")
        payload = response.json()
        return {
            "repository": repository.full_name,
            "pr_number": payload.get("number"),
            "pr_url": payload.get("html_url"),
            "title": title,
        }

    async def _web_fetch(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from backend.modules.workforce.services.outbound_url import (
            UnsafeURLError,
            safe_outbound_request,
            validate_outbound_url,
        )

        url = str(arguments.get("url") or "").strip()
        try:
            url = validate_outbound_url(url)
        except UnsafeURLError as exc:
            raise ToolExecutionError(f"web_fetch blocked unsafe URL: {exc}") from exc
        async with managed_http_client(
            "web-tools",
            timeout_seconds=float(arguments.get("timeout_seconds", 20)),
        ) as client:
            try:
                response = await safe_outbound_request("GET", url, client=client)
            except UnsafeURLError as exc:
                raise ToolExecutionError(f"web_fetch blocked unsafe redirect: {exc}") from exc
        if response.status_code >= 400:
            raise ToolExecutionError(f"Fetch failed with status {response.status_code}")
        text = response.text[: int(arguments.get("max_chars", 5000))]
        return {
            "url": str(response.url),
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "body": text,
        }

    async def _web_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolExecutionError("web_search requires a query")
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        async with managed_http_client("web-tools", timeout_seconds=20.0) as client:
            response = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers=external_headers({"User-Agent": "troop-orchestrator/1.0"}),
            )
        if response.status_code >= 400:
            raise ToolExecutionError(f"Search failed with status {response.status_code}")
        matches = re.findall(
            r'<a[^>]+class="result__a"[^>]+href="(?P<href>[^"]+)"[^>]*>(?P<title>.*?)</a>',
            response.text,
            flags=re.IGNORECASE | re.DOTALL,
        )
        results = []
        for href, title in matches[:limit]:
            cleaned_title = re.sub(r"<.*?>", "", title).strip()
            results.append({"title": cleaned_title, "url": href})
        return {"query": query, "results": results}

    async def _code_execute(self, arguments: dict[str, Any]) -> dict[str, Any]:
        command = arguments.get("command")
        if isinstance(command, str):
            shell_cmd = command
            use_shell_wrap = True
        elif isinstance(command, list) and all(isinstance(item, str) for item in command):
            shell_cmd = " ".join(command)
            use_shell_wrap = False
        else:
            raise ToolExecutionError("code_execute requires a string command or string list")

        timeout = max(1, min(int(arguments.get("timeout_seconds", 30)), 120))
        cwd = self._workspace_root()
        sandbox_mode = str(
            ((self.project.settings_json or {}).get("hitl") or {}).get("sandbox_mode")
            or "allow_host_fallback"
        )
        require_docker = sandbox_mode == "docker_required"
        if settings.CELERY_TASK_ALWAYS_EAGER:
            result = await execute_code_job_async(
                shell_cmd=shell_cmd,
                cwd=str(cwd),
                timeout=timeout,
                use_shell_wrap=use_shell_wrap,
                require_docker=require_docker,
            )
        else:
            from backend.workers.orchestration import run_code_execution

            async_result = run_code_execution.apply_async(
                args=[shell_cmd, str(cwd), timeout, use_shell_wrap, require_docker],
                queue=settings.CELERY_QUEUE_CPU,
            )
            wait_timeout = timeout + 20
            configured = settings.ORCHESTRATION_CPU_JOB_TIMEOUT_SECONDS
            if configured is not None:
                wait_timeout = max(wait_timeout, configured)
            try:
                from backend.workers.celery_async import await_celery_result

                result = await await_celery_result(
                    async_result, timeout_seconds=float(wait_timeout)
                )
            except TimeoutError as exc:
                raise ToolExecutionError(str(exc)) from exc
            if not isinstance(result, dict):
                raise ToolExecutionError("CPU worker returned an invalid code execution payload")
        if str(result.get("error") or "") == "docker_required_unavailable":
            raise ToolExecutionError(
                str(result.get("stderr") or "Docker sandbox required but unavailable.")
            )
        if sandbox_mode == "docker_required" and str(result.get("sandbox") or "host") != "docker":
            raise ToolExecutionError(
                "Sandbox policy requires Docker isolation, but execution fell back to host."
            )
        return result

    async def _fs_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(arguments.get("path") or "").strip()
        if not relative_path:
            raise ToolExecutionError("fs_read requires a project-scoped path")
        path = self._resolve_scoped_path(relative_path)
        try:
            text = await read_bounded_text(path)
        except FileNotFoundError as exc:
            raise ToolExecutionError(f"File does not exist: {relative_path}") from exc
        except FilesystemToolError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except OSError as exc:
            raise ToolExecutionError(f"Failed to read file: {relative_path}") from exc
        max_chars = max(1, min(int(arguments.get("max_chars", 5000)), 50000))
        return {
            "path": relative_path,
            "absolute_path": str(path),
            "content": text[:max_chars],
            "truncated": len(text) > max_chars,
        }

    async def _fs_write(self, arguments: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(arguments.get("path") or "").strip()
        content = str(arguments.get("content") or "")
        if not relative_path:
            raise ToolExecutionError("fs_write requires a project-scoped path")
        path = self._resolve_scoped_path(relative_path)
        try:
            bytes_written = await write_bounded_text(path, content)
        except FilesystemToolError as exc:
            raise ToolExecutionError(str(exc)) from exc
        except OSError as exc:
            raise ToolExecutionError(f"Failed to write file: {relative_path}") from exc
        return {
            "path": relative_path,
            "absolute_path": str(path),
            "bytes_written": bytes_written,
        }

    async def _db_query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        entity = str(arguments.get("entity") or "").strip()
        filters = arguments.get("filters") or {}
        limit = max(1, min(int(arguments.get("limit", 10)), 100))
        if entity == "tasks":
            stmt = select(OrchestratorTask).where(OrchestratorTask.project_id == self.project.id)
            for key, value in filters.items():
                if key in {
                    "status",
                    "priority",
                    "assigned_agent_id",
                    "reviewer_agent_id",
                    "task_type",
                }:
                    stmt = stmt.where(getattr(OrchestratorTask, key) == value)
            rows = (await self.db.execute(stmt.limit(limit))).scalars().all()
            items = [
                {
                    "id": row.id,
                    "title": row.title,
                    "status": row.status,
                    "priority": row.priority,
                    "assigned_agent_id": row.assigned_agent_id,
                }
                for row in rows
            ]
            return {"entity": entity, "items": items}
        if entity == "runs":
            stmt = select(TaskRun).where(TaskRun.project_id == self.project.id)
            if "status" in filters:
                stmt = stmt.where(TaskRun.status == filters["status"])
            rows = (await self.db.execute(stmt.limit(limit))).scalars().all()
            items = [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "status": row.status,
                    "run_mode": row.run_mode,
                }
                for row in rows
            ]
            return {"entity": entity, "items": items}
        if entity == "documents":
            stmt = select(ProjectDocument).where(ProjectDocument.project_id == self.project.id)
            rows = (await self.db.execute(stmt.limit(limit))).scalars().all()
            items = [
                {
                    "id": row.id,
                    "filename": row.filename,
                    "summary_text": row.summary_text,
                    "task_id": row.task_id,
                }
                for row in rows
            ]
            return {"entity": entity, "items": items}
        if entity == "artifacts":
            stmt = (
                select(TaskArtifact)
                .join(OrchestratorTask, TaskArtifact.task_id == OrchestratorTask.id)
                .where(OrchestratorTask.project_id == self.project.id)
            )
            rows = (await self.db.execute(stmt.limit(limit))).scalars().all()
            items = [
                {
                    "id": row.id,
                    "task_id": row.task_id,
                    "kind": row.kind,
                    "title": row.title,
                }
                for row in rows
            ]
            return {"entity": entity, "items": items}
        if entity == "events":
            event_run_id = self._event_run_id
            if not event_run_id:
                return {"entity": entity, "items": []}
            stmt = (
                select(RunEvent)
                .where(RunEvent.run_id == event_run_id)
                .order_by(RunEvent.created_at.desc())
            )
            rows = (await self.db.execute(stmt.limit(limit))).scalars().all()
            items = [
                {
                    "id": row.id,
                    "event_type": row.event_type,
                    "message": row.message,
                    "created_at": row.created_at.isoformat(),
                }
                for row in rows
            ]
            return {"entity": entity, "items": items}
        raise ToolExecutionError(f"Unsupported db_query entity: {entity}")

    async def _repo_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolExecutionError("repo_search requires a query")
        limit = max(1, min(int(arguments.get("limit", 5)), 20))

        from backend.modules.rag.schemas import RagSearchFilters
        from backend.modules.rag.service import RagService

        rag = RagService(self.db)
        vector_matches = await rag.retrieve(
            query,
            filters=RagSearchFilters(
                project_id=self.project.id,
                user_id=self._actor_user_id,
                source_kind="repo_index",
            ),
            limit=limit,
        )
        if vector_matches:
            return {
                "query": query,
                "retrieval": "vector",
                "items": [
                    {
                        "project_document_id": match.document_id,
                        "chunk_index": match.chunk_index,
                        "score": match.score,
                        "content": match.content[:1000],
                        "path": (match.metadata or {}).get("path"),
                    }
                    for match in vector_matches
                ],
            }

        rows = (
            (
                await self.db.execute(
                    select(ProjectDocumentChunk)
                    .join(
                        ProjectDocument,
                        ProjectDocumentChunk.project_document_id == ProjectDocument.id,
                    )
                    .where(
                        ProjectDocumentChunk.project_id == self.project.id,
                        ProjectDocument.deleted_at.is_(None),
                        ProjectDocumentChunk.deleted_at.is_(None),
                        ProjectDocumentChunk.metadata_json["source_kind"].as_string()
                        == "repo_index",
                    )
                    .order_by(ProjectDocumentChunk.created_at.desc())
                    .limit(limit * 10)
                )
            )
            .scalars()
            .all()
        )
        query_terms = {term for term in re.findall(r"[a-z0-9_]+", query.lower()) if len(term) > 2}
        matches: list[dict[str, Any]] = []
        for row in rows:
            haystack = row.content.lower()
            score = sum(1 for term in query_terms if term in haystack)
            if score <= 0:
                continue
            matches.append(
                {
                    "project_document_id": row.project_document_id,
                    "chunk_index": row.chunk_index,
                    "score": score,
                    "content": row.content[:1000],
                    "path": (row.metadata_json or {}).get("path"),
                }
            )
        matches.sort(key=lambda item: item["score"], reverse=True)
        return {"query": query, "retrieval": "keyword", "items": matches[:limit]}

    async def _knowledge_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolExecutionError("knowledge_search requires a query")
        limit = max(1, min(int(arguments.get("limit", 5)), 20))
        include_decisions = bool(arguments.get("include_decisions", False))

        from backend.modules.rag.schemas import RagSearchFilters
        from backend.modules.rag.service import RagService

        actor_email: str | None = None
        if self._actor_user_id:
            actor = await self.db.get(User, self._actor_user_id)
            actor_email = actor.email if actor else None

        rag = RagService(self.db)
        matches = await rag.retrieve(
            query,
            filters=RagSearchFilters(
                project_id=self.project.id,
                user_id=self._actor_user_id,
                actor_email=actor_email,
                include_decisions=include_decisions,
            ),
            limit=limit,
        )
        return {
            "query": query,
            "retrieval": "vector",
            "items": [
                {
                    "document_id": match.document_id,
                    "chunk_id": match.chunk_id,
                    "chunk_index": match.chunk_index,
                    "score": match.score,
                    "title": match.title,
                    "content": match.content[:1200],
                    "hit_kind": match.hit_kind,
                }
                for match in matches
            ],
        }


    async def _invoke_specialist(self, arguments: dict[str, Any]) -> dict[str, Any]:
        from backend.modules.orchestration.execution.execution_workflow import ensure_workflow_state
        from backend.modules.orchestration.models import TaskRun
        from backend.modules.orchestration.services.execution_domain import ExecutionService

        run_id = self._event_run_id
        if not run_id:
            raise ToolExecutionError("invoke_specialist requires an active task run")
        parent = await self.db.get(TaskRun, str(run_id))
        if parent is None:
            raise ToolExecutionError("Parent task run not found")
        if parent.parent_run_id:
            raise ToolExecutionError("Specialist depth limit exceeded (max 1)")

        specialist_agent_id = str(arguments.get("specialist_agent_id") or "").strip()
        prompt = str(arguments.get("prompt") or arguments.get("task") or "").strip()
        if not specialist_agent_id or not prompt:
            raise ToolExecutionError("specialist_agent_id and prompt are required")

        payload = parent.input_payload_json or {}
        max_invocations = int(payload.get("max_specialist_invocations") or 3)
        children = await self.repo.list_child_runs(parent.id)
        specialist_children = [
            child
            for child in children
            if (child.input_payload_json or {}).get("specialist_invocation")
        ]
        if len(specialist_children) >= max_invocations:
            raise ToolExecutionError(
                f"Max specialist invocations ({max_invocations}) reached for this run"
            )

        child = await self.repo.create_run(
            parent_run_id=parent.id,
            project_id=parent.project_id,
            task_id=parent.task_id,
            triggered_by_user_id=parent.triggered_by_user_id,
            orchestrator_agent_id=parent.orchestrator_agent_id,
            worker_agent_id=specialist_agent_id,
            reviewer_agent_id=None,
            provider_config_id=parent.provider_config_id,
            brainstorm_id=parent.brainstorm_id,
            run_mode="single_agent",
            status="queued",
            model_name=parent.model_name,
            input_payload_json={
                "specialist_invocation": True,
                "specialist_prompt": prompt,
                "parent_run_id": parent.id,
                "orchestration_meta": {
                    "parent_run_id": parent.id,
                    "specialist_agent_id": specialist_agent_id,
                },
            },
        )
        child.checkpoint_json = ensure_workflow_state(
            child.checkpoint_json,
            run_mode=child.run_mode,
            steps=[],
            run_id=child.id,
        )
        await self.db.commit()
        owner_id = self._actor_user_id or str(getattr(self.project, "owner_id", "") or "")
        service = ExecutionService(self.db)
        completed = await service.execute_run(child.id, expected_owner_id=owner_id or None)
        output = completed.output_payload_json or {}
        return {
            "child_run_id": child.id,
            "status": completed.status,
            "output": output.get("final_output") or output.get("summary") or "",
            "structured_output": output.get("structured_output_json"),
        }


def sanitize_tool_result(result: dict[str, Any], *, max_chars: int = 4000) -> dict[str, Any]:
    serialized = json.dumps(result, default=str)
    if len(serialized) <= max_chars:
        return result
    return {"truncated": True, "preview": serialized[:max_chars]}
