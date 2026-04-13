from __future__ import annotations

import asyncio
import json
import re
import subprocess
import time
from pathlib import Path
from typing import Any

import httpx
import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
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
from backend.modules.orchestration.security import decrypt_secret

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
        run: TaskRun,
    ) -> None:
        self.db = db
        self.repo = repo
        self.project = project
        self.task = task
        self.run = run

    async def execute(self, call: dict[str, Any]) -> dict[str, Any]:
        tool_name = str(call.get("tool") or "").strip()
        arguments = call.get("arguments") or {}
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
        issue_link: GithubIssueLink | None = None
        issue_link_id = arguments.get("issue_link_id") or (self.task.github_issue_link_id if self.task else None)
        if issue_link_id:
            issue_link = await self.db.get(GithubIssueLink, issue_link_id)
        repository: GithubRepository | None = None
        if issue_link is not None:
            repository = await self.db.get(GithubRepository, issue_link.repository_id)
            issue_number = issue_link.issue_number
        else:
            issue_number = int(arguments.get("issue_number", 0))
            repository_id = arguments.get("repository_id")
            if repository_id:
                repository = await self.db.get(GithubRepository, repository_id)
            elif arguments.get("repository_full_name"):
                rows = await self.db.execute(
                    select(GithubRepository).where(
                        GithubRepository.full_name == arguments["repository_full_name"]
                    )
                )
                repository = rows.scalar_one_or_none()
        if repository is None or issue_number <= 0:
            raise ToolExecutionError("GitHub tool call requires a repository and issue context")
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None:
            raise ToolExecutionError("GitHub connection not found for repository")
        return connection, repository, issue_link, issue_number

    def _github_connection_mode(self, connection: GithubConnection) -> str:
        return str((connection.metadata_json or {}).get("connection_mode") or "token")

    def _github_app_jwt(self) -> str:
        if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
            raise ToolExecutionError("GitHub App credentials are not configured")
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": settings.GITHUB_APP_ID},
            settings.GITHUB_APP_PRIVATE_KEY,
            algorithm="RS256",
        )

    async def _github_auth_headers(self, connection: GithubConnection) -> dict[str, str]:
        if self._github_connection_mode(connection) == "github_app":
            installation_id = int((connection.metadata_json or {}).get("installation_id") or 0)
            if installation_id <= 0:
                raise ToolExecutionError("GitHub App connection is missing installation_id")
            async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
                response = await client.post(
                    f"/app/installations/{installation_id}/access_tokens",
                    headers={
                        "Authorization": f"Bearer {self._github_app_jwt()}",
                        "Accept": "application/vnd.github+json",
                    },
                )
            if response.status_code >= 400:
                raise ToolExecutionError("Failed to mint GitHub installation token")
            token = str(response.json()["token"])
        else:
            token = decrypt_secret(connection.encrypted_token)
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _github_comment(self, arguments: dict[str, Any]) -> dict[str, Any]:
        body = str(arguments.get("body") or "").strip()
        if not body:
            raise ToolExecutionError("GitHub comment body is required")
        close_issue = bool(arguments.get("close_issue", False))
        connection, repository, issue_link, issue_number = await self._resolve_issue_context(arguments)
        headers = await self._github_auth_headers(connection)
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
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
                    raise ToolExecutionError(f"GitHub close issue failed: {close_response.text[:300]}")
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
        connection, repository, issue_link, issue_number = await self._resolve_issue_context(arguments)
        headers = await self._github_auth_headers(connection)
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
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
        repository: GithubRepository | None = None
        if repository_id:
            repository = await self.db.get(GithubRepository, repository_id)
        elif repository_full_name:
            rows = await self.db.execute(
                select(GithubRepository).where(GithubRepository.full_name == repository_full_name)
            )
            repository = rows.scalar_one_or_none()
        if repository is None:
            raise ToolExecutionError("GitHub repository was not found")
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None:
            raise ToolExecutionError("GitHub connection not found for repository")
        headers = await self._github_auth_headers(connection)
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
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
        url = str(arguments.get("url") or "").strip()
        if not re.match(r"^https?://", url):
            raise ToolExecutionError("web_fetch requires an absolute http(s) URL")
        async with httpx.AsyncClient(timeout=float(arguments.get("timeout_seconds", 20))) as client:
            response = await client.get(url)
        if response.status_code >= 400:
            raise ToolExecutionError(f"Fetch failed with status {response.status_code}")
        text = response.text[: int(arguments.get("max_chars", 5000))]
        return {
            "url": url,
            "status_code": response.status_code,
            "content_type": response.headers.get("content-type"),
            "body": text,
        }

    async def _web_search(self, arguments: dict[str, Any]) -> dict[str, Any]:
        query = str(arguments.get("query") or "").strip()
        if not query:
            raise ToolExecutionError("web_search requires a query")
        limit = max(1, min(int(arguments.get("limit", 5)), 10))
        async with httpx.AsyncClient(timeout=20.0) as client:
            response = await client.get(
                "https://duckduckgo.com/html/",
                params={"q": query},
                headers={"User-Agent": "troop-orchestrator/1.0"},
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

        # Try Docker sandbox first
        docker_available = await asyncio.to_thread(self._docker_available)
        if docker_available:
            return await self._code_execute_docker(shell_cmd, cwd, timeout)

        # Fallback: direct subprocess (host execution)
        if use_shell_wrap:
            args = ["bash", "-lc", shell_cmd]
        else:
            args = shell_cmd.split()

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                args,
                cwd=str(cwd),
                capture_output=True,
                text=True,
                timeout=timeout,
                check=False,
            )

        result = await asyncio.to_thread(_run)
        return {
            "command": args,
            "cwd": str(cwd),
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "sandbox": "host",
        }

    @staticmethod
    def _docker_available() -> bool:
        try:
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True,
                timeout=3,
                check=False,
            )
            return result.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    async def _code_execute_docker(
        self, shell_cmd: str, cwd: Path, timeout: int
    ) -> dict[str, Any]:
        workspace_str = str(cwd)
        docker_args = [
            "docker", "run",
            "--rm",
            "--network", "none",
            "--memory", "256m",
            "--cpus", "0.5",
            "--read-only",
            "--tmpfs", "/tmp:rw,size=64m",
            "-v", f"{workspace_str}:/workspace:ro",
            "-w", "/workspace",
            "python:3.12-slim",
            "bash", "-c", shell_cmd,
        ]

        def _run() -> subprocess.CompletedProcess[str]:
            return subprocess.run(
                docker_args,
                capture_output=True,
                text=True,
                timeout=timeout + 10,  # extra buffer for container startup
                check=False,
            )

        result = await asyncio.to_thread(_run)
        return {
            "command": shell_cmd,
            "cwd": "/workspace",
            "returncode": result.returncode,
            "stdout": result.stdout[-4000:],
            "stderr": result.stderr[-4000:],
            "sandbox": "docker",
        }

    async def _fs_read(self, arguments: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(arguments.get("path") or "").strip()
        if not relative_path:
            raise ToolExecutionError("fs_read requires a project-scoped path")
        path = self._resolve_scoped_path(relative_path)
        if not path.exists():
            raise ToolExecutionError(f"File does not exist: {relative_path}")
        text = path.read_text(encoding="utf-8")
        max_chars = max(1, min(int(arguments.get("max_chars", 5000)), 50000))
        return {
            "path": relative_path,
            "absolute_path": str(path),
            "content": text[:max_chars],
        }

    async def _fs_write(self, arguments: dict[str, Any]) -> dict[str, Any]:
        relative_path = str(arguments.get("path") or "").strip()
        content = str(arguments.get("content") or "")
        if not relative_path:
            raise ToolExecutionError("fs_write requires a project-scoped path")
        path = self._resolve_scoped_path(relative_path)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
        return {
            "path": relative_path,
            "absolute_path": str(path),
            "bytes_written": len(content.encode("utf-8")),
        }

    async def _db_query(self, arguments: dict[str, Any]) -> dict[str, Any]:
        entity = str(arguments.get("entity") or "").strip()
        filters = arguments.get("filters") or {}
        limit = max(1, min(int(arguments.get("limit", 10)), 100))
        if entity == "tasks":
            stmt = select(OrchestratorTask).where(OrchestratorTask.project_id == self.project.id)
            for key, value in filters.items():
                if key in {"status", "priority", "assigned_agent_id", "reviewer_agent_id", "task_type"}:
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
            stmt = select(RunEvent).where(RunEvent.run_id == self.run.id).order_by(RunEvent.created_at.desc())
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
        rows = (
            await self.db.execute(
                select(ProjectDocumentChunk)
                .join(ProjectDocument, ProjectDocumentChunk.project_document_id == ProjectDocument.id)
                .where(
                    ProjectDocumentChunk.project_id == self.project.id,
                    ProjectDocument.deleted_at.is_(None),
                    ProjectDocumentChunk.deleted_at.is_(None),
                    ProjectDocumentChunk.metadata_json["source_kind"].as_string() == "repo_index",
                )
                .order_by(ProjectDocumentChunk.created_at.desc())
                .limit(limit * 10)
            )
        ).scalars().all()
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
        return {"query": query, "items": matches[:limit]}


def sanitize_tool_result(result: dict[str, Any], *, max_chars: int = 4000) -> dict[str, Any]:
    serialized = json.dumps(result, default=str)
    if len(serialized) <= max_chars:
        return result
    return {"truncated": True, "preview": serialized[:max_chars]}
