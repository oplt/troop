"""Project repository links, local repo workspace, and indexing."""

from __future__ import annotations

import asyncio
import io
import tarfile
from datetime import UTC, datetime
from types import SimpleNamespace
from typing import Any

from fastapi import HTTPException

from backend.core.logging import get_logger
from backend.modules.identity_access.models import User
from backend.modules.orchestration.local_repo import (
    LocalRepoError,
    build_context_pack_async,
    create_isolated_worktree_async,
    inspect_workspace_async,
    normalize_workspace,
    read_repo_file_async,
    run_safe_command_async,
)

logger = get_logger(__name__)


class ProjectWorkspaceMixin:
    async def add_project_repository(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        item = await self.repo.create_project_repository(project_id=project_id, **payload)
        await self.db.commit()
        await self.db.refresh(item)
        sync_repository = getattr(self, "_sync_knowledge_graph_for_project_repository", None)
        if callable(sync_repository):
            await sync_repository(project, item)
            await self.db.commit()
        return item


    async def list_project_repositories(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        return await self.repo.list_project_repositories(project_id)


    async def get_local_repo_workspace(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        return normalize_workspace(settings.get("local_repo"))


    async def validate_local_repo_workspace(
        self, user: User, payload: dict[str, Any]
    ) -> dict[str, Any]:
        _ = user
        workspace = normalize_workspace(payload)
        try:
            return await inspect_workspace_async(workspace)
        except LocalRepoError as exc:
            return {"valid": False, "blocked_reasons": [str(exc)], "workspace": workspace}


    async def update_local_repo_workspace(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        workspace = normalize_workspace(payload)
        try:
            status = await inspect_workspace_async(workspace)
        except LocalRepoError as exc:
            if workspace["enabled"]:
                raise HTTPException(status_code=422, detail=str(exc)) from exc
            status = {"valid": False, "blocked_reasons": [str(exc)], "workspace": workspace}
        settings = dict(project.settings_json or {})
        settings["local_repo"] = {**workspace, "last_validation": status}
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return status


    async def inspect_local_repo_workspace(self, user: User, project_id: str) -> dict[str, Any]:
        workspace = await self.get_local_repo_workspace(user, project_id)
        try:
            return await inspect_workspace_async(workspace)
        except LocalRepoError as exc:
            return {"valid": False, "blocked_reasons": [str(exc)], "workspace": workspace}


    async def create_local_repo_worktree(
        self,
        user: User,
        project_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        task = await self.repo.get_task(project.id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        workspace = normalize_workspace((project.settings_json or {}).get("local_repo"))
        try:
            worktree = await create_isolated_worktree_async(
                workspace, task_id=task.id, title=task.title
            )
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        metadata = dict(task.metadata_json or {})
        session = dict(metadata.get("local_repo_session") or {})
        session.update(
            {
                "status": "preparing_workspace",
                "worktree": worktree,
                "updated_at": datetime.now(UTC).isoformat(),
            }
        )
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        await self.db.commit()
        return worktree


    async def build_local_repo_context_pack(
        self,
        user: User,
        project_id: str,
        task_id: str,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        task = await self.repo.get_task(project.id, task_id)
        if task is None:
            raise HTTPException(status_code=404, detail="Task not found")
        issue_text = "\n\n".join(part for part in [task.title, task.description or ""] if part)
        try:
            context = await build_context_pack_async(
                (project.settings_json or {}).get("local_repo"),
                issue_text=issue_text,
                acceptance_criteria=task.acceptance_criteria,
            )
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        await self.repo.create_task_artifact(
            task_id=task.id,
            run_id=None,
            kind="local_repo_context_pack",
            title="Local repo context pack",
            content=None,
            metadata_json=context,
        )
        metadata = dict(task.metadata_json or {})
        session = dict(metadata.get("local_repo_session") or {})
        session.update({"status": "analyzing", "context_pack_created_at": context["created_at"]})
        metadata["local_repo_session"] = session
        task.metadata_json = metadata
        await self.db.commit()
        return context


    async def run_local_repo_command(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        try:
            result = await run_safe_command_async(
                (project.settings_json or {}).get("local_repo"),
                command=str(payload.get("command") or ""),
                cwd=payload.get("cwd"),
                timeout_seconds=int(payload.get("timeout_seconds") or 60),
            )
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        return {
            "command": result.command,
            "cwd": result.cwd,
            "exit_code": result.exit_code,
            "stdout": result.stdout,
            "stderr": result.stderr,
            "duration_ms": result.duration_ms,
            "timed_out": result.timed_out,
        }


    async def read_local_repo_file(
        self,
        user: User,
        project_id: str,
        path: str,
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        try:
            return await read_repo_file_async(
                (project.settings_json or {}).get("local_repo"), path
            )
        except LocalRepoError as exc:
            raise HTTPException(status_code=422, detail=str(exc)) from exc


    async def update_project_repository(
        self, user: User, project_id: str, repository_link_id: str, updates: dict[str, Any]
    ):
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if "default_branch" in updates:
            repository_link.default_branch = updates.get("default_branch")
        if "metadata" in updates and isinstance(updates.get("metadata"), dict):
            repository_link.metadata_json = {
                **(repository_link.metadata_json or {}),
                **(updates.get("metadata") or {}),
            }
        if "github_repository_id" in updates and updates.get("github_repository_id") is not None:
            repository_link.github_repository_id = updates["github_repository_id"]
        await self.db.commit()
        await self.db.refresh(repository_link)
        sync_repository = getattr(self, "_sync_knowledge_graph_for_project_repository", None)
        if callable(sync_repository):
            await sync_repository(project, repository_link)
            await self.db.commit()
        return repository_link


    async def project_repository_index_status(
        self, user: User, project_id: str
    ) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        repositories = await self.repo.list_project_repositories(project.id)
        jobs = await self.repo.list_memory_ingest_jobs_for_project(user.id, project.id, limit=240)
        documents = await self.repo.list_documents(project.id, None, limit=0)

        documents_by_repo: dict[str, list[Any]] = {}
        for document in documents:
            metadata = document.metadata_json or {}
            if metadata.get("source_kind") != "repo_index":
                continue
            repository_link_id = str(metadata.get("repository_link_id") or "")
            if not repository_link_id:
                continue
            documents_by_repo.setdefault(repository_link_id, []).append(document)

        jobs_by_repo: dict[str, list[Any]] = {}
        for job in jobs:
            if job.job_type != "repo_index":
                continue
            repository_link_id = str((job.payload_json or {}).get("repository_link_id") or "")
            if not repository_link_id:
                continue
            jobs_by_repo.setdefault(repository_link_id, []).append(job)

        rows: list[dict[str, Any]] = []
        for repository in repositories:
            repo_docs = documents_by_repo.get(repository.id, [])
            repo_jobs = jobs_by_repo.get(repository.id, [])
            latest_job = repo_jobs[0] if repo_jobs else None
            latest_success = next((job for job in repo_jobs if job.status == "completed"), None)
            indexed_files = len(repo_docs)
            chunk_count = sum(int(doc.chunk_count or 0) for doc in repo_docs)
            latest_indexed_at = None
            if repo_docs:
                latest_indexed_at = max(
                    (
                        doc.updated_at or doc.created_at
                        for doc in repo_docs
                        if (doc.updated_at or doc.created_at)
                    ),
                    default=None,
                )
            recent_files = [
                {
                    "document_id": doc.id,
                    "path": str((doc.metadata_json or {}).get("path") or doc.filename),
                    "branch": str(
                        (doc.metadata_json or {}).get("branch") or repository.default_branch or ""
                    ),
                    "chunk_count": int(doc.chunk_count or 0),
                    "status": doc.ingestion_status,
                }
                for doc in sorted(
                    repo_docs,
                    key=lambda item: item.updated_at or item.created_at,
                    reverse=True,
                )[:10]
            ]
            recent_errors = [
                {
                    "job_id": job.id,
                    "error_text": job.error_text,
                    "created_at": job.created_at,
                    "mode": str((job.payload_json or {}).get("mode") or "full"),
                    "path_prefixes": list((job.payload_json or {}).get("path_prefixes") or []),
                }
                for job in repo_jobs
                if job.status == "failed" and job.error_text
            ][:5]
            index_settings = dict((repository.metadata_json or {}).get("indexing") or {})
            rows.append(
                {
                    "repository_link_id": repository.id,
                    "github_repository_id": repository.github_repository_id,
                    "full_name": repository.full_name,
                    "default_branch": repository.default_branch,
                    "repository_url": repository.repository_url,
                    "index_settings": index_settings,
                    "indexed_files": indexed_files,
                    "chunk_count": chunk_count,
                    "searchable_documents": indexed_files,
                    "last_indexed_at": latest_indexed_at,
                    "latest_job": {
                        "id": latest_job.id,
                        "status": latest_job.status,
                        "error_text": latest_job.error_text,
                        "created_at": latest_job.created_at,
                        "started_at": latest_job.started_at,
                        "finished_at": latest_job.finished_at,
                        "mode": str((latest_job.payload_json or {}).get("mode") or "full"),
                        "path_prefixes": list(
                            (latest_job.payload_json or {}).get("path_prefixes") or []
                        ),
                    }
                    if latest_job
                    else None,
                    "last_successful_job_id": latest_success.id if latest_success else None,
                    "pending_jobs": sum(1 for job in repo_jobs if job.status == "pending"),
                    "running_jobs": sum(1 for job in repo_jobs if job.status == "running"),
                    "recent_files": recent_files,
                    "recent_errors": recent_errors,
                }
            )
        return rows


    async def index_project_repository(
        self,
        user: User,
        project_id: str,
        repository_link_id: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = payload or {}
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if not repository_link.github_repository_id:
            raise HTTPException(
                status_code=422, detail="Project repository is not linked to GitHub"
            )
        path_prefixes = [
            str(item).strip()
            for item in list(payload.get("path_prefixes") or [])
            if str(item).strip()
        ][:20]
        mode = "incremental" if str(payload.get("mode") or "full") == "incremental" else "full"
        auto_enabled = payload.get("auto_enabled")
        schedule_label = str(payload.get("schedule_label") or "").strip() or None
        if auto_enabled is not None or schedule_label is not None:
            metadata = dict(repository_link.metadata_json or {})
            metadata["indexing"] = {
                **dict(metadata.get("indexing") or {}),
                **({"auto_enabled": bool(auto_enabled)} if auto_enabled is not None else {}),
                **({"schedule_label": schedule_label} if schedule_label is not None else {}),
                "last_requested_mode": mode,
                "last_requested_at": datetime.now(UTC).isoformat(),
                "path_prefixes": path_prefixes,
            }
            repository_link.metadata_json = metadata
        job = await self.repo.create_memory_ingest_job(
            owner_id=user.id,
            project_id=project.id,
            job_type="repo_index",
            payload_json={
                "project_id": project.id,
                "repository_link_id": repository_link.id,
                "requested_by_user_id": user.id,
                "mode": mode,
                "path_prefixes": path_prefixes,
            },
            status="pending",
        )
        await self.db.commit()
        try:
            from backend.workers.orchestration import queue_memory_ingest_jobs

            queue_memory_ingest_jobs()
        except Exception as exc:
            logger.warning("queue memory ingest jobs failed for repo index: %s", exc)
        return {
            "queued": True,
            "job_id": job.id,
            "project_id": project.id,
            "repository_link_id": repository_link.id,
            "status": job.status,
            "mode": mode,
            "path_prefixes": path_prefixes,
        }


    async def _run_repository_index_job(
        self,
        *,
        owner_id: str,
        project_id: str,
        repository_link_id: str,
        requested_by_user_id: str | None = None,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        payload = dict(payload or {})
        user = SimpleNamespace(id=owner_id)
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if not repository_link.github_repository_id:
            raise HTTPException(
                status_code=422, detail="Project repository is not linked to GitHub"
            )
        github_repository = await self.repo.get_github_repository(
            user.id, repository_link.github_repository_id
        )
        if github_repository is None:
            raise HTTPException(status_code=404, detail="GitHub repository not found")
        connection = await self.repo.get_github_connection(user.id, github_repository.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="GitHub connection not found")

        github_request = getattr(self, "_github_request", None)
        if not callable(github_request):
            raise RuntimeError("_run_repository_index_job requires a host _github_request helper")
        index_document = getattr(self, "_index_project_document", None)
        if not callable(index_document):
            raise RuntimeError(
                "_run_repository_index_job requires a host _index_project_document helper"
            )

        branch = repository_link.default_branch or github_repository.default_branch or "main"
        path_prefixes = [
            str(item).strip()
            for item in list(payload.get("path_prefixes") or [])
            if str(item).strip()
        ][:20]
        requested_mode = str(payload.get("mode") or "full")
        archive_response = await github_request(
            connection,
            "GET",
            f"/repos/{github_repository.full_name}/tarball/{branch}",
        )
        if archive_response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch repository snapshot")
        allowed_suffixes = {
            ".py",
            ".ts",
            ".tsx",
            ".js",
            ".jsx",
            ".md",
            ".txt",
            ".json",
            ".yaml",
            ".yml",
            ".toml",
            ".sql",
        }
        indexed = 0
        chunk_total = 0
        max_files = 200

        def _extract_repo_files() -> list[tuple[str, str, int]]:
            extracted_files: list[tuple[str, str, int]] = []
            with tarfile.open(fileobj=io.BytesIO(archive_response.content), mode="r:gz") as tf:
                for member in tf.getmembers():
                    if len(extracted_files) >= max_files:
                        break
                    if not member.isfile():
                        continue
                    raw_name = str(member.name or "")
                    _, _, path = raw_name.partition("/")
                    if not path or not any(path.endswith(suffix) for suffix in allowed_suffixes):
                        continue
                    if path_prefixes and not any(path.startswith(prefix) for prefix in path_prefixes):
                        continue
                    extracted = tf.extractfile(member)
                    if extracted is None:
                        continue
                    file_payload = extracted.read()
                    if not file_payload:
                        continue
                    try:
                        content = file_payload.decode("utf-8")
                    except UnicodeDecodeError:
                        continue
                    extracted_files.append((path, content, len(file_payload)))
            return extracted_files

        extracted_files = await asyncio.to_thread(_extract_repo_files)
        for path, content, size_bytes in extracted_files:
            document = await self.repo.create_document(
                project_id=project.id,
                task_id=None,
                uploaded_by_user_id=requested_by_user_id or user.id,
                filename=path,
                content_type="text/plain",
                source_text=content,
                object_key=None,
                size_bytes=size_bytes,
                summary_text=content[:500],
                ingestion_status="pending",
                chunk_count=0,
                ttl_days=None,
                expires_at=None,
                metadata_json={
                    "source_kind": "repo_index",
                    "repository_link_id": repository_link.id,
                    "repository_full_name": github_repository.full_name,
                    "branch": branch,
                    "path": path,
                    "index_mode": requested_mode,
                },
            )
            await index_document(document)
            indexed += 1
            chunk_total += document.chunk_count
        return {
            "repository_link_id": repository_link.id,
            "repository_full_name": github_repository.full_name,
            "branch": branch,
            "indexed_files": indexed,
            "chunk_count": chunk_total,
            "mode": requested_mode,
            "path_prefixes": path_prefixes,
        }

