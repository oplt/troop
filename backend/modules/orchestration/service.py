from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import io
import json
import logging
import uuid
from difflib import unified_diff
import math
import re
import tarfile
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Sequence

import httpx
import jwt
from fastapi import HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as orm_attributes

from backend.core.cache import redis_client
from backend.core.storage import StorageNotConfiguredError, object_storage
from backend.core.config import settings
from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.audit.repository import AuditRepository
from backend.modules.github.models import GithubConnection, GithubIssueLink, GithubRepository
from backend.modules.identity_access.models import User
from backend.modules.memory.models import (
    AgentMemoryEntry,
    ProceduralPlaybook,
    ProjectDocument,
    SemanticMemoryEntry,
    SemanticMemoryLink,
    normalize_embedding_for_vector,
)
from backend.modules.notifications.repository import NotificationsRepository
from backend.modules.orchestration.markdown import parse_agent_markdown
from backend.modules.orchestration.model_catalog import BUILTIN_MODEL_CAPABILITIES
from backend.modules.orchestration.models import (
    ApprovalRequest,
    Brainstorm,
    EvalRecord,
    ModelCapability,
    ProviderConfig,
    RunEvent,
    TaskRun,
)
from backend.modules.orchestration.providers import execute_prompt, list_provider_models, test_provider
from backend.modules.orchestration.context_packet import ContextPacket, log_context_packet_telemetry
from backend.modules.orchestration.execution_state import (
    EXECUTION_SNAPSHOT_SCHEMA_VERSION,
    EXECUTION_TRUTH_DESCRIPTION,
    SNAPSHOT_SOURCES_RUN,
    SNAPSHOT_SOURCES_TASK,
    checkpoint_excerpt,
    extract_execution_metadata_views,
)
from backend.modules.orchestration.execution_workflow import (
    WORKFLOW_STATE_KEY,
    current_step,
    ensure_workflow_state,
    get_workflow_artifact,
    increment_resume_count,
    mark_step,
    set_workflow_artifact,
    summarize_trace,
    workflow_state,
)
from backend.modules.orchestration.memory_coordination import (
    MEMORY_COORDINATION_KEY,
    extract_blackboard_sections,
)
from backend.modules.orchestration.memory_episodic import (
    build_episodic_archive_jsonl_gz,
    episodic_object_key,
)
from backend.modules.orchestration.memory_metrics import increment_memory_metric
from backend.modules.orchestration.memory_settings import merge_memory_settings
from backend.modules.orchestration.procedural_context import build_procedural_snippets
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.orchestration.working_memory import (
    EXECUTION_THREAD_ID_KEY,
    WORKING_MEMORY_KEY,
    format_working_memory_for_prompt,
    merge_working_memory_patch,
    patch_allowed_for_run_status,
    working_memory_from_checkpoint,
)
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret, mask_secret
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
    ProjectDecision,
    ProjectMilestone,
    TaskArtifact,
)
from backend.modules.team.models import AgentProfile, AgentTemplateCatalog, SkillPack, TeamTemplateCatalog


logger = logging.getLogger(__name__)


TASK_TRANSITIONS: dict[str, set[str]] = {
    "backlog": {"queued", "archived"},
    "queued": {"planned", "blocked", "failed", "archived"},
    "planned": {"in_progress", "blocked", "archived", "failed"},
    "in_progress": {"blocked", "needs_review", "completed", "failed", "planned"},
    "blocked": {"planned", "in_progress", "failed", "archived"},
    "needs_review": {"approved", "planned", "blocked", "failed"},
    "approved": {"completed", "planned", "archived"},
    "completed": {"synced_to_github", "planned", "archived"},
    "failed": {"planned", "queued", "archived"},
    "synced_to_github": {"archived", "planned"},
    "archived": set(),
}

SEMANTIC_ENTRY_TYPES = frozenset(
    {"policy", "standard", "adr", "glossary", "convention", "preference", "routing", "note"}
)


def _default_semantic_namespace(project_id: str, entry_type: str, title: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:80] or "entry"
    return f"project/{project_id}/semantic/{entry_type}/{slug}"


def _normalize_task_priority(value: str | None) -> str:
    if not value:
        return "normal"
    v = str(value).strip().lower()
    if v == "medium":
        return "normal"
    return v


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


def _estimate_embedding_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class BlockedExecution(RuntimeError):
    pass


class OrchestrationService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.audit_repo = AuditRepository(db)
        self.notifications_repo = NotificationsRepository(db)
        self.ai_providers = AiProviderRegistry()

    async def get_overview(self, user: User) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        return {
            "projects": await self.repo.list_projects(user.id),
            "agents": await self.repo.list_agents(user.id),
            "active_runs": (await self.repo.list_runs(user.id))[:10],
            "pending_approvals": (await self.repo.list_approvals(user.id, "pending"))[:10],
            "github_events": (await self.repo.list_sync_events(user.id))[:10],
        }

    async def validate_agent_markdown(
        self, user: User, content: str
    ) -> tuple[dict[str, Any] | None, list[str], list[str]]:
        await self._ensure_catalog_seeded()
        normalized, errors = parse_agent_markdown(content)
        if errors or normalized is None:
            return normalized, errors, []
        lint = await self.lint_agent_payload_detailed(user, normalized)
        return normalized, lint["errors"], lint["warnings"]

    async def list_agents(self, user: User, project_id: str | None = None) -> list[AgentProfile]:
        await self._ensure_catalog_seeded()
        return await self.repo.list_agents(user.id, project_id)

    async def create_agent(self, user: User, payload: dict[str, Any]) -> AgentProfile:
        await self._ensure_catalog_seeded()
        await self._ensure_unique_agent_slug(user.id, payload["slug"], None)
        payload = await self._validate_and_normalize_agent_payload(user, payload, existing_agent_id=None)
        payload["is_active"] = bool(payload.get("is_active", False))
        agent = await self.repo.create_agent(owner_id=user.id, **self._agent_payload_to_model(payload))
        await self._snapshot_agent(agent, user.id)
        await self.audit_repo.log(
            "orchestration.agent.created",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"slug": agent.slug},
        )
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def import_agent_markdown(
        self,
        user: User,
        *,
        content: str,
        project_id: str | None = None,
        existing_agent_id: str | None = None,
    ) -> AgentProfile:
        await self._ensure_catalog_seeded()
        normalized, errors = parse_agent_markdown(content)
        if errors or normalized is None:
            raise HTTPException(status_code=422, detail={"errors": errors})
        normalized["project_id"] = project_id
        normalized = await self._validate_and_normalize_agent_payload(
            user,
            normalized,
            existing_agent_id=existing_agent_id,
        )

        manager_slug = normalized["model_policy"].pop("manager_slug", None)
        parent_agent = None
        if manager_slug:
            parent_agent = await self.repo.get_agent_by_slug(user.id, manager_slug)
            if parent_agent:
                normalized["parent_agent_id"] = parent_agent.id

        if existing_agent_id:
            agent = await self.get_agent(user, existing_agent_id)
            await self._ensure_unique_agent_slug(user.id, normalized["slug"], agent.id)
            self._apply_agent_updates(agent, normalized)
            agent.version += 1
        else:
            await self._ensure_unique_agent_slug(user.id, normalized["slug"], None)
            normalized["is_active"] = False
            agent = await self.repo.create_agent(
                owner_id=user.id, **self._agent_payload_to_model(normalized)
            )

        await self._snapshot_agent(agent, user.id)
        await self.audit_repo.log(
            "orchestration.agent.imported_markdown",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"project_id": project_id},
        )
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def get_agent(self, user: User, agent_id: str) -> AgentProfile:
        await self._ensure_catalog_seeded()
        agent = await self.repo.get_agent(user.id, agent_id)
        if not agent:
            raise HTTPException(status_code=404, detail="Agent not found")
        return agent

    async def update_agent(self, user: User, agent_id: str, updates: dict[str, Any]) -> AgentProfile:
        await self._ensure_catalog_seeded()
        agent = await self.get_agent(user, agent_id)
        if "slug" in updates and updates["slug"] is not None:
            await self._ensure_unique_agent_slug(user.id, updates["slug"], agent.id)
        if "source_markdown" in updates and updates["source_markdown"]:
            normalized, errors = parse_agent_markdown(updates["source_markdown"])
            if errors or normalized is None:
                raise HTTPException(status_code=422, detail={"errors": errors})
            updates = {**normalized, **updates}
        updates = await self._validate_and_normalize_agent_payload(user, updates, existing_agent_id=agent.id)
        self._apply_agent_updates(agent, updates)
        agent.version += 1
        await self._snapshot_agent(agent, user.id)
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def duplicate_agent(self, user: User, agent_id: str) -> AgentProfile:
        await self._ensure_catalog_seeded()
        source = await self.get_agent(user, agent_id)
        duplicate_slug = await self._generate_duplicate_slug(user.id, source.slug)
        payload = {
            **self._agent_model_to_payload(source),
            "slug": duplicate_slug,
            "name": f"{source.name} Copy",
            "is_active": False,
            "version": 1,
        }
        copy = await self.repo.create_agent(owner_id=user.id, **payload)
        await self._snapshot_agent(copy, user.id)
        await self.db.commit()
        await self.db.refresh(copy)
        return copy

    async def set_agent_active_state(self, user: User, agent_id: str, is_active: bool) -> AgentProfile:
        agent = await self.get_agent(user, agent_id)
        if is_active:
            lint = await self.summarize_agent_lint(user, agent)
            if lint["errors"]:
                raise HTTPException(
                    status_code=422,
                    detail={
                        "errors": lint["errors"],
                        "warnings": lint["warnings"],
                        "message": "Agent must pass validation before activation.",
                    },
                )
        agent.is_active = is_active
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def list_agent_versions(self, user: User, agent_id: str):
        await self.get_agent(user, agent_id)
        return await self.repo.list_agent_versions(agent_id)

    async def list_projects(self, user: User):
        return await self.repo.list_projects(user.id)

    async def create_project(self, user: User, payload: dict[str, Any]):
        project = await self.repo.create_project(
            owner_id=user.id,
            name=payload["name"],
            slug=payload["slug"],
            description=payload.get("description"),
            status=payload.get("status", "active"),
            goals_markdown=payload.get("goals_markdown", ""),
            settings_json=self._normalize_project_settings(payload.get("settings", {})),
            memory_scope=payload.get("memory_scope", "project"),
            knowledge_summary=payload.get("knowledge_summary"),
        )
        await self.audit_repo.log(
            "orchestration.project.created",
            user_id=user.id,
            resource_type="orchestrator_project",
            resource_id=project.id,
        )
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def get_project(self, user: User, project_id: str):
        project = await self.repo.get_project(user.id, project_id)
        if not project:
            raise HTTPException(status_code=404, detail="Project not found")
        return project

    async def update_project(self, user: User, project_id: str, updates: dict[str, Any]):
        project = await self.get_project(user, project_id)
        for field, value in updates.items():
            if field == "settings":
                merged = self._merge_nested_project_settings(project.settings_json or {}, value or {})
                project.settings_json = self._normalize_project_settings(merged)
            else:
                setattr(project, field, value)
        await self.db.commit()
        await self.db.refresh(project)
        return project

    async def get_gate_config(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = self._project_execution_settings(project)
        return {
            "autonomy_level": settings.get("autonomy_level", "assisted"),
            "approval_gates": settings.get("approval_gates", [
                "post_to_github", "open_pr", "mark_complete",
                "change_task_ownership",
                "write_memory", "use_expensive_model", "run_tool",
            ]),
        }

    async def update_gate_config(self, user: User, project_id: str, autonomy_level: str | None, approval_gates: list[str] | None) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        if autonomy_level is not None:
            execution["autonomy_level"] = autonomy_level
        if approval_gates is not None:
            execution["approval_gates"] = approval_gates
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return await self.get_gate_config(user, project_id)

    async def add_project_agent(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        agent = await self.get_agent(user, payload["agent_id"])
        existing = await self.repo.get_project_membership(project.id, agent.id)
        if existing:
            raise HTTPException(status_code=409, detail="Agent already assigned to project")
        if payload.get("is_default_manager"):
            for membership in await self.repo.list_project_memberships(project.id):
                membership.is_default_manager = False
        membership = await self.repo.create_project_membership(project_id=project.id, **payload)
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def list_project_agents(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        return await self.repo.list_project_memberships(project_id)

    async def update_project_agent(
        self, user: User, project_id: str, membership_id: str, updates: dict[str, Any]
    ):
        project = await self.get_project(user, project_id)
        membership = await self.repo.get_project_membership_by_id(project.id, membership_id)
        if not membership:
            raise HTTPException(status_code=404, detail="Project agent membership not found")
        if updates.get("is_default_manager"):
            for item in await self.repo.list_project_memberships(project.id):
                item.is_default_manager = item.id == membership.id
        if "role" in updates and updates["role"] is not None:
            membership.role = updates["role"]
        if "is_default_manager" in updates and updates["is_default_manager"] is not None:
            membership.is_default_manager = updates["is_default_manager"]
        await self.db.commit()
        await self.db.refresh(membership)
        return membership

    async def add_project_repository(self, user: User, project_id: str, payload: dict[str, Any]):
        await self.get_project(user, project_id)
        item = await self.repo.create_project_repository(project_id=project_id, **payload)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_project_repositories(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        return await self.repo.list_project_repositories(project_id)

    async def list_project_memory_ingest_jobs(
        self, user: User, project_id: str, *, limit: int = 60
    ) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        rows = await self.repo.list_memory_ingest_jobs_for_project(user.id, project_id, limit=limit)
        return [
            {
                "id": row.id,
                "project_id": row.project_id,
                "job_type": row.job_type,
                "status": row.status,
                "error_text": row.error_text,
                "created_at": row.created_at,
                "started_at": row.started_at,
                "finished_at": row.finished_at,
                "payload": row.payload_json or {},
            }
            for row in rows
        ]

    async def index_project_repository(
        self, user: User, project_id: str, repository_link_id: str
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if not repository_link.github_repository_id:
            raise HTTPException(status_code=422, detail="Project repository is not linked to GitHub")
        job = await self.repo.create_memory_ingest_job(
            owner_id=user.id,
            project_id=project.id,
            job_type="repo_index",
            payload_json={
                "project_id": project.id,
                "repository_link_id": repository_link.id,
                "requested_by_user_id": user.id,
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
        }

    async def _run_repository_index_job(
        self,
        *,
        owner_id: str,
        project_id: str,
        repository_link_id: str,
        requested_by_user_id: str | None = None,
    ) -> dict[str, Any]:
        user = SimpleNamespace(id=owner_id)
        project = await self.get_project(user, project_id)
        repository_link = await self.repo.get_project_repository(project.id, repository_link_id)
        if repository_link is None:
            raise HTTPException(status_code=404, detail="Project repository link not found")
        if not repository_link.github_repository_id:
            raise HTTPException(status_code=422, detail="Project repository is not linked to GitHub")
        github_repository = await self.repo.get_github_repository(user.id, repository_link.github_repository_id)
        if github_repository is None:
            raise HTTPException(status_code=404, detail="GitHub repository not found")
        connection = await self.repo.get_github_connection(user.id, github_repository.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="GitHub connection not found")

        branch = repository_link.default_branch or github_repository.default_branch or "main"
        archive_response = await self._github_request(
            connection,
            "GET",
            f"/repos/{github_repository.full_name}/tarball/{branch}",
        )
        if archive_response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch repository snapshot")
        allowed_suffixes = {
            ".py", ".ts", ".tsx", ".js", ".jsx", ".md", ".txt", ".json", ".yaml", ".yml", ".toml", ".sql"
        }
        indexed = 0
        chunk_total = 0
        max_files = 200
        with tarfile.open(fileobj=io.BytesIO(archive_response.content), mode="r:gz") as tf:
            for member in tf.getmembers():
                if indexed >= max_files:
                    break
                if not member.isfile():
                    continue
                raw_name = str(member.name or "")
                _, _, path = raw_name.partition("/")
                if not path or not any(path.endswith(suffix) for suffix in allowed_suffixes):
                    continue
                extracted = tf.extractfile(member)
                if extracted is None:
                    continue
                payload = extracted.read()
                if not payload:
                    continue
                try:
                    content = payload.decode("utf-8")
                except UnicodeDecodeError:
                    continue
                document = await self.repo.create_document(
                    project_id=project.id,
                    task_id=None,
                    uploaded_by_user_id=requested_by_user_id or user.id,
                    filename=path,
                    content_type="text/plain",
                    source_text=content,
                    object_key=None,
                    size_bytes=len(payload),
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
                    },
                )
                await self._index_project_document(document)
                indexed += 1
                chunk_total += document.chunk_count
        return {
            "repository_link_id": repository_link.id,
            "repository_full_name": github_repository.full_name,
            "branch": branch,
            "indexed_files": indexed,
            "chunk_count": chunk_total,
        }

    async def list_tasks(self, user: User, project_id: str):
        await self.get_project(user, project_id)
        return await self.repo.list_tasks(project_id)

    async def get_task(self, user: User, project_id: str, task_id: str):
        await self.get_project(user, project_id)
        task = await self.repo.get_task(project_id, task_id)
        if not task:
            raise HTTPException(status_code=404, detail="Task not found")
        return task

    async def create_task(self, user: User, project_id: str, payload: dict[str, Any]):
        project = await self.get_project(user, project_id)
        if payload.get("assigned_agent_id"):
            await self.get_agent(user, payload["assigned_agent_id"])
        if payload.get("reviewer_agent_id"):
            await self.get_agent(user, payload["reviewer_agent_id"])
        position = await self.repo.get_next_task_position(project.id)
        task = await self.repo.create_task(
            project_id=project.id,
            created_by_user_id=user.id,
            assigned_agent_id=payload.get("assigned_agent_id"),
            reviewer_agent_id=payload.get("reviewer_agent_id"),
            title=payload["title"],
            description=payload.get("description"),
            source=payload.get("source", "manual"),
            task_type=payload.get("task_type", "general"),
            priority=_normalize_task_priority(payload.get("priority")),
            status=payload.get("status", "backlog"),
            acceptance_criteria=payload.get("acceptance_criteria"),
            due_date=payload.get("due_date"),
            response_sla_hours=payload.get("response_sla_hours"),
            labels_json=payload.get("labels", []),
            result_summary=payload.get("result_summary"),
            result_payload_json=payload.get("result_payload", {}),
            metadata_json=payload.get("metadata", {}),
            position=position,
        )
        dependency_ids = list(payload.get("dependency_ids", []) or [])
        await self._validate_task_dependencies(project.id, task.id, dependency_ids)
        await self.repo.replace_task_dependencies(task.id, dependency_ids)
        await self.db.commit()
        await self.db.refresh(task)
        return task

    async def update_task(self, user: User, project_id: str, task_id: str, updates: dict[str, Any]):
        task = await self.get_task(user, project_id, task_id)
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if "assigned_agent_id" in updates and updates.get("assigned_agent_id") != task.assigned_agent_id:
            if self.action_requires_approval(project, "change_task_ownership"):
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=None,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=user.id,
                    approval_type="task_assignment_change",
                    status="pending",
                    payload_json={
                        "task_id": task.id,
                        "from_assigned_agent_id": task.assigned_agent_id,
                        "to_assigned_agent_id": updates.get("assigned_agent_id"),
                    },
                )
                await self.db.commit()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Changing task ownership requires approval.",
                        "approval_id": approval.id,
                    },
                )
        if "status" in updates and updates.get("status") in {"completed", "approved"}:
            if self.action_requires_approval(project, "mark_complete"):
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=None,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=user.id,
                    approval_type="task_mark_complete",
                    status="pending",
                    payload_json={
                        "task_id": task.id,
                        "from_status": task.status,
                        "to_status": updates.get("status"),
                    },
                )
                await self.db.commit()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Marking tasks complete requires approval.",
                        "approval_id": approval.id,
                    },
                )
        prev_snapshot = {
            "status": task.status,
            "assigned_agent_id": getattr(task, "assigned_agent_id", None),
            "labels": list(getattr(task, "labels_json", None) or []),
            "metadata": dict(getattr(task, "metadata_json", None) or {}),
        }
        prev_status = task.status
        if "assigned_agent_id" in updates and updates["assigned_agent_id"]:
            await self.get_agent(user, updates["assigned_agent_id"])
        if "reviewer_agent_id" in updates and updates["reviewer_agent_id"]:
            await self.get_agent(user, updates["reviewer_agent_id"])
        for field, value in updates.items():
            if field == "labels":
                task.labels_json = value
            elif field == "result_payload":
                task.result_payload_json = value
            elif field == "metadata":
                task.metadata_json = value
            elif field == "dependency_ids":
                dependency_ids = list(value or [])
                await self._validate_task_dependencies(project_id, task.id, dependency_ids)
                await self.repo.replace_task_dependencies(task.id, dependency_ids)
            elif field == "status":
                if value in {"completed", "approved"}:
                    acceptance = await self._check_task_acceptance_payload(task)
                    if not acceptance["passed"]:
                        raise HTTPException(
                            status_code=409,
                            detail={
                                "message": "Acceptance checks must pass before the task can be marked done.",
                                "checks": acceptance["checks"],
                            },
                        )
                await self._transition_task_status(task, value, reason="manual update")
            elif field == "priority":
                setattr(task, field, _normalize_task_priority(str(value) if value is not None else None))
            else:
                setattr(task, field, value)
        await self.db.commit()
        await self.db.refresh(task)
        await self._queue_task_github_sync_from_internal_changes(user, task, prev_snapshot)
        if prev_status != task.status and task.status in {"completed", "archived", "synced_to_github"}:
            await self._maybe_promote_task_close_working_memory(user, project, task)
        return task

    async def _validate_task_dependencies(
        self,
        project_id: str,
        task_id: str,
        dependency_ids: Sequence[str],
    ) -> None:
        normalized = [str(item) for item in dependency_ids if str(item).strip()]
        if len(set(normalized)) != len(normalized):
            raise HTTPException(status_code=409, detail="Duplicate task dependencies are not allowed.")
        if task_id in normalized:
            raise HTTPException(status_code=409, detail="A task cannot depend on itself.")

        tasks = await self.repo.list_tasks(project_id)
        task_ids = {item.id for item in tasks}
        missing = [dep_id for dep_id in normalized if dep_id not in task_ids]
        if missing:
            raise HTTPException(
                status_code=404,
                detail=f"Dependency tasks not found in this project: {', '.join(missing[:5])}",
            )

        adjacency: dict[str, list[str]] = {
            item.id: [str(dep_id) for dep_id in (item.dependency_ids or []) if str(dep_id).strip()]
            for item in tasks
        }
        adjacency[task_id] = normalized
        for dep_id in normalized:
            if self._task_dependency_path_exists(adjacency, dep_id, task_id):
                raise HTTPException(
                    status_code=409,
                    detail="Dependency update would create a cycle in the task DAG.",
                )

    def _task_dependency_path_exists(
        self,
        adjacency: dict[str, Sequence[str]],
        start_id: str,
        target_id: str,
    ) -> bool:
        stack = [start_id]
        seen: set[str] = set()
        while stack:
            current = stack.pop()
            if current == target_id:
                return True
            if current in seen:
                continue
            seen.add(current)
            stack.extend(str(item) for item in adjacency.get(current, []))
        return False

    async def delete_task(self, user: User, project_id: str, task_id: str):
        task = await self.get_task(user, project_id, task_id)
        await self.db.delete(task)
        await self.db.commit()

    def _task_effective_sla_deadline(self, task: OrchestratorTask) -> datetime | None:
        deadlines: list[datetime] = []
        if task.due_date:
            deadlines.append(task.due_date)
        if task.response_sla_hours and task.created_at:
            deadlines.append(task.created_at + timedelta(hours=int(task.response_sla_hours)))
        if not deadlines:
            return None
        return min(deadlines)

    async def _task_dependencies_met_for_run(self, task_id: str) -> bool:
        for dep in await self.repo.list_task_dependencies_for_task(task_id):
            dep_task = await self.repo.get_task_by_id(dep.depends_on_task_id)
            if dep_task and dep_task.status not in {"completed", "approved"}:
                return False
        return True

    async def list_dag_ready_tasks(self, user: User, project_id: str) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        tasks = await self.repo.list_tasks(project_id)
        deps_all = await self.repo.list_task_dependencies(project_id)
        dep_count: dict[str, int] = {}
        for dep in deps_all:
            dep_count[dep.task_id] = dep_count.get(dep.task_id, 0) + 1
        ready: list[dict[str, Any]] = []
        ready_statuses = {"backlog", "planned"}
        for t in tasks:
            if t.status not in ready_statuses:
                continue
            if await self.repo.task_has_active_run(project_id, t.id):
                continue
            if not await self._task_dependencies_met_for_run(t.id):
                continue
            ready.append(
                {
                    "id": t.id,
                    "title": t.title,
                    "status": t.status,
                    "dependency_count": dep_count.get(t.id, 0),
                }
            )
        return ready

    async def start_parallel_dag_ready_runs(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        run_mode = str(payload.get("run_mode") or "single_agent")
        limit = min(max(int(payload.get("limit") or 8), 1), 24)
        filter_ids = payload.get("task_ids")
        base_input = dict(payload.get("input_payload") or {})
        ready = await self.list_dag_ready_tasks(user, project_id)
        if filter_ids:
            fid = {str(x) for x in filter_ids}
            ready = [r for r in ready if r["id"] in fid]
        started: list[str] = []
        skipped: list[str] = []
        messages: list[str] = []
        for row in ready[:limit]:
            try:
                run = await self.start_task_run(
                    user,
                    project_id,
                    row["id"],
                    {"run_mode": run_mode, "input_payload": {**base_input, "dag_parallel_wave": True}},
                )
                started.append(run.id)
            except HTTPException as exc:
                skipped.append(row["id"])
                detail = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
                messages.append(f"{row['title']}: {detail}")
        return {"started_run_ids": started, "skipped_task_ids": skipped, "messages": messages}

    async def merge_resolution_preview(self, user: User, project_id: str, parent_task_id: str) -> dict[str, Any]:
        parent = await self.get_task(user, project_id, parent_task_id)
        children = await self.repo.list_subtasks(parent_task_id)
        branches: list[dict[str, Any]] = []
        for c in children:
            branches.append(
                {
                    "id": c.id,
                    "title": c.title,
                    "status": c.status,
                    "assigned_agent_id": c.assigned_agent_id,
                    "result_summary": c.result_summary,
                }
            )
        completed = [c for c in children if c.status in {"completed", "approved"}]
        agents = {c.assigned_agent_id for c in completed if c.assigned_agent_id}
        return {
            "parent": {"id": parent.id, "title": parent.title, "task_type": parent.task_type},
            "branches": branches,
            "completed_branch_count": len(completed),
            "distinct_agents_on_completed": len(agents),
            "needs_merge_agent": len(agents) > 1 and len(completed) >= 2,
        }

    async def start_merge_resolution_run(
        self,
        user: User,
        project_id: str,
        parent_task_id: str,
        payload: dict[str, Any],
    ) -> TaskRun:
        children = await self.repo.list_subtasks(parent_task_id)
        completed = [c for c in children if c.status in {"completed", "approved"}]
        if len(completed) < 2:
            raise HTTPException(
                status_code=400,
                detail="Merge resolution requires at least two completed subtasks under this parent.",
            )
        sources: list[dict[str, Any]] = []
        for c in completed:
            sources.append(
                {
                    "task_id": c.id,
                    "title": c.title,
                    "assigned_agent_id": c.assigned_agent_id,
                    "result_summary": c.result_summary,
                    "result_payload": c.result_payload_json,
                }
            )
        merge_ctx = {
            "parent_task_id": parent_task_id,
            "sources": sources,
            "notes": (payload.get("notes") or "")[:8000],
        }
        inp = dict(payload.get("input_payload") or {})
        inp["orchestration_merge_resolve"] = merge_ctx
        return await self.start_task_run(
            user,
            project_id,
            parent_task_id,
            {
                "run_mode": str(payload.get("run_mode") or "single_agent"),
                "input_payload": inp,
                "model_name": payload.get("model_name"),
            },
        )

    async def run_global_sla_escalation_scan(self) -> dict[str, Any]:
        projects = await self.repo.list_all_orchestrator_projects()
        checked = 0
        escalated = 0
        warned = 0
        now = datetime.now(UTC)
        for project in projects:
            exe = self._project_execution_settings(project)
            sla = exe.get("sla") or {}
            if not sla.get("enabled", True):
                continue
            after_h = float(sla.get("escalate_hours_after_due", 0) or 0)
            warn_h = float(sla.get("warn_hours_before_due", 24) or 24)
            tasks = await self.repo.list_tasks(project.id)
            for task in tasks:
                if task.status in {"completed", "approved", "archived", "synced_to_github"}:
                    continue
                deadline = self._task_effective_sla_deadline(task)
                if deadline is None:
                    continue
                checked += 1
                meta = dict(task.metadata_json or {})
                warn_at = deadline - timedelta(hours=warn_h)
                if now >= warn_at and now < deadline and not meta.get("sla_warn_sent"):
                    meta["sla_warn_sent"] = True
                    meta["sla_warn_at"] = now.isoformat()
                    task.metadata_json = meta
                    orm_attributes.flag_modified(task, "metadata_json")
                    warned += 1
                    meta = dict(task.metadata_json or {})
                breach_at = deadline + timedelta(hours=after_h)
                if now <= breach_at:
                    continue
                if meta.get("sla_escalated_at"):
                    continue
                if await self.repo.count_pending_approvals_for_task(project.id, task.id, "sla_escalation") > 0:
                    continue
                latest_run = await self.repo.get_latest_run_for_task(project.id, task.id)
                await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=latest_run.id if latest_run else None,
                    requested_by_user_id=project.owner_id,
                    approval_type="sla_escalation",
                    status="pending",
                    payload_json={
                        "deadline": deadline.isoformat(),
                        "breach_at": breach_at.isoformat(),
                        "escalate_hours_after_due": after_h,
                    },
                )
                meta["sla_escalated_at"] = now.isoformat()
                task.metadata_json = meta
                orm_attributes.flag_modified(task, "metadata_json")
                escalated += 1
        await self.db.commit()
        return {
            "projects_scanned": len(projects),
            "tasks_considered": checked,
            "warnings_flagged": warned,
            "escalations_created": escalated,
        }

    def _update_task_execution_memory(self, task: OrchestratorTask, run: TaskRun) -> None:
        """Persist a compact execution-memory snapshot and a diff vs the previous completed run."""
        meta = dict(task.metadata_json or {})
        prev_block = meta.get("execution_memory") or {}
        latest = str(
            run.output_payload_json.get("summary")
            or run.output_payload_json.get("final_output")
            or task.result_summary
            or ""
        )
        prev_excerpt = str(prev_block.get("latest_summary_excerpt") or "")[:4000]
        new_excerpt = latest[:4000]
        diff_text = ""
        if prev_excerpt and new_excerpt and prev_excerpt != new_excerpt:
            diff_lines = list(
                unified_diff(
                    prev_excerpt.splitlines(),
                    new_excerpt.splitlines(),
                    fromfile="previous_run",
                    tofile="this_run",
                    lineterm="",
                )
            )[:160]
            diff_text = "\n".join(diff_lines)[:12000]
        meta["execution_memory"] = {
            "last_run_id": run.id,
            "last_run_mode": run.run_mode,
            "last_completed_at": datetime.now(UTC).isoformat(),
            "previous_summary_excerpt": prev_excerpt[:2000],
            "latest_summary_excerpt": new_excerpt[:2000],
            "since_last_run_unified_diff": diff_text,
        }
        task.metadata_json = meta
        orm_attributes.flag_modified(task, "metadata_json")

    def _append_structured_reopen_record(
        self,
        task: OrchestratorTask,
        review_payload: dict[str, Any],
        *,
        run: TaskRun | None,
    ) -> None:
        meta = dict(task.metadata_json or {})
        hist = list(meta.get("reopen_history") or [])
        reasons = review_payload.get("reasons")
        if isinstance(reasons, str):
            reasons = [reasons]
        elif isinstance(reasons, list):
            reasons = [str(x) for x in reasons]
        else:
            reasons = [str(review_payload.get("summary") or "rework requested")]
        checklist = review_payload.get("checklist")
        if not isinstance(checklist, list):
            checklist = []
        checklist = [str(x) for x in checklist]
        rec: dict[str, Any] = {
            "at": datetime.now(UTC).isoformat(),
            "run_id": run.id if run else None,
            "decision": str(review_payload.get("decision") or "rework"),
            "summary": str(review_payload.get("summary") or "")[:4000],
            "reasons": [str(x)[:2000] for x in reasons[:50]],
            "checklist": [str(x)[:2000] for x in checklist[:50]],
        }
        hist.append(rec)
        meta["reopen_history"] = hist[-40:]
        meta["latest_reopen"] = rec
        task.metadata_json = meta
        orm_attributes.flag_modified(task, "metadata_json")

    async def list_task_comments(self, user: User, project_id: str, task_id: str):
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_task_comments(task_id)

    async def add_task_comment(self, user: User, project_id: str, task_id: str, body: str):
        await self.get_task(user, project_id, task_id)
        comment = await self.repo.create_task_comment(task_id=task_id, author_user_id=user.id, body=body)
        await self.db.commit()
        await self.db.refresh(comment)
        return comment

    async def list_task_timeline(self, user: User, project_id: str, task_id: str) -> list[dict[str, Any]]:
        await self.get_task(user, project_id, task_id)
        comments = await self.repo.list_task_comments(task_id)
        sync_events = await self.repo.list_sync_events_for_task(task_id)
        merged: list[dict[str, Any]] = []
        for c in comments:
            merged.append(
                {
                    "kind": "comment",
                    "id": c.id,
                    "created_at": c.created_at,
                    "title": "Task comment",
                    "body": c.body,
                    "detail": None,
                    "payload": {"author_user_id": c.author_user_id, "author_agent_id": c.author_agent_id},
                }
            )
        for e in sync_events:
            merged.append(
                {
                    "kind": "github_sync",
                    "id": e.id,
                    "created_at": e.created_at,
                    "title": e.action,
                    "body": None,
                    "detail": e.detail,
                    "payload": e.payload_json or {},
                }
            )
        merged.sort(key=lambda row: row["created_at"])
        return merged

    async def _queue_task_github_sync_from_internal_changes(
        self,
        user: User,
        task: OrchestratorTask,
        prev_snapshot: dict[str, Any],
    ) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        project = await self.db.get(OrchestratorProject, task.project_id)
        if repository is None or project is None:
            return
        github = self._project_github_settings(project)
        issue_update: dict[str, Any] = {}
        if github.get("sync_state_to_github", True):
            next_state = self._task_state_to_github_issue_state(task)
            prev_state = "closed" if prev_snapshot.get("status") in {"approved", "completed", "synced_to_github", "archived"} else "open"
            if next_state != prev_state:
                issue_update["state"] = next_state
        if github.get("sync_labels_to_github", True):
            next_labels = [str(item) for item in (task.labels_json or [])]
            prev_labels = [str(item) for item in (prev_snapshot.get("labels") or [])]
            if next_labels != prev_labels:
                issue_update["labels"] = next_labels
        if github.get("sync_assignees_to_github", True):
            next_assignee = await self._task_assignee_login_for_github(task, project)
            prev_assignee = None
            prev_assignee_id = prev_snapshot.get("assigned_agent_id")
            if prev_assignee_id:
                shadow = SimpleNamespace(
                    assigned_agent_id=prev_assignee_id,
                    github_issue_link_id=task.github_issue_link_id,
                    project_id=task.project_id,
                )
                prev_assignee = await self._task_assignee_login_for_github(shadow, project)
            if next_assignee != prev_assignee:
                issue_update["assignees"] = [next_assignee] if next_assignee else []
        if github.get("sync_milestone_to_github", True):
            next_milestone = (task.metadata_json or {}).get("github_milestone_number")
            prev_milestone = (prev_snapshot.get("metadata") or {}).get("github_milestone_number")
            if next_milestone != prev_milestone:
                issue_update["milestone"] = next_milestone
        if not issue_update:
            return
        await self._create_github_write_approval(
            user_id=user.id,
            project_id=task.project_id,
            task_id=task.id,
            run_id=None,
            issue_link_id=issue_link.id,
            approval_type="github_issue_sync",
            payload_json={
                "repository_id": repository.id,
                "issue_number": issue_link.issue_number,
                "issue_update": issue_update,
            },
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="sync_issue_fields_pending",
            status="pending",
            detail="Internal task changes queued for GitHub sync approval.",
            payload_json={"issue_update": issue_update, "task_id": task.id},
        )
        await self.db.commit()

    async def list_task_artifacts(self, user: User, project_id: str, task_id: str):
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_task_artifacts(task_id)

    async def create_task_artifact(self, user: User, project_id: str, task_id: str, kind: str, title: str, content: str | None, metadata: dict) -> TaskArtifact:
        await self.get_task(user, project_id, task_id)
        artifact = await self.repo.create_task_artifact(task_id=task_id, kind=kind, title=title, content=content, metadata_json=metadata)
        await self.db.commit()
        await self.db.refresh(artifact)
        return artifact

    async def list_subtasks(self, user: User, project_id: str, task_id: str) -> list[OrchestratorTask]:
        await self.get_task(user, project_id, task_id)
        return await self.repo.list_subtasks(task_id)

    async def decompose_task(self, user: User, project_id: str, task_id: str, max_subtasks: int = 5, context: str | None = None) -> list[OrchestratorTask]:
        parent = await self.get_task(user, project_id, task_id)
        existing = await self.repo.list_subtasks(task_id)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="Task already has subtasks. Update or archive the existing branch plan before decomposing again.",
            )
        blueprint = self._generate_subtask_blueprint(parent, max_subtasks=max_subtasks, context=context)
        subtasks = []
        for i, item in enumerate(blueprint):
            position = await self.repo.get_next_task_position(project_id)
            task = await self.repo.create_task(
                project_id=project_id,
                created_by_user_id=user.id,
                title=str(item["title"]),
                description=str(item["description"]),
                source="decompose",
                task_type=parent.task_type,
                priority=parent.priority,
                status="backlog",
                parent_task_id=task_id,
                position=position,
                labels_json=list(item.get("labels") or []),
                result_payload_json={},
                metadata_json={
                    "parallelizable": bool(item.get("parallelizable", False)),
                    "required_tools": list(item.get("required_tools") or []),
                    "blueprint_kind": item.get("kind"),
                },
                acceptance_criteria=item.get("acceptance_criteria"),
            )
            subtasks.append(task)
        for index, task in enumerate(subtasks):
            dependency_indexes = list(blueprint[index].get("dependency_indexes") or [])
            dependency_ids = [
                subtasks[dep_index].id
                for dep_index in dependency_indexes
                if 0 <= dep_index < len(subtasks)
            ]
            await self.repo.replace_task_dependencies(task.id, dependency_ids)
        await self.db.commit()
        for t in subtasks:
            await self.db.refresh(t)
        return subtasks

    async def check_task_acceptance(self, user: User, project_id: str, task_id: str) -> dict:
        task = await self.get_task(user, project_id, task_id)
        return await self._check_task_acceptance_payload(task)

    async def _check_task_acceptance_payload(self, task: OrchestratorTask) -> dict:
        checks: list[dict] = []

        output_text = self._task_output_text(task)
        has_output = bool(output_text.strip())
        checks.append({"name": "has_output", "passed": has_output, "detail": "Task has output summary or payload" if has_output else "No task output yet"})

        valid_statuses = {"completed", "needs_review"}
        in_valid_status = task.status in valid_statuses
        checks.append({"name": "valid_status", "passed": in_valid_status, "detail": f"Status is '{task.status}'" if in_valid_status else f"Status '{task.status}' is not a terminal state"})

        dep_rows = await self.repo.list_task_dependencies_for_task(task.id)
        if dep_rows:
            incomplete_count = 0
            for dep in dep_rows:
                dep_task = await self.repo.get_task_by_id(dep.depends_on_task_id)
                if dep_task and dep_task.status not in {"completed", "approved"}:
                    incomplete_count += 1
            deps_done = incomplete_count == 0
            checks.append({"name": "dependencies_complete", "passed": deps_done, "detail": "All dependencies completed" if deps_done else f"{incomplete_count} dependencies not yet complete"})
        else:
            checks.append({"name": "dependencies_complete", "passed": True, "detail": "No dependencies"})

        criteria_items = self._acceptance_criteria_items(task.acceptance_criteria or "")
        if criteria_items:
            item_checks = [self._acceptance_item_check(item, output_text) for item in criteria_items]
            missing = [item["item"] for item in item_checks if not item["passed"]]
            checks.append({
                "name": "acceptance_criteria",
                "passed": len(missing) == 0,
                "detail": "All acceptance criteria matched output." if not missing else f"Missing acceptance evidence for {len(missing)} item(s): {', '.join(missing[:3])}",
                "items": item_checks,
            })
        else:
            checks.append({
                "name": "acceptance_criteria",
                "passed": False,
                "detail": "No acceptance criteria defined.",
                "items": [],
            })

        if (getattr(task, "metadata_json", None) or {}).get("latest_reopen"):
            checks.append({
                "name": "reopen_items_resolved",
                "passed": False,
                "detail": "Latest review requested rework; rerun after addressing checklist items.",
            })
        else:
            checks.append({
                "name": "reopen_items_resolved",
                "passed": True,
                "detail": "No outstanding rework checklist.",
            })

        return {"task_id": task.id, "passed": all(c["passed"] for c in checks), "checks": checks}

    def _task_output_text(self, task: OrchestratorTask | Any) -> str:
        payload = getattr(task, "result_payload_json", None) or {}
        summary = getattr(task, "result_summary", None) or ""
        if not summary and isinstance(payload, dict):
            summary = str(payload.get("summary") or payload.get("final_output") or "")
        return "\n".join(
            chunk for chunk in [str(summary).strip(), json.dumps(payload, default=str) if payload else ""] if chunk
        )

    def _acceptance_criteria_items(self, text: str) -> list[str]:
        items: list[str] = []
        for raw_line in str(text or "").splitlines():
            line = raw_line.strip()
            if not line:
                continue
            normalized = re.sub(r"^[-*]\s+", "", line)
            normalized = re.sub(r"^\d+\.\s+", "", normalized)
            if normalized:
                items.append(normalized)
        if not items and str(text or "").strip():
            items.append(str(text).strip())
        return items

    def _acceptance_item_matches_output(self, item: str, output_text: str) -> bool:
        return self._acceptance_item_check(item, output_text)["passed"]

    def _acceptance_item_check(self, item: str, output_text: str) -> dict[str, Any]:
        required_tokens = [token for token in re.findall(r"[a-z0-9]+", item.lower()) if len(token) > 2]
        if not required_tokens:
            return {"item": item, "passed": True, "evidence_excerpt": ""}
        output_tokens = set(re.findall(r"[a-z0-9]+", output_text.lower()))
        overlap = sum(1 for token in required_tokens if token in output_tokens)
        passed = overlap >= max(1, math.ceil(len(required_tokens) * 0.5))
        return {
            "item": item,
            "passed": passed,
            "evidence_excerpt": self._acceptance_evidence_excerpt(item, output_text) if passed else "",
        }

    def _acceptance_evidence_excerpt(self, item: str, output_text: str) -> str:
        lowered = output_text.lower()
        for token in re.findall(r"[a-z0-9]+", item.lower()):
            if len(token) <= 2:
                continue
            index = lowered.find(token)
            if index >= 0:
                start = max(0, index - 40)
                end = min(len(output_text), index + 120)
                return output_text[start:end].strip()
        return output_text[:160].strip()

    def _generate_subtask_blueprint(
        self,
        parent: OrchestratorTask | Any,
        *,
        max_subtasks: int,
        context: str | None = None,
    ) -> list[dict[str, Any]]:
        criteria = self._acceptance_criteria_items(getattr(parent, "acceptance_criteria", "") or "")
        task_title = str(getattr(parent, "title", "Task")).strip()
        task_type = str(getattr(parent, "task_type", "general")).strip()
        shared_context = f"Context: {context}\n\n" if context else ""
        criteria_text = " ".join(criteria).lower()
        wants_docs = any(token in criteria_text for token in ["document", "docs", "adr", "summary"])
        wants_tests = any(token in criteria_text for token in ["test", "verify", "validation", "qa"])
        plan: list[dict[str, Any]] = [
            {
                "kind": "plan",
                "title": f"Plan scope for {task_title}",
                "description": f"{shared_context}Define the execution plan, assumptions, and dependency/risk map for this {task_type} task.",
                "dependency_indexes": [],
                "parallelizable": False,
                "required_tools": ["fs_read"],
                "labels": ["planning"],
                "acceptance_criteria": "Document execution plan, assumptions, and risks.",
            }
        ]
        if criteria:
            plan.append(
                {
                    "kind": "implement",
                    "title": f"Implement core work for {task_title}",
                    "description": f"{shared_context}Deliver the main implementation required by the task and cover these criteria:\n- " + "\n- ".join(criteria[:4]),
                    "dependency_indexes": [0],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["implementation"],
                    "acceptance_criteria": "\n".join(criteria[: min(3, len(criteria))]),
                }
            )
        else:
            plan.append(
                {
                    "kind": "implement",
                    "title": f"Implement {task_title}",
                    "description": f"{shared_context}Ship the main implementation for this task.",
                    "dependency_indexes": [0],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["implementation"],
                    "acceptance_criteria": "Primary implementation completed.",
                }
            )
        if wants_tests or max_subtasks >= 3:
            plan.append(
                {
                    "kind": "verify",
                    "title": f"Verify and test {task_title}",
                    "description": f"{shared_context}Run tests, validate acceptance criteria, and record any follow-up issues.",
                    "dependency_indexes": [1],
                    "parallelizable": False,
                    "required_tools": ["code_execute"],
                    "labels": ["testing"],
                    "acceptance_criteria": "Tests pass and acceptance criteria are validated.",
                }
            )
        if wants_docs or max_subtasks >= 4:
            plan.append(
                {
                    "kind": "document",
                    "title": f"Document rollout for {task_title}",
                    "description": f"{shared_context}Capture the final summary, operator notes, and any rollout caveats.",
                    "dependency_indexes": [1],
                    "parallelizable": True,
                    "required_tools": ["fs_write"],
                    "labels": ["documentation"],
                    "acceptance_criteria": "Documentation and rollout notes are updated.",
                }
            )
        return plan[:max_subtasks]

    async def list_milestones(self, user: User, project_id: str) -> list[ProjectMilestone]:
        await self.get_project(user, project_id)
        return await self.repo.list_project_milestones(project_id)

    async def create_milestone(self, user: User, project_id: str, title: str, description: str | None, due_date: Any, status: str, position: int) -> ProjectMilestone:
        await self.get_project(user, project_id)
        item = await self.repo.create_project_milestone(
            project_id=project_id,
            title=title,
            description=description,
            due_date=due_date,
            status=status,
            position=position,
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def update_milestone(self, user: User, project_id: str, milestone_id: str, updates: dict) -> ProjectMilestone:
        await self.get_project(user, project_id)
        item = await self.repo.update_project_milestone(milestone_id, {k: v for k, v in updates.items() if v is not None})
        if not item:
            raise HTTPException(status_code=404, detail="Milestone not found")
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_decisions(self, user: User, project_id: str) -> list[ProjectDecision]:
        await self.get_project(user, project_id)
        return await self.repo.list_project_decisions(project_id)

    async def create_decision(self, user: User, project_id: str, title: str, decision: str, rationale: str | None, author_label: str | None, task_id: str | None, brainstorm_id: str | None) -> ProjectDecision:
        project = await self.get_project(user, project_id)
        item = await self.repo.create_project_decision(
            project_id=project_id,
            task_id=task_id,
            brainstorm_id=brainstorm_id,
            title=title,
            decision=decision,
            rationale=rationale,
            author_label=author_label,
        )
        await self.db.commit()
        await self.db.refresh(item)
        await self._maybe_promote_decision_to_semantic(user, project, item)
        return item

    async def list_task_runs(self, user: User, project_id: str | None = None):
        return await self.repo.list_runs(user.id, project_id)

    async def get_run(self, user: User, run_id: str):
        run = await self.repo.get_run(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="Run not found")
        return run

    def _run_event_tail_payloads(self, events: list[Any], *, limit: int = 12) -> list[dict[str, Any]]:
        tail = events[-limit:] if len(events) > limit else events
        out: list[dict[str, Any]] = []
        for e in tail:
            msg = e.message or ""
            if len(msg) > 400:
                msg = msg[:400] + "…"
            out.append(
                {
                    "event_type": e.event_type,
                    "level": e.level,
                    "message": msg,
                    "created_at": e.created_at,
                }
            )
        return out

    def _workflow_steps_for_run(self, run: TaskRun) -> list[dict[str, Any]]:
        if run.run_mode == "manager_worker":
            return [
                {"id": "supervisor_plan", "title": "Supervisor plan", "actor": "supervisor"},
                {"id": "route_workers", "title": "Route workers", "actor": "supervisor"},
                {"id": "run_branches", "title": "Run delegated branches", "actor": "worker_pool"},
                {"id": "synthesize", "title": "Synthesize outputs", "actor": "supervisor"},
                {"id": "persist_output", "title": "Persist outputs", "actor": "system"},
            ]
        return [
            {"id": "build_prompt", "title": "Build prompt", "actor": "system"},
            {"id": "plan_execution", "title": "Plan execution", "actor": "supervisor"},
            {"id": "run_tools", "title": "Run tools", "actor": "worker_pool"},
            {"id": "model_response", "title": "Model response", "actor": "worker"},
            {"id": "persist_output", "title": "Persist outputs", "actor": "system"},
        ]

    def _ensure_run_workflow(self, run: TaskRun) -> dict[str, Any]:
        run.checkpoint_json = ensure_workflow_state(
            run.checkpoint_json,
            run_mode=run.run_mode,
            steps=self._workflow_steps_for_run(run),
        )
        return workflow_state(run.checkpoint_json)

    def _workflow_trace_payload(self, run: TaskRun) -> list[dict[str, Any]]:
        return summarize_trace(run.checkpoint_json)

    def _run_is_resumable(self, run: TaskRun) -> bool:
        state = workflow_state(run.checkpoint_json)
        if run.status not in {"failed", "blocked"}:
            return False
        step = current_step(run.checkpoint_json)
        return bool(step and step.get("resumable", True))

    async def _mark_run_step(
        self,
        run: TaskRun,
        *,
        step_id: str,
        status: str,
        message: str,
        event_type: str = "workflow_step",
        level: str = "info",
        metadata: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        run.checkpoint_json = mark_step(
            run.checkpoint_json,
            step_id=step_id,
            status=status,
            error=error,
            metadata=metadata,
        )
        await self._emit_run_event(
            run,
            event_type=event_type,
            level=level,
            message=message,
            payload={
                "step_id": step_id,
                "status": status,
                "trace": self._workflow_trace_payload(run),
                **dict(metadata or {}),
            },
        )

    def _workflow_checkpoint_artifact(self, run: TaskRun, key: str, default: Any = None) -> Any:
        return get_workflow_artifact(run.checkpoint_json, key, default)

    def _set_workflow_checkpoint_artifact(self, run: TaskRun, *, key: str, value: Any) -> None:
        run.checkpoint_json = set_workflow_artifact(run.checkpoint_json, key=key, value=value)

    async def get_task_execution_snapshot(self, user: User, project_id: str, task_id: str) -> dict[str, Any]:
        """Compose Layer-1 execution snapshot from Postgres only (no embedding search)."""
        task = await self.get_task(user, project_id, task_id)
        active_runs = await self.repo.list_active_runs_for_task(project_id, task_id)
        pending_approvals = await self.repo.list_pending_approvals_for_task(
            user.id, project_id, task_id
        )
        sync_all = await self.repo.list_sync_events_for_task(task_id)
        pending_sync = [e for e in sync_all if e.status in ("queued", "pending")]
        pending_sync = pending_sync[-10:]

        latest = await self.repo.get_latest_run_for_task(project_id, task_id)
        focal = active_runs[0] if active_runs else latest
        events_tail: list[dict[str, Any]] = []
        cp_excerpt: dict[str, Any] = {}
        if focal:
            raw_events = await self.repo.list_run_events(focal.id)
            events_tail = self._run_event_tail_payloads(raw_events, limit=8)
            cp_excerpt = checkpoint_excerpt(focal.checkpoint_json)

        meta = {
            "schema_version": EXECUTION_SNAPSHOT_SCHEMA_VERSION,
            "execution_truth": EXECUTION_TRUTH_DESCRIPTION,
            "sources_read": list(SNAPSHOT_SOURCES_TASK),
        }
        return {
            "meta": meta,
            "project_id": project_id,
            "task_id": task_id,
            "task_status": task.status,
            "task_title": task.title,
            "has_active_run": bool(active_runs),
            "active_runs": [
                {
                    "id": r.id,
                    "status": r.status,
                    "run_mode": r.run_mode,
                    "attempt_number": r.attempt_number,
                    "retry_count": r.retry_count,
                    "started_at": r.started_at,
                    "created_at": r.created_at,
                    "error_message": r.error_message,
                }
                for r in active_runs
            ],
            "pending_approvals": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "run_id": a.run_id,
                    "task_id": a.task_id,
                    "reason": a.reason,
                    "created_at": a.created_at,
                }
                for a in pending_approvals
            ],
            "pending_github_sync": [
                {
                    "id": e.id,
                    "action": e.action,
                    "status": e.status,
                    "detail": e.detail,
                    "created_at": e.created_at,
                }
                for e in pending_sync
            ],
            "metadata_views": extract_execution_metadata_views(task.metadata_json),
            "last_run_id": latest.id if latest else None,
            "focal_run_id": focal.id if focal else None,
            "checkpoint_excerpt": cp_excerpt,
            "recent_events_tail": events_tail,
            "trace": self._workflow_trace_payload(focal) if focal else [],
        }

    async def get_run_execution_snapshot(self, user: User, run_id: str) -> dict[str, Any]:
        """Run-scoped execution snapshot (relational reads only)."""
        run = await self.get_run(user, run_id)
        pending_approvals = await self.repo.list_pending_approvals_for_run(user.id, run_id)
        raw_events = await self.repo.list_run_events(run.id)
        events_tail = self._run_event_tail_payloads(raw_events, limit=12)
        pending_sync: list = []
        if run.task_id:
            sync_all = await self.repo.list_sync_events_for_task(run.task_id)
            pending_sync = [e for e in sync_all if e.status in ("queued", "pending")]
            pending_sync = pending_sync[-10:]
        meta = {
            "schema_version": EXECUTION_SNAPSHOT_SCHEMA_VERSION,
            "execution_truth": EXECUTION_TRUTH_DESCRIPTION,
            "sources_read": list(SNAPSHOT_SOURCES_RUN),
        }
        return {
            "meta": meta,
            "project_id": run.project_id,
            "run": run,
            "task_id": run.task_id,
            "pending_approvals": [
                {
                    "id": a.id,
                    "approval_type": a.approval_type,
                    "run_id": a.run_id,
                    "task_id": a.task_id,
                    "reason": a.reason,
                    "created_at": a.created_at,
                }
                for a in pending_approvals
            ],
            "pending_github_sync": [
                {
                    "id": e.id,
                    "action": e.action,
                    "status": e.status,
                    "detail": e.detail,
                    "created_at": e.created_at,
                }
                for e in pending_sync
            ],
            "checkpoint_excerpt": checkpoint_excerpt(run.checkpoint_json),
            "recent_events_tail": events_tail,
            "trace": self._workflow_trace_payload(run),
            "resumable": self._run_is_resumable(run),
        }

    async def get_working_memory(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        return working_memory_from_checkpoint(run.checkpoint_json)

    async def patch_working_memory(self, user: User, run_id: str, patch: dict[str, Any]) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        if not patch_allowed_for_run_status(run.status):
            raise HTTPException(
                status_code=409,
                detail="Working memory can only be edited while the run is queued, in progress, or blocked.",
            )
        current = working_memory_from_checkpoint(run.checkpoint_json)
        try:
            merged = merge_working_memory_patch(current, patch)
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        run.checkpoint_json = {**(run.checkpoint_json or {}), WORKING_MEMORY_KEY: merged}
        await self.db.commit()
        await self.db.refresh(run)
        return merged

    async def _semantic_context_snippets_for_prompt(
        self, task: OrchestratorTask, project: OrchestratorProject
    ) -> str:
        title_q = (task.title or "").strip()[:120] or None
        entries = await self.repo.list_semantic_memory_entries(
            project.owner_id,
            project_id=project.id,
            search=title_q,
            limit=6,
        )
        if not entries:
            return ""
        lines = [
            f"- [{e.entry_type}] **{e.title}** (`{e.namespace}`): {(e.body or '')[:420].strip()}"
            for e in entries
        ]
        return "Semantic memory (typed entries):\n" + "\n".join(lines)

    async def list_semantic_memory_entries_for_project(
        self,
        user: User,
        project_id: str,
        *,
        q: str | None = None,
        entry_type: str | None = None,
        namespace_prefix: str | None = None,
        vec_q: str | None = None,
        limit: int = 100,
    ) -> list[SemanticMemoryEntry]:
        project = await self.get_project(user, project_id)
        ms = merge_memory_settings(project.settings_json)
        rows = await self.repo.list_semantic_memory_entries(
            project.owner_id,
            project_id=project_id,
            entry_type=entry_type,
            namespace_prefix=namespace_prefix,
            search=q,
            limit=limit,
        )
        if (
            vec_q
            and vec_q.strip()
            and ms.get("enable_semantic_vector_search", True)
            and not settings.ORCHESTRATION_OFFLINE_MODE
        ):
            try:
                qv = (await self.ai_providers.embed_texts([vec_q.strip()[:8000]]))[0]
                vrows = await self.repo.search_semantic_memory_by_vector(
                    project.owner_id, project_id, qv, limit=limit
                )
                seen: set[str] = set()
                merged: list[SemanticMemoryEntry] = []
                for r in [*vrows, *rows]:
                    if r.id in seen:
                        continue
                    seen.add(r.id)
                    merged.append(r)
                increment_memory_metric("semantic_vector_queries")
                return merged[:limit]
            except Exception as exc:
                logger.warning("semantic vector search failed, using keyword only: %s", exc)
        return rows

    async def _persist_semantic_memory_row(
        self, user: User, project: OrchestratorProject, payload: dict[str, Any]
    ) -> SemanticMemoryEntry:
        project_id = project.id
        et = str(payload["entry_type"])
        if et not in SEMANTIC_ENTRY_TYPES:
            raise HTTPException(status_code=422, detail=f"Invalid entry_type: {et}")
        title = str(payload["title"]).strip()
        body = str(payload["body"]).strip()
        if not title or not body:
            raise HTTPException(status_code=422, detail="title and body are required")
        ns = str(payload.get("namespace") or "").strip() or _default_semantic_namespace(
            project_id, et, title
        )
        scope = str(payload.get("scope") or "project")
        if scope not in ("project", "agent", "company"):
            raise HTTPException(status_code=422, detail="Invalid scope")
        proj_for_row = None if scope == "company" else project_id
        entry = await self.repo.create_semantic_memory_entry(
            owner_id=project.owner_id,
            scope=scope,
            project_id=proj_for_row,
            agent_id=payload.get("agent_id"),
            entry_type=et,
            namespace=ns[:512],
            title=title[:255],
            body=body,
            metadata_json=dict(payload.get("metadata") or {}),
            source_chunk_id=payload.get("source_chunk_id"),
            source_task_id=payload.get("source_task_id"),
            source_run_id=payload.get("source_run_id"),
            provenance_json=dict(
                payload.get("provenance") or {"source": "api", "created_by_user_id": user.id}
            ),
            created_by_user_id=user.id,
        )
        ms_proj = merge_memory_settings(project.settings_json)
        if ms_proj.get("classifier_worker_enabled", True):
            await self.repo.create_memory_ingest_job(
                owner_id=project.owner_id,
                project_id=project_id,
                job_type="semantic_embed",
                payload_json={"entry_id": entry.id},
                status="pending",
            )
        else:
            self._schedule_semantic_embedding(entry.id)
        await self.db.commit()
        await self.db.refresh(entry)
        increment_memory_metric("semantic_entry_created")
        return entry

    async def create_semantic_memory_entry_for_project(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
        *,
        bypass_semantic_write_gate: bool = False,
    ) -> SemanticMemoryEntry | ApprovalRequest:
        project = await self.get_project(user, project_id)
        ms = merge_memory_settings(project.settings_json)
        if ms.get("semantic_write_requires_approval") and not bypass_semantic_write_gate:
            approval = await self.repo.create_approval(
                project_id=project_id,
                task_id=None,
                run_id=None,
                requested_by_user_id=user.id,
                approval_type="semantic_memory_write",
                status="pending",
                payload_json={"operation": "create", "payload": dict(payload)},
            )
            await self.db.commit()
            await self.db.refresh(approval)
            increment_memory_metric("semantic_write_approval_requested")
            return approval
        return await self._persist_semantic_memory_row(user, project, payload)

    async def get_semantic_memory_entry_for_project(
        self, user: User, project_id: str, entry_id: str
    ) -> SemanticMemoryEntry:
        project = await self.get_project(user, project_id)
        entry = await self.repo.get_semantic_memory_entry(project.owner_id, entry_id)
        if entry is None or entry.project_id != project_id:
            raise HTTPException(status_code=404, detail="Semantic entry not found")
        return entry

    async def _apply_semantic_entry_updates(
        self, entry: SemanticMemoryEntry, updates: dict[str, Any]
    ) -> None:
        if "title" in updates and updates["title"] is not None:
            entry.title = str(updates["title"])[:255]
        if "body" in updates and updates["body"] is not None:
            entry.body = str(updates["body"])
        if "entry_type" in updates and updates["entry_type"] is not None:
            et = str(updates["entry_type"])
            if et not in SEMANTIC_ENTRY_TYPES:
                raise HTTPException(status_code=422, detail="Invalid entry_type")
            entry.entry_type = et
        if "namespace" in updates and updates["namespace"] is not None:
            entry.namespace = str(updates["namespace"])[:512]
        if "metadata" in updates and updates["metadata"] is not None:
            entry.metadata_json = dict(updates["metadata"])

    async def update_semantic_memory_entry_for_project(
        self,
        user: User,
        project_id: str,
        entry_id: str,
        updates: dict[str, Any],
        *,
        bypass_semantic_write_gate: bool = False,
    ) -> SemanticMemoryEntry | ApprovalRequest:
        project = await self.get_project(user, project_id)
        entry = await self.get_semantic_memory_entry_for_project(user, project_id, entry_id)
        ms = merge_memory_settings(project.settings_json)
        if ms.get("semantic_write_requires_approval") and not bypass_semantic_write_gate:
            approval = await self.repo.create_approval(
                project_id=project_id,
                task_id=None,
                run_id=None,
                requested_by_user_id=user.id,
                approval_type="semantic_memory_write",
                status="pending",
                payload_json={
                    "operation": "update",
                    "entry_id": entry_id,
                    "updates": dict(updates),
                },
            )
            await self.db.commit()
            await self.db.refresh(approval)
            increment_memory_metric("semantic_write_approval_requested")
            return approval
        await self._apply_semantic_entry_updates(entry, updates)
        await self.db.commit()
        await self.db.refresh(entry)
        self._schedule_semantic_embedding(entry.id)
        return entry

    async def delete_semantic_memory_entry_for_project(
        self,
        user: User,
        project_id: str,
        entry_id: str,
        *,
        bypass_semantic_write_gate: bool = False,
    ) -> None | ApprovalRequest:
        project = await self.get_project(user, project_id)
        entry = await self.get_semantic_memory_entry_for_project(user, project_id, entry_id)
        ms = merge_memory_settings(project.settings_json)
        if ms.get("semantic_write_requires_approval") and not bypass_semantic_write_gate:
            approval = await self.repo.create_approval(
                project_id=project_id,
                task_id=None,
                run_id=None,
                requested_by_user_id=user.id,
                approval_type="semantic_memory_write",
                status="pending",
                payload_json={"operation": "delete", "entry_id": entry_id},
            )
            await self.db.commit()
            await self.db.refresh(approval)
            increment_memory_metric("semantic_write_approval_requested")
            return approval
        await self.db.delete(entry)
        await self.db.commit()
        return None

    async def promote_working_memory_to_semantic_entry(
        self,
        user: User,
        project_id: str,
        *,
        run_id: str,
        entry_type: str = "note",
        title: str | None = None,
    ) -> SemanticMemoryEntry:
        run = await self.get_run(user, run_id)
        if run.project_id != project_id:
            raise HTTPException(status_code=400, detail="Run is not in this project")
        wm = working_memory_from_checkpoint(run.checkpoint_json)
        chunks = [
            c
            for c in (
                wm.get("objective"),
                wm.get("accepted_plan"),
                wm.get("latest_findings"),
                wm.get("open_questions"),
            )
            if isinstance(c, str) and c.strip()
        ]
        body = "\n\n".join(chunks)[:50000]
        if not body.strip():
            raise HTTPException(status_code=400, detail="Working memory is empty; nothing to promote")
        et = entry_type if entry_type in SEMANTIC_ENTRY_TYPES else "note"
        default_title = (title or f"Promoted from run {run.id[:8]}")[:255]
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project_id,
            {
                "entry_type": et,
                "title": default_title,
                "body": body,
                "scope": "project",
                "source_task_id": run.task_id,
                "source_run_id": run.id,
                "provenance": {
                    "promoted_from": "working_memory_v1",
                    "run_id": run.id,
                    "working_memory_updated_at": wm.get("updated_at"),
                },
            },
            bypass_semantic_write_gate=False,
        )
        if isinstance(out, ApprovalRequest):
            raise HTTPException(
                status_code=403,
                detail="Semantic write requires approval; complete the pending approval first.",
            )
        return out

    def _schedule_semantic_embedding(self, entry_id: str) -> None:
        try:
            from backend.workers.orchestration import queue_semantic_embedding

            queue_semantic_embedding(entry_id)
        except Exception as exc:
            logger.warning("schedule semantic embedding failed: %s", exc)

    async def embed_semantic_memory_entry_worker(self, entry_id: str) -> None:
        """Worker: compute embedding_vector for a semantic row (pgvector)."""
        entry = await self.db.get(SemanticMemoryEntry, entry_id)
        if entry is None:
            return
        text = f"{entry.title}\n\n{entry.body}"[:8000]
        vec = (await self.ai_providers.embed_texts([text]))[0]
        entry.embedding_vector = normalize_embedding_for_vector(vec)
        await self.db.commit()
        increment_memory_metric("semantic_embeddings_completed")

    async def _maybe_promote_decision_to_semantic(
        self, user: User, project: OrchestratorProject, decision_row: ProjectDecision
    ) -> None:
        ms = merge_memory_settings(project.settings_json)
        if not ms.get("auto_promote_decisions"):
            return
        existing = await self.repo.find_semantic_by_decision_id(
            project.owner_id, project.id, decision_row.id
        )
        if existing:
            return
        body = (decision_row.decision or "").strip()
        if decision_row.rationale:
            body = f"{body}\n\nRationale:\n{decision_row.rationale.strip()}"
        if not body:
            return
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project.id,
            {
                "entry_type": "adr",
                "title": (decision_row.title or "Decision")[:255],
                "body": body,
                "scope": "project",
                "source_task_id": decision_row.task_id,
                "provenance": {
                    "source": "project_decision",
                    "decision_id": decision_row.id,
                },
            },
            bypass_semantic_write_gate=merge_memory_settings(project.settings_json).get(
                "auto_ingest_bypasses_semantic_approval", True
            ),
        )
        if isinstance(out, ApprovalRequest):
            return
        increment_memory_metric("auto_ingest_decisions")

    async def _maybe_promote_agent_memory_to_semantic(
        self, user: User, project: OrchestratorProject, memory: AgentMemoryEntry
    ) -> None:
        ms = merge_memory_settings(project.settings_json)
        if not ms.get("auto_promote_approved_agent_memory"):
            return
        existing = await self.repo.find_semantic_by_agent_memory_id(
            project.owner_id, project.id, memory.id
        )
        if existing:
            return
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project.id,
            {
                "entry_type": "preference",
                "title": f"Memory: {memory.key}"[:255],
                "body": memory.value_text,
                "scope": "project",
                "agent_id": memory.agent_id,
                "source_run_id": memory.source_run_id,
                "provenance": {"source": "agent_memory", "agent_memory_id": memory.id},
            },
            bypass_semantic_write_gate=merge_memory_settings(project.settings_json).get(
                "auto_ingest_bypasses_semantic_approval", True
            ),
        )
        if isinstance(out, ApprovalRequest):
            return
        increment_memory_metric("auto_ingest_agent_memory")

    async def _maybe_promote_task_close_working_memory(
        self, user: User, project: OrchestratorProject, task: OrchestratorTask
    ) -> None:
        ms = merge_memory_settings(project.settings_json)
        if not ms.get("task_close_auto_promote_working_memory"):
            return
        meta = dict(task.metadata_json or {})
        if meta.get("memory_task_close_promoted"):
            return
        existing = await self.repo.find_semantic_by_task_close(
            project.owner_id, project.id, task.id
        )
        if existing:
            return
        latest = await self.repo.get_latest_run_for_task(project.id, task.id)
        if not latest:
            return
        wm = working_memory_from_checkpoint(latest.checkpoint_json)
        chunks = [
            c
            for c in (
                wm.get("objective"),
                wm.get("accepted_plan"),
                wm.get("latest_findings"),
                wm.get("open_questions"),
            )
            if isinstance(c, str) and c.strip()
        ]
        body = "\n\n".join(chunks)[:50000]
        if not body.strip():
            return
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project.id,
            {
                "entry_type": "note",
                "title": f"Task close snapshot: {task.title or task.id[:8]}"[:255],
                "body": body,
                "scope": "project",
                "source_task_id": task.id,
                "source_run_id": latest.id,
                "provenance": {"source": "task_close", "task_id": task.id, "run_id": latest.id},
            },
            bypass_semantic_write_gate=merge_memory_settings(project.settings_json).get(
                "auto_ingest_bypasses_semantic_approval", True
            ),
        )
        if isinstance(out, ApprovalRequest):
            return
        await self.db.refresh(task)
        meta = dict(task.metadata_json or {})
        meta["memory_task_close_promoted"] = True
        task.metadata_json = meta
        await self.db.commit()
        increment_memory_metric("task_close_auto_promotions")

    async def get_project_memory_settings(self, user: User, project_id: str) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        return merge_memory_settings(project.settings_json)

    async def update_project_memory_settings(
        self, user: User, project_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        cur = merge_memory_settings(settings)
        allowed = set(cur.keys())
        for k, v in patch.items():
            if k in allowed:
                cur[k] = v
        settings["memory"] = cur
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return merge_memory_settings(project.settings_json)

    async def list_semantic_memory_conflicts(
        self, user: User, project_id: str
    ) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        entries = await self.repo.list_semantic_memory_entries(
            project.owner_id, project_id=project_id, limit=500
        )
        groups: dict[tuple[str, str], list[SemanticMemoryEntry]] = {}
        for e in entries:
            t = (e.title or "").lower()[:80].strip()
            key = (e.entry_type, t)
            groups.setdefault(key, []).append(e)
        out: list[dict[str, Any]] = []
        for (_et, title_key), items in groups.items():
            if len(items) < 2:
                continue
            bodies = {x.body.strip() for x in items}
            if len(bodies) < 2:
                continue
            out.append(
                {
                    "group_key": f"{_et}:{title_key}",
                    "entries": [
                        {
                            "id": x.id,
                            "title": x.title,
                            "namespace": x.namespace,
                            "updated_at": x.updated_at.isoformat(),
                        }
                        for x in items
                    ],
                }
            )
        return out

    async def _procedural_playbook_excerpt(
        self, project: OrchestratorProject | None, task: OrchestratorTask | None
    ) -> str:
        if not project or not task:
            return ""
        rows = await self.repo.list_procedural_playbooks(project.owner_id, project.id)
        if not rows:
            return ""
        labels = {str(x).lower() for x in (task.labels_json or [])}
        tt = (task.task_type or "").lower()
        bits: list[str] = []
        for pb in rows[:16]:
            tags = [str(t).lower() for t in (pb.tags_json or []) if t]
            if tags and tt not in tags and not labels.intersection(set(tags)):
                continue
            bits.append(f"**{pb.title}** (`{pb.slug}`):\n{(pb.body_md or '')[:900]}")
        return "\n\n".join(bits)[:2400]

    async def list_procedural_playbooks_for_project(
        self, user: User, project_id: str
    ) -> list[ProceduralPlaybook]:
        project = await self.get_project(user, project_id)
        return await self.repo.list_procedural_playbooks(project.owner_id, project_id)

    async def create_procedural_playbook_for_project(
        self, user: User, project_id: str, payload: dict[str, Any]
    ) -> ProceduralPlaybook:
        project = await self.get_project(user, project_id)
        slug = re.sub(r"[^a-z0-9]+", "-", str(payload.get("slug") or "").lower()).strip("-")[
            :128
        ] or "playbook"
        title = str(payload.get("title") or slug).strip()[:255]
        body = str(payload.get("body_md") or "").strip()
        if not body:
            raise HTTPException(status_code=422, detail="body_md is required")
        ns = str(payload.get("namespace") or "").strip() or f"project/{project_id}/procedural/{slug}"
        tags = payload.get("tags") if isinstance(payload.get("tags"), list) else []
        row = await self.repo.create_procedural_playbook(
            owner_id=project.owner_id,
            project_id=project_id,
            slug=slug,
            title=title,
            body_md=body,
            version=int(payload.get("version") or 1),
            tags_json=list(tags),
            namespace=ns[:512],
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def update_procedural_playbook_for_project(
        self, user: User, project_id: str, playbook_id: str, updates: dict[str, Any]
    ) -> ProceduralPlaybook:
        project = await self.get_project(user, project_id)
        row = await self.repo.get_procedural_playbook(project.owner_id, project_id, playbook_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Playbook not found")
        if "title" in updates and updates["title"] is not None:
            row.title = str(updates["title"])[:255]
        if "body_md" in updates and updates["body_md"] is not None:
            row.body_md = str(updates["body_md"])
        if "tags" in updates and updates["tags"] is not None:
            row.tags_json = list(updates["tags"])
        if "namespace" in updates and updates["namespace"] is not None:
            row.namespace = str(updates["namespace"])[:512]
        if "version" in updates and updates["version"] is not None:
            row.version = int(updates["version"])
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def delete_procedural_playbook_for_project(
        self, user: User, project_id: str, playbook_id: str
    ) -> None:
        project = await self.get_project(user, project_id)
        row = await self.repo.get_procedural_playbook(project.owner_id, project_id, playbook_id)
        if row is None:
            raise HTTPException(status_code=404, detail="Playbook not found")
        await self.db.delete(row)
        await self.db.commit()

    async def get_task_memory_coordination(
        self, user: User, project_id: str, task_id: str
    ) -> dict[str, Any]:
        task = await self.get_task(user, project_id, task_id)
        coord = (task.metadata_json or {}).get(MEMORY_COORDINATION_KEY) or {}
        return {
            "shared": coord.get("shared") if isinstance(coord.get("shared"), str) else "",
            "private": coord.get("private") if isinstance(coord.get("private"), dict) else {},
        }

    async def patch_task_memory_coordination(
        self, user: User, project_id: str, task_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        task = await self.get_task(user, project_id, task_id)
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        if "shared" in payload and payload["shared"] is not None:
            if self.action_requires_approval(project, "write_memory"):
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id,
                    run_id=None,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=user.id,
                    approval_type="shared_memory_write",
                    status="pending",
                    payload_json={
                        "task_id": task.id,
                        "shared": str(payload["shared"]),
                    },
                )
                await self.db.commit()
                raise HTTPException(
                    status_code=409,
                    detail={
                        "message": "Writing shared task memory requires approval.",
                        "approval_id": approval.id,
                    },
                )
        meta = dict(task.metadata_json or {})
        cur: dict[str, Any] = dict(meta.get(MEMORY_COORDINATION_KEY) or {})
        if "shared" in payload and payload["shared"] is not None:
            cur["shared"] = str(payload["shared"])
        if "private" in payload and isinstance(payload["private"], dict):
            merged_priv = dict(cur.get("private") or {})
            for k, v in payload["private"].items():
                merged_priv[str(k)] = str(v)
            cur["private"] = merged_priv
        meta[MEMORY_COORDINATION_KEY] = cur
        task.metadata_json = meta
        await self.db.commit()
        await self.db.refresh(task)
        return {
            "shared": cur.get("shared") or "",
            "private": cur.get("private") or {},
        }

    async def search_episodic_memory(
        self,
        user: User,
        project_id: str,
        *,
        q: str | None = None,
        vec_q: str | None = None,
        limit: int = 45,
        since: datetime | None = None,
        until: datetime | None = None,
        task_id: str | None = None,
        kinds: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        ms = merge_memory_settings(project.settings_json)
        base = await self.repo.search_episodic_for_project(
            project_id,
            query=q,
            limit=limit,
            since=since,
            until=until,
            task_id=task_id,
            kinds=kinds,
        )
        if (
            vec_q
            and str(vec_q).strip()
            and ms.get("enable_episodic_vector_search", True)
            and not settings.ORCHESTRATION_OFFLINE_MODE
        ):
            try:
                qv = (await self.ai_providers.embed_texts([str(vec_q).strip()[:8000]]))[0]
                idx_rows = await self.repo.search_episodic_index_by_vector(
                    project.owner_id, project_id, qv, limit=min(limit, 40)
                )
                vec_hits: list[dict[str, Any]] = []
                for r in idx_rows:
                    vec_hits.append(
                        {
                            "kind": f"indexed_{r.source_kind}",
                            "id": r.source_id,
                            "snippet": (r.text_content or "")[:500],
                            "created_at": r.created_at.isoformat(),
                            "index_id": r.id,
                        }
                    )
                seen: set[str] = set()
                merged: list[dict[str, Any]] = []
                for h in vec_hits + base:
                    key = f"{h.get('kind')}:{h.get('id')}"
                    if key in seen:
                        continue
                    seen.add(key)
                    merged.append(h)
                increment_memory_metric("episodic_vector_queries")
                return merged[:limit]
            except Exception as exc:
                logger.warning("episodic vector search failed: %s", exc)
        return base

    async def list_episodic_archive_manifests_for_project(
        self, user: User, project_id: str
    ) -> list[Any]:
        project = await self.get_project(user, project_id)
        return await self.repo.list_episodic_archive_manifests(project.owner_id, project_id)

    async def merge_semantic_memory_entries_for_project(
        self,
        user: User,
        project_id: str,
        *,
        canonical_entry_id: str,
        merge_entry_ids: list[str],
        link_relation: str = "supersedes",
    ) -> SemanticMemoryEntry:
        project = await self.get_project(user, project_id)
        canonical = await self.get_semantic_memory_entry_for_project(
            user, project_id, canonical_entry_id
        )
        bodies: list[str] = [canonical.body]
        merged_from: list[str] = []
        for eid in merge_entry_ids:
            if eid == canonical_entry_id:
                continue
            other = await self.get_semantic_memory_entry_for_project(user, project_id, eid)
            bodies.append(f"---\nMerged from {eid[:8]}:\n{other.body}")
            merged_from.append(other.id)
            await self.db.delete(other)
        canonical.body = "\n\n".join(bodies)[:100000]
        prov = dict(canonical.provenance_json or {})
        prov["merge"] = {
            "merged_ids": merge_entry_ids,
            "merged_entry_ids": merged_from,
            "relation": link_relation,
            "merged_at": datetime.now(UTC).isoformat(),
        }
        canonical.provenance_json = prov
        await self.db.commit()
        await self.db.refresh(canonical)
        self._schedule_semantic_embedding(canonical.id)
        increment_memory_metric("semantic_merges")
        return canonical

    async def create_semantic_memory_link_for_project(
        self,
        user: User,
        project_id: str,
        *,
        from_entry_id: str,
        to_entry_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticMemoryLink:
        project = await self.get_project(user, project_id)
        await self.get_semantic_memory_entry_for_project(user, project_id, from_entry_id)
        await self.get_semantic_memory_entry_for_project(user, project_id, to_entry_id)
        row = await self.repo.create_semantic_memory_link(
            owner_id=project.owner_id,
            project_id=project_id,
            from_entry_id=from_entry_id,
            to_entry_id=to_entry_id,
            relation_type=relation_type[:64],
            metadata_json=dict(metadata or {}),
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row

    async def list_semantic_memory_links_for_entry(
        self, user: User, project_id: str, entry_id: str
    ) -> list[SemanticMemoryLink]:
        project = await self.get_project(user, project_id)
        await self.get_semantic_memory_entry_for_project(user, project_id, entry_id)
        return await self.repo.list_semantic_memory_links(project.owner_id, project_id, entry_id)

    async def delete_semantic_memory_link_for_project(
        self, user: User, project_id: str, link_id: str
    ) -> None:
        project = await self.get_project(user, project_id)
        ok = await self.repo.delete_semantic_memory_link(project.owner_id, project_id, link_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Link not found")
        await self.db.commit()

    async def run_episodic_retention_and_archive_job(self) -> dict[str, Any]:
        """Archive old episodic sources to cold storage; trim search index (never deletes run_events)."""
        from sqlalchemy import select

        result = await self.db.execute(select(OrchestratorProject))
        projects = list(result.scalars().all())
        archived_projects = 0
        archived_bytes = 0
        index_rows_dropped = 0
        for project in projects:
            ms = merge_memory_settings(project.settings_json)
            if not ms.get("episodic_archive_enabled", True):
                continue
            days = int(ms.get("episodic_retention_days") or 90)
            cutoff = datetime.now(UTC) - timedelta(days=days)
            events = await self.repo.list_run_events_for_project_before(project.id, cutoff, limit=5000)
            if not events:
                continue
            records = [
                {
                    "kind": "run_event",
                    "id": ev.id,
                    "run_id": ev.run_id,
                    "task_id": ev.task_id,
                    "event_type": ev.event_type,
                    "message": ev.message,
                    "created_at": ev.created_at,
                }
                for ev in events
            ]
            try:
                body = build_episodic_archive_jsonl_gz(records)
            except Exception:
                continue
            tag = f"{cutoff.date().isoformat()}_{project.id[:8]}"
            key = episodic_object_key(project.owner_id, project.id, tag)
            try:
                await object_storage.upload_bytes(
                    object_key=key, body=body, content_type="application/gzip"
                )
            except StorageNotConfiguredError:
                logger.warning("episodic archive skipped: storage not configured")
                continue
            except Exception as exc:
                logger.warning("episodic archive upload failed: %s", exc)
                continue
            await self.repo.create_episodic_archive_manifest(
                owner_id=project.owner_id,
                project_id=project.id,
                object_key=key,
                period_start=events[0].created_at,
                period_end=events[-1].created_at,
                record_count=len(records),
                byte_size=len(body),
                stats_json={"kinds": {"run_event": len(records)}},
            )
            if ms.get("episodic_delete_index_after_archive", True):
                dropped = await self.repo.delete_episodic_index_rows_before(project.id, cutoff)
                index_rows_dropped += dropped
            await self.db.commit()
            archived_projects += 1
            archived_bytes += len(body)
        increment_memory_metric("episodic_retention_runs")
        return {
            "projects_touched": archived_projects,
            "archived_bytes": archived_bytes,
            "index_rows_dropped": index_rows_dropped,
        }

    async def backfill_episodic_search_index(self, user: User, project_id: str, *, limit: int = 200) -> int:
        """Index recent run events into episodic_search_index (snippets for vector search)."""
        project = await self.get_project(user, project_id)
        from sqlalchemy import select

        res = await self.db.execute(
            select(RunEvent)
            .join(TaskRun, RunEvent.run_id == TaskRun.id)
            .where(TaskRun.project_id == project_id)
            .order_by(RunEvent.created_at.desc())
            .limit(max(1, min(limit, 2000)))
        )
        events = list(res.scalars().all())
        n = 0
        for ev in events:
            existing = await self.repo.get_episodic_index_row(project_id, "run_event", ev.id)
            if existing:
                continue
            text = (ev.message or "")[:4000]
            if not text.strip():
                continue
            row = await self.repo.create_episodic_search_index_row(
                owner_id=project.owner_id,
                project_id=project_id,
                source_kind="run_event",
                source_id=ev.id,
                text_content=text,
                created_at=ev.created_at,
            )
            await self.db.flush()
            try:
                vec = (await self.ai_providers.embed_texts([text[:8000]]))[0]
                row.embedding_vector = normalize_embedding_for_vector(vec)
            except Exception:
                pass
            n += 1
        await self.db.commit()
        increment_memory_metric("episodic_index_backfills")
        return n

    async def process_episodic_index_embedding_batch(self, *, limit: int = 30) -> int:
        """Embed episodic index rows missing vectors (global, for Celery)."""
        from sqlalchemy import select

        res = await self.db.execute(select(OrchestratorProject.id))
        pids = [r[0] for r in res.all()]
        done = 0
        for pid in pids:
            rows = await self.repo.list_episodic_index_missing_embedding(pid, limit=limit)
            for row in rows:
                try:
                    vec = (await self.ai_providers.embed_texts([(row.text_content or "")[:8000]]))[0]
                    row.embedding_vector = normalize_embedding_for_vector(vec)
                    done += 1
                except Exception:
                    continue
            await self.db.commit()
        return done

    async def process_memory_ingest_jobs_worker(self, *, limit: int = 15) -> dict[str, Any]:
        jobs = await self.repo.list_pending_memory_ingest_jobs(limit=limit)
        processed = 0
        for job in jobs:
            await self.repo.update_memory_ingest_job(
                job.id, status="running", started_at=datetime.now(UTC)
            )
            await self.db.commit()
            try:
                jt = job.job_type
                payload = job.payload_json or {}
                if jt == "semantic_embed":
                    await self.embed_semantic_memory_entry_worker(str(payload.get("entry_id")))
                elif jt == "episodic_embed_index":
                    await self.process_episodic_index_embedding_batch(limit=5)
                elif jt == "document_ingest":
                    document = await self.repo.get_document(
                        str(payload.get("project_id") or ""),
                        str(payload.get("document_id") or ""),
                    )
                    if document is None:
                        raise RuntimeError("document_ingest target not found")
                    await self._index_project_document(document)
                elif jt == "repo_index":
                    await self._run_repository_index_job(
                        owner_id=str(job.owner_id),
                        project_id=str(payload.get("project_id") or ""),
                        repository_link_id=str(payload.get("repository_link_id") or ""),
                        requested_by_user_id=str(payload.get("requested_by_user_id") or "") or None,
                    )
                elif jt == "classifier_stub":
                    pass
                await self.repo.update_memory_ingest_job(
                    job.id, status="completed", finished_at=datetime.now(UTC)
                )
                processed += 1
            except Exception as exc:
                await self.repo.update_memory_ingest_job(
                    job.id,
                    status="failed",
                    error_text=str(exc)[:2000],
                    finished_at=datetime.now(UTC),
                )
            await self.db.commit()
        increment_memory_metric("memory_ingest_jobs_processed")
        return {"processed": processed, "batch_size": len(jobs)}

    async def _enforce_orchestration_run_rate_limit(self, user_id: str) -> None:
        limit = settings.ORCHESTRATION_RUN_RATE_LIMIT_PER_MINUTE
        if limit <= 0:
            return
        key = f"rate_limit:orch_run:{user_id}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, 60)
        if count > limit:
            raise HTTPException(
                status_code=429,
                detail="Too many orchestration runs started in the last minute. Try again shortly.",
            )

    async def _enforce_agent_token_budget(
        self,
        *,
        owner_id: str,
        agent_id: str | None,
    ) -> None:
        if not agent_id:
            return
        agent = await self.db.get(AgentProfile, agent_id)
        if agent is None:
            return
        budget = (agent.budget_json or {}).get("token_budget")
        if not budget:
            return
        try:
            cap = int(budget)
        except (TypeError, ValueError):
            return
        since = datetime.now(UTC) - timedelta(days=max(1, settings.AGENT_TOKEN_BUDGET_WINDOW_DAYS))
        used = await self.repo.sum_token_usage_for_agent(owner_id, agent_id, since)
        if used >= cap:
            raise HTTPException(
                status_code=429,
                detail="Agent token budget for the configured window is exhausted.",
            )

    async def _enforce_agent_cost_budget(
        self,
        *,
        owner_id: str,
        agent_id: str | None,
    ) -> None:
        if not agent_id:
            return
        agent = await self.db.get(AgentProfile, agent_id)
        if agent is None:
            return
        raw_cap = (agent.budget_json or {}).get("cost_cap_usd")
        if raw_cap is None:
            return
        try:
            cap_usd = float(raw_cap)
        except (TypeError, ValueError):
            return
        if cap_usd <= 0:
            return
        since = datetime.now(UTC) - timedelta(days=max(1, settings.AGENT_TOKEN_BUDGET_WINDOW_DAYS))
        used_micros = await self.repo.sum_estimated_cost_micros_for_agent(owner_id, agent_id, since)
        if used_micros / 1_000_000 >= cap_usd:
            raise HTTPException(
                status_code=429,
                detail="Agent cost budget (cost_cap_usd) for the configured window is exhausted.",
            )

    async def github_issue_summaries_for_link_ids(self, link_ids: list[str]) -> dict[str, dict[str, Any]]:
        return await self.repo.map_github_issue_summaries_by_link_id(link_ids)

    async def get_run_cost_summary(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        event_micros = await self.repo.sum_run_event_cost_micros_for_run(run.id)
        return {
            "run_id": run.id,
            "project_id": run.project_id,
            "status": run.status,
            "estimated_cost_usd": run.estimated_cost_micros / 1_000_000,
            "event_cost_sum_usd": event_micros / 1_000_000,
            "token_input": run.token_input,
            "token_output": run.token_output,
            "token_total": run.token_total,
            "model_name": run.model_name,
        }

    async def get_runtime_info(self, user: User) -> dict[str, Any]:
        """Non-secret orchestration flags for admin UI (air-gapped / failover toggles)."""
        _ = user
        return {
            "orchestration_offline_mode": settings.ORCHESTRATION_OFFLINE_MODE,
            "orchestration_provider_failover": settings.ORCHESTRATION_PROVIDER_FAILOVER,
            "orchestration_use_langgraph": settings.ORCHESTRATION_USE_LANGGRAPH,
            "orchestration_durable_queue_backend": settings.ORCHESTRATION_DURABLE_QUEUE_BACKEND,
            "celery_queues": {
                "orchestration": settings.CELERY_TASK_DEFAULT_QUEUE,
                "email": settings.CELERY_EMAIL_QUEUE,
                "github": settings.CELERY_QUEUE_GITHUB,
                "model_gateway": settings.CELERY_QUEUE_MODEL_GATEWAY,
                "observability": settings.CELERY_QUEUE_OBSERVABILITY,
            },
        }

    async def summarize_portfolio(self, user: User) -> list[dict[str, Any]]:
        return await self.repo.summarize_portfolio_for_owner(user.id)

    async def execution_insights(self, user: User, days: int = 7) -> dict[str, Any]:
        safe_days = max(1, min(int(days or 7), 90))
        since = datetime.now(UTC) - timedelta(days=safe_days)
        rows = await self.repo.aggregate_run_events_by_type_for_owner(user.id, since)
        by_type = {et: c for et, c in rows}
        tf_payloads = await self.repo.list_tool_failure_payloads_for_owner(user.id, since)
        tool_counts: Counter[str] = Counter()
        for payload in tf_payloads:
            tool = str((payload or {}).get("tool") or "unknown")
            tool_counts[tool] += 1
        tool_failures_by_tool = [{"tool": t, "count": n} for t, n in tool_counts.most_common(25)]
        return {
            "since": since,
            "days": safe_days,
            "by_event_type": [{"event_type": et, "count": c} for et, c in rows],
            "tool_failures_by_tool": tool_failures_by_tool,
            "reopen_events": int(by_type.get("reopened", 0)),
            "brainstorm_round_summary_events": int(by_type.get("brainstorm_round_summary", 0)),
            "blocked_events": int(by_type.get("blocked", 0)),
            "tool_call_failed_events": int(by_type.get("tool_call_failed", 0)),
        }

    async def brainstorm_discourse_insights(self, user: User, brainstorm_id: str) -> dict[str, Any]:
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        messages = await self.repo.list_brainstorm_messages(brainstorm_id)
        if not messages:
            return {
                "message_count": 0,
                "same_agent_streak_ratio": 0.0,
                "top_repeated_terms": [],
                "rounds_with_messages": 0,
                "last_round_repetition_score": None,
                "last_round_pairwise_min_similarity": None,
                "consensus_kind": None,
                "conflict_signal": None,
            }
        prev: str | None = None
        pairs = 0
        same = 0
        for m in messages:
            cur = m.agent_id or "unknown"
            if prev is not None:
                pairs += 1
                if cur == prev:
                    same += 1
            prev = cur
        ratio = same / pairs if pairs else 0.0
        stopwords = {
            "the",
            "and",
            "for",
            "with",
            "this",
            "that",
            "from",
            "have",
            "has",
            "are",
            "was",
            "were",
            "but",
            "not",
            "you",
            "your",
            "our",
            "their",
        }
        wc: Counter[str] = Counter()
        for m in messages:
            for w in re.findall(r"[a-zA-Z]{4,}", (m.content or "").lower()):
                if w not in stopwords:
                    wc[w] += 1
        top_terms = [w for w, _ in wc.most_common(12)]
        rounds = {m.round_number for m in messages}
        last_round = max((m.round_number for m in messages), default=0)
        last_contents = [m.content or "" for m in messages if m.round_number == last_round]
        stop_conditions = dict(brainstorm.stop_conditions_json or {})
        soft_thr = float(stop_conditions.get("soft_consensus_min_similarity", 0.72))
        conflict_thr = float(stop_conditions.get("conflict_pairwise_max_similarity", 0.38))
        metrics = self._brainstorm_consensus_metrics_from_contents(last_contents, soft_thr, conflict_thr)
        latest_log = None
        for entry in reversed(brainstorm.decision_log_json or []):
            if entry.get("type") == "round_summary":
                latest_log = entry
                break
        return {
            "message_count": len(messages),
            "same_agent_streak_ratio": round(float(ratio), 4),
            "top_repeated_terms": top_terms,
            "rounds_with_messages": len(rounds),
            "last_round_repetition_score": float(latest_log["repetition_score"])
            if latest_log and latest_log.get("repetition_score") is not None
            else metrics.get("repetition_score"),
            "last_round_pairwise_min_similarity": metrics.get("pairwise_min_similarity"),
            "consensus_kind": (latest_log or {}).get("consensus_kind") or metrics.get("consensus_kind"),
            "conflict_signal": (latest_log or {}).get("conflict_signal")
            if latest_log and "conflict_signal" in latest_log
            else metrics.get("conflict_signal"),
        }

    async def _run_selection_meta(
        self,
        *,
        project_id: str,
        task: OrchestratorTask,
        payload: dict[str, Any],
        execution_settings: dict[str, Any],
        run_mode: str,
        worker_agent_id: str | None,
        orchestrator_agent_id: str | None,
        worker_source: str | None,
        model_name: str | None,
        model_source: str,
    ) -> dict[str, Any]:
        worker_rationale = ""
        if worker_source == "payload":
            worker_rationale = "The worker agent was set explicitly in the run request payload."
        elif worker_source == "pinned":
            agent = await self.db.get(AgentProfile, worker_agent_id) if worker_agent_id else None
            nm = agent.name if agent else "the pinned agent"
            worker_rationale = (
                f"This run uses a pinned worker ({nm}) from task or project execution settings "
                "(or the run payload), after membership and task_filter checks."
            )
        elif worker_source == "task":
            agent = await self.db.get(AgentProfile, worker_agent_id) if worker_agent_id else None
            nm = agent.name if agent else "the assigned agent"
            worker_rationale = f"This run uses the task's assigned worker agent ({nm})."
        elif worker_source == "auto" and worker_agent_id:
            agent = await self.db.get(AgentProfile, worker_agent_id)
            required = set(self._extract_required_tools(task))
            tools = set(agent.allowed_tools_json or []) if agent else set()
            overlap = required & tools
            depths = await self.repo.count_active_runs_by_worker(project_id, [worker_agent_id])
            qd = depths.get(worker_agent_id, 0)
            nm = agent.name if agent else "An agent"
            parts = [
                f"{nm} was auto-selected from this project's eligible agents.",
            ]
            if required:
                parts.append(
                    f"The task lists these required_tools: {', '.join(sorted(required))}."
                )
                if overlap:
                    parts.append(
                        f"This agent's allowed_tools cover {len(overlap)} of them ({', '.join(sorted(overlap))})."
                    )
                else:
                    parts.append("No agent covered all required_tools; the lowest queue-depth eligible agent was used.")
            else:
                parts.append("No required_tools filter; chose lowest active-run load, then name order.")
            parts.append(f"Queued depth for this agent was {qd} other in-flight runs.")
            rm = execution_settings.get("routing_mode") or "capability_based"
            sb = execution_settings.get("sibling_load_balance") or "queue_depth"
            su = bool(execution_settings.get("skip_unhealthy_worker_providers", True))
            parts.append(
                f"Project routing_mode={rm}, sibling_load_balance={sb}, "
                f"skip_unhealthy_worker_providers={su}."
            )
            worker_rationale = " ".join(parts)
        elif worker_source == "debate_pair" and worker_agent_id:
            agent = await self.db.get(AgentProfile, worker_agent_id)
            nm = agent.name if agent else "Agent A"
            worker_rationale = (
                f"{nm} leads the debate side as the first seat in the auto-ranked debate pair "
                "(capability overlap, queue depth, then name)."
            )
        elif not worker_agent_id:
            worker_rationale = "No worker agent is attached to this run (orchestration-only / planner mode)."
        else:
            worker_rationale = "Worker routing metadata is unavailable for this run."

        if model_source == "payload":
            model_rationale = "The model name was set explicitly on the run API request."
        elif model_source == "project_execution":
            model_rationale = (
                "Uses execution.model_name from the orchestration project settings (org-wide default for this project)."
            )
        else:
            model_rationale = (
                "No explicit model on the run or project; the worker uses provider defaults or policy routing "
                "when the first LLM call is made."
            )

        return {
            "worker_agent_id_source": worker_source,
            "model_source": model_source,
            "worker_agent_rationale": worker_rationale,
            "model_rationale": model_rationale,
            "run_mode": run_mode,
            "orchestrator_agent_id": orchestrator_agent_id,
            "worker_agent_id": worker_agent_id,
            "model_name": model_name,
            "routing_mode": execution_settings.get("routing_mode") or "capability_based",
            "sibling_load_balance": execution_settings.get("sibling_load_balance") or "queue_depth",
            "skip_unhealthy_worker_providers": bool(
                execution_settings.get("skip_unhealthy_worker_providers", True)
            ),
        }

    async def start_task_run(
        self,
        user: User,
        project_id: str,
        task_id: str,
        payload: dict[str, Any],
    ):
        await self._enforce_orchestration_run_rate_limit(user.id)
        project = await self.get_project(user, project_id)
        task = await self.get_task(user, project_id, task_id)
        deps = await self.repo.list_task_dependencies_for_task(task.id)
        if deps:
            blocking = []
            for dep in deps:
                dep_task = await self.db.get(OrchestratorTask, dep.depends_on_task_id)
                if dep_task and dep_task.status not in {"completed", "approved"}:
                    blocking.append(dep_task.title)
            if blocking:
                raise HTTPException(400, f"Task has incomplete dependencies: {blocking}")
        execution_settings = self._project_execution_settings(project)
        run_mode = payload.get("run_mode", "single_agent")
        orchestrator_agent_id = payload.get("orchestrator_agent_id") or execution_settings.get("manager_agent_id")
        reviewer_agent_id = payload.get("reviewer_agent_id") or task.reviewer_agent_id
        if reviewer_agent_id is None:
            reviewer_ids = execution_settings.get("reviewer_agent_ids", [])
            reviewer_agent_id = reviewer_ids[0] if reviewer_ids else None
        if reviewer_agent_id and task.reviewer_agent_id != reviewer_agent_id:
            task.reviewer_agent_id = reviewer_agent_id
            chain = [str(item).strip() for item in execution_settings.get("reviewer_agent_ids", []) if str(item).strip()]
            if chain and reviewer_agent_id in chain:
                meta = dict(task.metadata_json or {})
                meta["review_chain"] = {
                    "reviewer_agent_ids": chain,
                    "current_index": chain.index(reviewer_agent_id),
                }
                task.metadata_json = meta
                orm_attributes.flag_modified(task, "metadata_json")

        worker_explicit = "worker_agent_id" in payload and payload.get("worker_agent_id") is not None
        if worker_explicit:
            worker_agent_id = payload.get("worker_agent_id")
            worker_source = "payload"
        else:
            pinned_raw = (
                payload.get("pinned_worker_agent_id")
                or (task.metadata_json or {}).get("pinned_worker_agent_id")
                or execution_settings.get("pinned_worker_agent_id")
            )
            if pinned_raw:
                worker_agent_id = str(pinned_raw)
                worker_source = "pinned"
            elif task.assigned_agent_id:
                worker_agent_id = task.assigned_agent_id
                worker_source = "task"
            else:
                worker_agent_id = None
                worker_source = None

        if run_mode in {"single_agent", "manager_worker", "debate"} and worker_agent_id is None:
            selected_worker = await self._select_best_agent_for_task(
                project.id,
                task=task,
                exclude_agent_ids=[orchestrator_agent_id] if orchestrator_agent_id else [],
            )
            worker_agent_id = selected_worker.id if selected_worker else None
            worker_source = "auto" if worker_agent_id else worker_source

        if run_mode == "manager_worker" and orchestrator_agent_id is None:
            manager = await self._project_default_manager(project.id)
            orchestrator_agent_id = manager.id if manager else None

        if run_mode == "debate":
            pair = await self._select_debate_pair(
                project.id,
                task,
                exclude_agent_ids=[orchestrator_agent_id] if orchestrator_agent_id else [],
            )
            if pair:
                worker_agent_id = pair[0].id
                if len(pair) > 1:
                    reviewer_agent_id = pair[1].id
                worker_source = "debate_pair"

        if worker_agent_id and worker_source == "pinned":
            member_ids = {m.agent_id for m in await self.repo.list_project_memberships(project.id)}
            if worker_agent_id not in member_ids:
                raise HTTPException(
                    status_code=400,
                    detail="pinned_worker_agent_id is not a member of this project.",
                )
            p_agent = await self._load_agent_for_run(worker_agent_id)
            if p_agent is None or not p_agent.is_active:
                raise HTTPException(status_code=400, detail="Pinned worker agent is missing or inactive.")
            if not self._agent_eligible_for_task_by_filters(p_agent, task):
                raise HTTPException(
                    status_code=400,
                    detail="Pinned worker agent task_filters do not match this task.",
                )

        if run_mode in {"single_agent", "manager_worker", "debate"} and worker_agent_id:
            worker = await self._load_agent_for_run(worker_agent_id)
            req_tools = self._extract_required_tools(task)
            if req_tools and not self._required_tools_satisfied(worker, req_tools):
                raise HTTPException(
                    status_code=400,
                    detail=(
                        "Worker agent allowed_tools must include every task required_tools entry: "
                        + ", ".join(req_tools)
                    ),
                )

        payload_model = payload.get("model_name")
        if payload_model not in (None, ""):
            model_source = "payload"
        elif execution_settings.get("model_name"):
            model_source = "project_execution"
        else:
            model_source = "runtime_default"
        model_name = payload_model or execution_settings.get("model_name")

        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=worker_agent_id)
        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=orchestrator_agent_id)
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=worker_agent_id)
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=orchestrator_agent_id)

        selection_meta = await self._run_selection_meta(
            project_id=project.id,
            task=task,
            payload=payload,
            execution_settings=execution_settings,
            run_mode=run_mode,
            worker_agent_id=worker_agent_id,
            orchestrator_agent_id=orchestrator_agent_id,
            worker_source=worker_source,
            model_name=model_name,
            model_source=model_source,
        )
        input_payload = dict(payload.get("input_payload") or {})
        prev_meta = input_payload.get("orchestration_meta")
        if isinstance(prev_meta, dict):
            input_payload["orchestration_meta"] = {**prev_meta, **selection_meta}
        else:
            input_payload["orchestration_meta"] = selection_meta

        run = await self.repo.create_run(
            project_id=project_id,
            task_id=task.id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=orchestrator_agent_id,
            worker_agent_id=worker_agent_id,
            reviewer_agent_id=reviewer_agent_id,
            provider_config_id=payload.get("provider_config_id") or execution_settings.get("provider_config_id"),
            run_mode=run_mode,
            status="queued",
            model_name=model_name,
            input_payload_json=input_payload,
        )
        await self._transition_task_status(task, "queued", run=run, reason="run queued")
        await self._emit_run_event(
            run,
            event_type="queued",
            message="Run queued for execution.",
            payload={"run_mode": run.run_mode},
        )
        await self.db.commit()
        from backend.modules.orchestration.durable_execution import submit_orchestration_run

        submit_orchestration_run(run.id)
        await self.db.refresh(run)
        return run

    async def cancel_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        run.status = "cancelled"
        run.cancelled_at = datetime.now(UTC)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        if task and task.status in {"queued", "planned", "in_progress"}:
            await self._transition_task_status(task, "planned", run=run, reason="run cancelled")
        await self._emit_run_event(
            run,
            event_type="cancelled",
            level="warning",
            message="Run cancelled by user.",
        )
        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def resume_run(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        if not self._run_is_resumable(run):
            raise HTTPException(status_code=409, detail="Run is not resumable from its current checkpoint.")
        run.status = "queued"
        run.error_message = None
        run.completed_at = None
        run.cancelled_at = None
        run.checkpoint_json = increment_resume_count(run.checkpoint_json)
        await self._emit_run_event(
            run,
            event_type="workflow_resumed",
            message="Run resumed from durable checkpoint.",
            payload={"trace": self._workflow_trace_payload(run)},
        )
        await self.db.commit()
        from backend.modules.orchestration.durable_execution import submit_orchestration_run

        submit_orchestration_run(run.id)
        await self.db.refresh(run)
        return run

    async def replay_run(
        self,
        user: User,
        run_id: str,
        from_event_index: int = 0,
        *,
        model_name: str | None = None,
    ):
        """Queue a new run that carries forward transcript context from a parent run."""
        await self._enforce_orchestration_run_rate_limit(user.id)
        old = await self.get_run(user, run_id)
        old_project = await self.db.get(OrchestratorProject, old.project_id)
        if old_project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await self._enforce_agent_token_budget(owner_id=old_project.owner_id, agent_id=old.worker_agent_id)
        await self._enforce_agent_token_budget(owner_id=old_project.owner_id, agent_id=old.orchestrator_agent_id)
        await self._enforce_agent_cost_budget(owner_id=old_project.owner_id, agent_id=old.worker_agent_id)
        await self._enforce_agent_cost_budget(owner_id=old_project.owner_id, agent_id=old.orchestrator_agent_id)
        events = await self.repo.list_run_events(old.id)
        if from_event_index < 0 or from_event_index > len(events):
            raise HTTPException(status_code=400, detail="from_event_index is out of range for this run")
        prior = events[:from_event_index]
        transcript = "\n".join(f"[{e.event_type}] {e.message}" for e in prior)
        base_input = dict(old.input_payload_json or {})
        base_input.pop("orchestration_replay", None)
        base_input["orchestration_replay"] = {
            "parent_run_id": old.id,
            "from_event_index": from_event_index,
            "prior_transcript": transcript[:12000],
        }
        old_orch = base_input.get("orchestration_meta")
        if isinstance(old_orch, dict):
            base_input["orchestration_meta"] = {**old_orch, "replayed_from_run_id": old.id}
        else:
            base_input["orchestration_meta"] = {"replayed_from_run_id": old.id}
        new_run = await self.repo.create_run(
            project_id=old.project_id,
            task_id=old.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=old.orchestrator_agent_id,
            worker_agent_id=old.worker_agent_id,
            reviewer_agent_id=old.reviewer_agent_id,
            provider_config_id=old.provider_config_id,
            brainstorm_id=old.brainstorm_id,
            run_mode=old.run_mode,
            status="queued",
            model_name=(str(model_name).strip() or old.model_name) if model_name is not None else old.model_name,
            attempt_number=old.attempt_number + 1,
            retry_count=old.retry_count,
            checkpoint_json=dict(old.checkpoint_json or {}),
            input_payload_json=base_input,
        )
        task = await self.db.get(OrchestratorTask, new_run.task_id) if new_run.task_id else None
        if task:
            await self._transition_task_status(task, "queued", run=new_run, reason="replay queued")
        await self._emit_run_event(
            new_run,
            event_type="replay_queued",
            message=f"Replay from run {old.id} starting after event index {from_event_index}.",
            payload={"parent_run_id": old.id, "from_event_index": from_event_index},
        )
        await self.db.commit()
        from backend.modules.orchestration.durable_execution import submit_orchestration_run

        submit_orchestration_run(new_run.id)
        await self.db.refresh(new_run)
        return new_run

    async def aggregate_cost_analytics(self, user: User, days: int = 30) -> dict[str, Any]:
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        raw = await self.repo.aggregate_run_costs(user.id, since=since)
        by_agent = []
        for row in raw["by_agent"]:
            aid = row["agent_id"]
            agent = await self.db.get(AgentProfile, aid) if aid else None
            by_agent.append(
                {
                    "name": agent.name if agent else str(aid)[:8],
                    "cost_usd": row["cost_usd"],
                    "tokens": row["tokens"],
                    "runs": row["runs"],
                }
            )
        by_agent.sort(key=lambda item: item["cost_usd"], reverse=True)
        by_project = sorted(raw["by_project"], key=lambda item: item["cost_usd"], reverse=True)
        by_provider = sorted(raw["by_provider"], key=lambda item: item["cost_usd"], reverse=True)
        total_cost = raw["total_cost_micros"] / 1_000_000
        return {
            "period": f"last_{days}_days",
            "by_project": by_project,
            "by_agent": by_agent,
            "by_provider": by_provider,
            "most_expensive_runs": raw["most_expensive_runs"],
            "total_cost_usd": total_cost,
            "total_tokens": raw["total_tokens"],
        }

    async def run_agent_simulation(
        self,
        user: User,
        agent_id: str,
        *,
        scenarios: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        agent = await self.get_agent(user, agent_id)
        cases = scenarios or [
            {"title": "Bug triage", "description": "Identify likely root cause and first fix.", "acceptance_criteria": "Clear diagnosis + first patch."},
            {"title": "Spec drafting", "description": "Write a concise API spec with risks.", "acceptance_criteria": "Endpoints + risks + rollout plan."},
            {"title": "Review response", "description": "Review a patch proposal for correctness.", "acceptance_criteria": "Find at least one risk and test gap."},
        ]
        results: list[dict[str, Any]] = []
        pass_count = 0
        for idx, case in enumerate(cases, start=1):
            probe = await self.test_run_agent(
                user,
                agent_id,
                {
                    "prompt": str(case.get("description") or case.get("title") or "Simulation task"),
                    "max_output_tokens": 400,
                    "temperature": 0.2,
                    "simulate_tools": True,
                },
            )
            output = str(probe.get("output_text") or "")
            passed = len(output.strip()) >= 40
            if passed:
                pass_count += 1
            results.append(
                {
                    "scenario_index": idx,
                    "title": str(case.get("title") or f"Scenario {idx}"),
                    "passed": passed,
                    "latency_ms": int(probe.get("latency_ms") or 0),
                    "token_total": int(probe.get("token_total") or 0),
                    "estimated_cost_usd": float(probe.get("estimated_cost_usd") or 0),
                    "output_preview": output[:280],
                }
            )
        avg_cost = sum(float(item["estimated_cost_usd"]) for item in results) / max(len(results), 1)
        avg_latency = sum(int(item["latency_ms"]) for item in results) / max(len(results), 1)
        readiness = "ready" if pass_count >= max(1, int(len(results) * 0.67)) and avg_cost < 0.5 else "needs_tuning"
        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "readiness": readiness,
            "pass_rate": round(pass_count / max(len(results), 1), 3),
            "avg_cost_usd": round(avg_cost, 6),
            "avg_latency_ms": round(avg_latency, 1),
            "results": results,
        }

    async def bootstrap_project_from_text(self, user: User, prompt: str) -> dict[str, Any]:
        text = str(prompt or "").strip()
        if not text:
            raise HTTPException(status_code=422, detail="Prompt is required")
        sentence = text[:200]
        slug_base = re.sub(r"[^a-z0-9]+", "-", sentence.lower()).strip("-")[:40] or "new-project"
        return {
            "approved": False,
            "proposal": {
                "name": sentence[:80].title(),
                "slug": slug_base,
                "description": f"Bootstrapped from natural-language request: {sentence}",
                "goals": [
                    f"Deliver requested outcome: {sentence}",
                    "Establish milestones and measurable acceptance criteria",
                    "Keep cost and risk within project policies",
                ],
                "milestones": [
                    {"title": "Discovery & scope", "description": "Clarify scope and dependencies"},
                    {"title": "Implementation", "description": "Build and validate core functionality"},
                    {"title": "Release readiness", "description": "Review, approvals, and rollout"},
                ],
                "tasks": [
                    {"title": "Draft implementation plan", "task_type": "planning", "priority": "high"},
                    {"title": "Implement core feature set", "task_type": "feature", "priority": "normal"},
                    {"title": "Validation and handoff", "task_type": "review", "priority": "normal"},
                ],
                "team_suggestion": {"manager_role": "manager", "worker_roles": ["specialist", "reviewer"]},
            },
        }

    async def apply_bootstrap_project(self, user: User, payload: dict[str, Any]) -> OrchestratorProject:
        proposal = dict(payload.get("proposal") or payload)
        project = await self.create_project(
            user,
            {
                "name": proposal.get("name") or "Bootstrapped Project",
                "slug": proposal.get("slug"),
                "description": proposal.get("description"),
                "goals_markdown": "\n".join(f"- {g}" for g in (proposal.get("goals") or [])),
                "settings": {"bootstrap_source": "natural_language"},
            },
        )
        for idx, ms in enumerate((proposal.get("milestones") or [])[:12]):
            await self.create_milestone(
                user,
                project.id,
                title=str(ms.get("title") or f"Milestone {idx + 1}"),
                description=str(ms.get("description") or ""),
                due_date=None,
                status="open",
                position=idx,
            )
        for t in (proposal.get("tasks") or [])[:30]:
            await self.create_task(
                user,
                project.id,
                {
                    "title": str(t.get("title") or "Bootstrapped task"),
                    "description": str(t.get("description") or ""),
                    "task_type": str(t.get("task_type") or "general"),
                    "priority": str(t.get("priority") or "normal"),
                    "status": "backlog",
                },
            )
        return project

    async def agent_performance_scorecard(self, user: User, days: int = 30) -> list[dict[str, Any]]:
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 365)))
        runs = await self.repo.list_runs(user.id, None)
        by_agent: dict[str, dict[str, Any]] = {}
        for run in runs:
            if run.created_at < since:
                continue
            agent_id = run.worker_agent_id or run.orchestrator_agent_id
            if not agent_id:
                continue
            row = by_agent.setdefault(
                agent_id,
                {"agent_id": agent_id, "runs": 0, "accepted": 0, "latency": 0, "cost": 0, "escalations": 0, "review_pass": 0, "review_total": 0},
            )
            row["runs"] += 1
            row["latency"] += int(run.latency_ms or 0)
            row["cost"] += float(run.estimated_cost_micros or 0) / 1_000_000
            if run.status == "completed":
                row["accepted"] += 1
            if run.run_mode == "review":
                row["review_total"] += 1
                if run.status == "completed":
                    row["review_pass"] += 1
            evs = await self.repo.list_run_events(run.id)
            row["escalations"] += sum(1 for e in evs if e.event_type in {"rule_escalation", "task_escalation"})
        output: list[dict[str, Any]] = []
        for aid, row in by_agent.items():
            agent = await self.db.get(AgentProfile, aid)
            runs_n = max(int(row["runs"]), 1)
            acc_rate = float(row["accepted"]) / runs_n
            avg_cost = float(row["cost"]) / runs_n
            avg_lat = float(row["latency"]) / runs_n
            review_pass_rate = float(row["review_pass"]) / max(int(row["review_total"]), 1) if row["review_total"] else 1.0
            under = acc_rate < 0.6 or review_pass_rate < 0.6 or avg_cost > 2.0
            output.append(
                {
                    "agent_id": aid,
                    "agent_name": agent.name if agent else aid[:8],
                    "acceptance_rate": round(acc_rate, 3),
                    "avg_cost_usd": round(avg_cost, 6),
                    "avg_latency_ms": round(avg_lat, 2),
                    "review_pass_rate": round(review_pass_rate, 3),
                    "escalation_frequency": round(float(row["escalations"]) / runs_n, 3),
                    "underperforming": under,
                    "suggestion": "Tune prompts/skills and lower-risk routing." if under else "Performance within target.",
                }
            )
        output.sort(key=lambda item: (item["underperforming"], -item["acceptance_rate"]), reverse=True)
        return output

    async def project_budget_projection(self, user: User, days: int = 30) -> dict[str, Any]:
        cost = await self.aggregate_cost_analytics(user, days=days)
        total = float(cost.get("total_cost_usd") or 0)
        burn_daily = total / max(days, 1)
        projected_month = burn_daily * 30.0
        return {
            "days": days,
            "total_cost_usd": round(total, 6),
            "daily_burn_usd": round(burn_daily, 6),
            "projected_monthly_usd": round(projected_month, 6),
            "soft_cap_warning": projected_month > 1000,
            "hard_cap_exceeded": projected_month > 5000,
        }

    async def explain_run(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        events = await self.repo.list_run_events(run.id)
        approvals = await self.repo.list_pending_approvals_for_run(user.id, run.id)
        tools = [str(e.payload_json.get("tool") or "") for e in events if e.event_type.startswith("tool_call_")]
        tools = [t for t in tools if t]
        selection = read_orchestration_selection_meta(run.input_payload_json or {})
        return {
            "run_id": run.id,
            "summary": (
                f"Run used agent {run.worker_agent_id or run.orchestrator_agent_id}, "
                f"model {run.model_name or 'default'}, executed {len(tools)} tool calls, "
                f"and finished with status {run.status}."
            ),
            "agent_rationale": selection.worker_agent_rationale,
            "model_rationale": selection.model_rationale,
            "tools_called": tools[:50],
            "approvals_pending": len(approvals),
            "approvals_pending_types": [a.approval_type for a in approvals],
        }

    async def _compress_run_context_if_needed(self, run: TaskRun) -> None:
        payload = dict(run.input_payload_json or {})
        replay = payload.get("orchestration_replay")
        if not isinstance(replay, dict):
            return
        transcript = str(replay.get("prior_transcript") or "")
        if len(transcript) < 4000:
            return
        compressed = transcript[:1800] + "\n...\n" + transcript[-1200:]
        replay["prior_transcript"] = compressed
        payload["orchestration_replay"] = replay
        run.input_payload_json = payload
        saved_chars = max(len(transcript) - len(compressed), 0)
        run.checkpoint_json = set_workflow_artifact(
            run.checkpoint_json,
            key="context_compression",
            value={
                "saved_chars": saved_chars,
                "saved_tokens_estimate": int(saved_chars / 4),
            },
        )
        await self._emit_run_event(
            run,
            event_type="context_compressed",
            message="Replay context compressed to reduce token usage.",
            payload={"saved_chars": saved_chars, "saved_tokens_estimate": int(saved_chars / 4)},
        )

    async def _enforce_run_output_schema(self, run: TaskRun) -> None:
        agent = await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id)
        schema = (agent.output_schema_json or {}) if agent else {}
        fmt = str(schema.get("format") or "").strip()
        final_output = str((run.output_payload_json or {}).get("final_output") or (run.output_payload_json or {}).get("summary") or "")
        if not fmt or not final_output:
            return
        valid = True
        if fmt == "json":
            try:
                json.loads(final_output)
            except Exception:
                valid = False
        elif fmt == "checklist":
            valid = "- " in final_output or "1." in final_output
        elif fmt == "adr":
            low = final_output.lower()
            valid = "decision" in low and "context" in low
        if not valid:
            raise BlockedExecution(f"Output validation failed for schema format '{fmt}'.")

    async def _detect_and_log_task_output_conflict(self, task: OrchestratorTask, run: TaskRun) -> None:
        if not task.id:
            return
        all_runs = await self.repo.list_runs(task.created_by_user_id, task.project_id)
        related = [r for r in all_runs if r.task_id == task.id and r.id != run.id and r.status == "completed"]
        if not related:
            return
        current = str((run.output_payload_json or {}).get("final_output") or (run.output_payload_json or {}).get("summary") or "").strip()
        if not current:
            return
        previous = str((related[-1].output_payload_json or {}).get("final_output") or (related[-1].output_payload_json or {}).get("summary") or "").strip()
        if not previous:
            return
        contradict = ("approve" in current.lower() and "reject" in previous.lower()) or ("reject" in current.lower() and "approve" in previous.lower())
        if not contradict:
            return
        await self.repo.create_approval(
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            issue_link_id=task.github_issue_link_id,
            requested_by_user_id=run.triggered_by_user_id,
            approval_type="output_conflict_resolution",
            status="pending",
            payload_json={
                "current_run_id": run.id,
                "previous_run_id": related[-1].id,
                "current_summary": current[:500],
                "previous_summary": previous[:500],
            },
        )
        await self._transition_task_status(task, "blocked", run=run, reason="conflicting agent outputs require resolution")

    async def ingest_incident_alert(self, user: User, payload: dict[str, Any]) -> OrchestratorTask:
        project_id = str(payload.get("project_id") or "")
        project = await self.get_project(user, project_id)
        source = str(payload.get("source") or "webhook")
        title = str(payload.get("title") or "Incident alert")
        body = str(payload.get("body") or "")
        severity = str(payload.get("severity") or "high")
        task = await self.create_task(
            user,
            project.id,
            {
                "title": f"[Incident:{severity}] {title}",
                "description": body,
                "priority": "urgent" if severity in {"critical", "sev1"} else "high",
                "task_type": "incident",
                "status": "planned",
                "metadata": {"incident_source": source, "alert_payload": payload},
            },
        )
        return task

    async def pr_assistant_review(self, user: User, payload: dict[str, Any]) -> dict[str, Any]:
        repo = str(payload.get("repository_full_name") or "unknown/repo")
        pr_number = int(payload.get("pr_number") or 0)
        summary = str(payload.get("diff_summary") or payload.get("title") or "")
        findings = []
        if "TODO" in summary or "FIXME" in summary:
            findings.append("Found unresolved TODO/FIXME markers in PR summary.")
        if "secret" in summary.lower() or "token" in summary.lower():
            findings.append("Potential secret handling risk detected; review carefully.")
        verdict = "request_changes" if findings else "approve"
        return {
            "repository_full_name": repo,
            "pr_number": pr_number,
            "verdict": verdict,
            "findings": findings or ["No blocking findings in lightweight assistant review."],
        }

    async def list_custom_workflow_templates(self, user: User, project_id: str) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        return list((project.settings_json or {}).get("custom_workflow_templates") or [])

    async def save_custom_workflow_template(self, user: User, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        current = list(settings.get("custom_workflow_templates") or [])
        item = {
            "id": str(payload.get("id") or uuid.uuid4()),
            "name": str(payload.get("name") or "Custom workflow"),
            "stages": list(payload.get("stages") or []),
            "forked_from": payload.get("forked_from"),
            "updated_at": datetime.now(UTC).isoformat(),
        }
        current = [c for c in current if str(c.get("id")) != item["id"]]
        current.append(item)
        settings["custom_workflow_templates"] = current
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return item

    async def pin_agent_skills(self, user: User, agent_id: str, payload: dict[str, Any]) -> AgentProfile:
        agent = await self.get_agent(user, agent_id)
        pins = list(payload.get("skill_pins") or [])
        meta = dict(agent.metadata_json or {})
        meta["skill_pins"] = pins
        agent.metadata_json = meta
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def list_agent_schedules(self, user: User, project_id: str) -> list[dict[str, Any]]:
        project = await self.get_project(user, project_id)
        return list((((project.settings_json or {}).get("execution") or {}).get("agent_schedules") or []))

    async def save_agent_schedule(self, user: User, project_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        project = await self.get_project(user, project_id)
        settings = dict(project.settings_json or {})
        execution = dict(settings.get("execution") or {})
        rows = list(execution.get("agent_schedules") or [])
        item = {
            "id": str(payload.get("id") or uuid.uuid4()),
            "agent_id": str(payload.get("agent_id") or ""),
            "cron": str(payload.get("cron") or ""),
            "action": str(payload.get("action") or "triage"),
            "enabled": bool(payload.get("enabled", True)),
        }
        rows = [r for r in rows if str(r.get("id")) != item["id"]]
        rows.append(item)
        execution["agent_schedules"] = rows
        settings["execution"] = execution
        project.settings_json = self._normalize_project_settings(settings)
        await self.db.commit()
        await self.db.refresh(project)
        return item

    async def list_eval_records(self, user: User, project_id: str) -> list[EvalRecord]:
        await self.get_project(user, project_id)
        return await self.repo.list_eval_records(project_id)

    async def create_eval_record(self, user: User, project_id: str, payload: dict[str, Any]) -> EvalRecord:
        await self.get_project(user, project_id)
        if payload.get("task_id"):
            await self.get_task(user, project_id, payload["task_id"])
        if payload.get("agent_a_id"):
            await self.get_agent(user, payload["agent_a_id"])
        if payload.get("agent_b_id"):
            await self.get_agent(user, payload["agent_b_id"])
        record = await self.repo.create_eval_record(
            project_id=project_id,
            name=payload["name"],
            task_id=payload.get("task_id"),
            agent_a_id=payload.get("agent_a_id"),
            agent_b_id=payload.get("agent_b_id"),
            model_a=payload.get("model_a"),
            model_b=payload.get("model_b"),
        )
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def update_eval_record(self, user: User, project_id: str, eval_id: str, payload: dict[str, Any]) -> EvalRecord:
        await self.get_project(user, project_id)
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record:
            raise HTTPException(status_code=404, detail="Eval record not found")
        for field in ("winner", "score_a", "score_b", "criteria_met_a", "criteria_met_b", "notes"):
            if field in payload and payload[field] is not None:
                setattr(record, field, payload[field])
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def score_eval_record(self, user: User, project_id: str, eval_id: str) -> EvalRecord:
        await self.get_project(user, project_id)
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record:
            raise HTTPException(status_code=404, detail="Eval record not found")
        run_metrics: dict[str, dict[str, float | int | None]] = {}
        for run_id, side in ((record.run_a_id, "a"), (record.run_b_id, "b")):
            if not run_id:
                continue
            try:
                run = await self.get_run(user, run_id)
            except HTTPException:
                continue
            run_metrics[side] = {
                "latency_ms": run.latency_ms,
                "cost_usd": run.estimated_cost_micros / 1_000_000,
                "tokens": run.token_total,
                "status": run.status,
            }
            if not run.task_id:
                continue
            result = await self.check_task_acceptance(user, project_id, run.task_id)
            passed = result["passed"]
            ratio = sum(1 for c in result["checks"] if c["passed"]) / max(len(result["checks"]), 1)
            score = round(ratio * 100, 1)
            if side == "a":
                record.criteria_met_a = passed
                record.score_a = score
            else:
                record.criteria_met_b = passed
                record.score_b = score
        meta = {**(record.metadata_json or {}), "benchmark_run_metrics": run_metrics}
        a_m = run_metrics.get("a") or {}
        b_m = run_metrics.get("b") or {}
        if a_m and b_m:
            ca, cb = float(a_m.get("cost_usd") or 0), float(b_m.get("cost_usd") or 0)
            la = a_m.get("latency_ms")
            lb = b_m.get("latency_ms")
            la_f = float(la) if la is not None else None
            lb_f = float(lb) if lb is not None else None
            cheaper = "a" if ca < cb else "b" if cb < ca else "tie"
            faster = (
                "a"
                if la_f is not None and lb_f is not None and la_f < lb_f
                else "b"
                if la_f is not None and lb_f is not None and lb_f < la_f
                else "tie"
            )
            meta["benchmark_efficiency"] = {"cheaper_side": cheaper, "faster_side": faster}
        record.metadata_json = meta
        await self.db.commit()
        await self.db.refresh(record)
        return record

    async def eval_leaderboard(self, user: User, project_id: str) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        records = await self.repo.list_eval_records(project_id)
        if not records:
            return []
        board: dict[str, dict[str, Any]] = {}

        def ensure(agent_id: str) -> dict[str, Any]:
            item = board.get(agent_id)
            if item is None:
                item = {
                    "agent_id": agent_id,
                    "agent_name": agent_id[:8],
                    "wins": 0,
                    "losses": 0,
                    "ties": 0,
                    "total": 0,
                    "score_sum": 0.0,
                    "score_n": 0,
                    "cost_sum": 0.0,
                    "cost_n": 0,
                    "lat_sum": 0.0,
                    "lat_n": 0,
                }
                board[agent_id] = item
            return item

        for record in records:
            pairs = [
                ("a", record.agent_a_id, record.score_a),
                ("b", record.agent_b_id, record.score_b),
            ]
            metrics = (record.metadata_json or {}).get("benchmark_run_metrics") or {}
            for side, agent_id, score in pairs:
                if not agent_id:
                    continue
                row = ensure(agent_id)
                row["total"] += 1
                if score is not None:
                    row["score_sum"] += float(score)
                    row["score_n"] += 1
                side_metrics = metrics.get(side) if isinstance(metrics, dict) else None
                if isinstance(side_metrics, dict):
                    if side_metrics.get("cost_usd") is not None:
                        row["cost_sum"] += float(side_metrics["cost_usd"])
                        row["cost_n"] += 1
                    if side_metrics.get("latency_ms") is not None:
                        row["lat_sum"] += float(side_metrics["latency_ms"])
                        row["lat_n"] += 1
            if record.winner == "a" and record.agent_a_id:
                ensure(record.agent_a_id)["wins"] += 1
                if record.agent_b_id:
                    ensure(record.agent_b_id)["losses"] += 1
            elif record.winner == "b" and record.agent_b_id:
                ensure(record.agent_b_id)["wins"] += 1
                if record.agent_a_id:
                    ensure(record.agent_a_id)["losses"] += 1
            elif record.winner == "tie":
                if record.agent_a_id:
                    ensure(record.agent_a_id)["ties"] += 1
                if record.agent_b_id:
                    ensure(record.agent_b_id)["ties"] += 1

        for agent_id, row in board.items():
            agent = await self.db.get(AgentProfile, agent_id)
            if agent:
                row["agent_name"] = agent.name

        result = []
        for row in board.values():
            total = max(int(row["total"]), 1)
            result.append(
                {
                    "agent_id": row["agent_id"],
                    "agent_name": row["agent_name"],
                    "wins": int(row["wins"]),
                    "losses": int(row["losses"]),
                    "ties": int(row["ties"]),
                    "total": int(row["total"]),
                    "win_rate": round(float(row["wins"]) / total, 4),
                    "avg_score": round(float(row["score_sum"]) / max(int(row["score_n"]), 1), 2),
                    "avg_cost_usd": round(float(row["cost_sum"]) / max(int(row["cost_n"]), 1), 6),
                    "avg_latency_ms": round(float(row["lat_sum"]) / max(int(row["lat_n"]), 1), 2),
                }
            )
        result.sort(key=lambda item: (item["win_rate"], item["wins"], item["avg_score"]), reverse=True)
        return result

    async def benchmark_historical_issues(
        self,
        user: User,
        project_id: str,
        *,
        agent_a_id: str,
        agent_b_id: str,
        model_a: str | None = None,
        model_b: str | None = None,
        days: int = 60,
        limit: int = 8,
    ) -> dict[str, Any]:
        await self.get_project(user, project_id)
        await self.get_agent(user, agent_a_id)
        await self.get_agent(user, agent_b_id)
        tasks = await self.repo.list_tasks(project_id)
        since = datetime.now(UTC) - timedelta(days=max(1, min(days, 3650)))
        candidate_tasks = [
            t for t in tasks
            if t.github_issue_link_id and t.created_at >= since and t.status in {"completed", "approved", "synced_to_github", "archived"}
        ][: max(1, min(limit, 50))]
        created: list[dict[str, Any]] = []
        for task in candidate_tasks:
            record = await self.create_eval_record(
                user,
                project_id,
                {
                    "name": f"Historical benchmark: {task.title[:80]}",
                    "task_id": task.id,
                    "agent_a_id": agent_a_id,
                    "agent_b_id": agent_b_id,
                    "model_a": model_a,
                    "model_b": model_b,
                },
            )
            launched = await self.start_benchmark(user, project_id, record.id)
            created.append({"eval_id": record.id, "task_id": task.id, "runs": launched.get("runs", [])})
        return {"created": created, "count": len(created)}

    async def start_benchmark(self, user: User, project_id: str, eval_id: str) -> dict[str, Any]:
        await self._enforce_orchestration_run_rate_limit(user.id)
        await self.get_project(user, project_id)
        record = await self.repo.get_eval_record(project_id, eval_id)
        if not record:
            raise HTTPException(status_code=404, detail="Eval record not found")
        if not record.task_id:
            raise HTTPException(status_code=400, detail="Eval record needs a task_id to benchmark")
        if not record.agent_a_id or not record.agent_b_id:
            raise HTTPException(status_code=400, detail="Both agent_a_id and agent_b_id are required to start a benchmark")
        source = await self.get_task(user, project_id, record.task_id)
        meta = {
            **(source.metadata_json or {}),
            "benchmark_eval_id": record.id,
            "benchmark_source_task_id": source.id,
        }
        task_a = await self.create_task(
            user,
            project_id,
            {
                "title": f"[Benchmark A] {record.name}",
                "description": source.description,
                "acceptance_criteria": source.acceptance_criteria,
                "priority": source.priority,
                "task_type": source.task_type,
                "status": "backlog",
                "assigned_agent_id": record.agent_a_id,
                "metadata": {**meta, "benchmark_side": "a"},
            },
        )
        task_b = await self.create_task(
            user,
            project_id,
            {
                "title": f"[Benchmark B] {record.name}",
                "description": source.description,
                "acceptance_criteria": source.acceptance_criteria,
                "priority": source.priority,
                "task_type": source.task_type,
                "status": "backlog",
                "assigned_agent_id": record.agent_b_id,
                "metadata": {**meta, "benchmark_side": "b"},
            },
        )
        run_a = await self.start_task_run(
            user,
            project_id,
            task_a.id,
            {
                "run_mode": "single_agent",
                "worker_agent_id": record.agent_a_id,
                "model_name": record.model_a,
                "input_payload": {"benchmark_eval_id": record.id, "benchmark_side": "a"},
            },
        )
        run_b = await self.start_task_run(
            user,
            project_id,
            task_b.id,
            {
                "run_mode": "single_agent",
                "worker_agent_id": record.agent_b_id,
                "model_name": record.model_b,
                "input_payload": {"benchmark_eval_id": record.id, "benchmark_side": "b"},
            },
        )
        record.run_a_id = run_a.id
        record.run_b_id = run_b.id
        record.metadata_json = {
            **(record.metadata_json or {}),
            "benchmark_task_a_id": task_a.id,
            "benchmark_task_b_id": task_b.id,
        }
        await self.db.commit()
        await self.db.refresh(record)
        return {
            "eval_id": record.id,
            "runs": [{"side": "a", "run_id": run_a.id}, {"side": "b", "run_id": run_b.id}],
        }

    async def retry_run(self, user: User, run_id: str):
        await self._enforce_orchestration_run_rate_limit(user.id)
        run = await self.get_run(user, run_id)
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise HTTPException(status_code=404, detail="Project not found")
        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=run.worker_agent_id)
        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=run.orchestrator_agent_id)
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=run.worker_agent_id)
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=run.orchestrator_agent_id)
        new_run = await self.repo.create_run(
            project_id=run.project_id,
            task_id=run.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=run.orchestrator_agent_id,
            worker_agent_id=run.worker_agent_id,
            reviewer_agent_id=run.reviewer_agent_id,
            provider_config_id=run.provider_config_id,
            brainstorm_id=run.brainstorm_id,
            run_mode=run.run_mode,
            status="queued",
            model_name=run.model_name,
            attempt_number=run.attempt_number + 1,
            retry_count=run.retry_count + 1,
            input_payload_json=run.input_payload_json,
        )
        task = await self.db.get(OrchestratorTask, new_run.task_id) if new_run.task_id else None
        if task:
            await self._transition_task_status(task, "queued", run=new_run, reason="retry queued")
        await self._emit_run_event(
            new_run,
            event_type="retry_queued",
            message=f"Retry created from run {run.id}.",
            payload={"previous_run_id": run.id},
        )
        await self.db.commit()
        from backend.modules.orchestration.durable_execution import submit_orchestration_run

        submit_orchestration_run(new_run.id)
        await self.db.refresh(new_run)
        return new_run

    async def list_run_events(self, user: User, run_id: str):
        run = await self.get_run(user, run_id)
        return await self.repo.list_run_events(run.id)

    async def execute_run(self, run_id: str) -> TaskRun:
        run = await self.repo.get_run_for_worker(run_id)
        if run is None:
            raise RuntimeError(f"Run {run_id} not found")
        if run.status == "cancelled":
            return run
        prior_status = run.status
        workflow = self._ensure_run_workflow(run)
        run.status = "in_progress"
        run.started_at = datetime.now(UTC)
        run.checkpoint_json = {
            **(run.checkpoint_json or {}),
            EXECUTION_THREAD_ID_KEY: run.id,
        }
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError(f"Project {run.project_id} not found")
        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=run.worker_agent_id)
        await self._enforce_agent_token_budget(owner_id=project.owner_id, agent_id=run.orchestrator_agent_id)
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=run.worker_agent_id)
        await self._enforce_agent_cost_budget(owner_id=project.owner_id, agent_id=run.orchestrator_agent_id)
        if task is not None:
            if task.status == "queued":
                await self._transition_task_status(task, "planned", run=run, reason="execution planning")
            await self._transition_task_status(task, "in_progress", run=run, reason="execution started")
        await self._emit_run_event(
            run,
            event_type="started",
            message="Run execution started.",
            payload={
                "run_mode": run.run_mode,
                "durable_backend": workflow.get("backend"),
                "trace": self._workflow_trace_payload(run),
            },
        )
        if prior_status in {"failed", "blocked"}:
            await self._emit_run_event(
                run,
                event_type="workflow_recovery",
                message="Worker resumed execution from checkpoint after a recoverable interruption.",
                payload={"prior_status": prior_status, "trace": self._workflow_trace_payload(run)},
            )

        try:
            await self._compress_run_context_if_needed(run)
            if settings.ORCHESTRATION_USE_LANGGRAPH:
                from backend.modules.orchestration.langgraph_runner import run_via_langgraph

                await run_via_langgraph(self, run)
            elif run.run_mode == "brainstorm":
                await self._execute_brainstorm_run(run)
            elif run.run_mode == "review":
                await self._execute_review_run(run)
            elif run.run_mode == "debate":
                await self._execute_debate_run(run)
            elif run.run_mode == "manager_worker":
                await self._execute_manager_worker_run(run)
            else:
                await self._execute_single_agent_run(run)

            await self._enforce_run_output_schema(run)
            run.status = "completed"
            run.completed_at = datetime.now(UTC)
            run.checkpoint_json = set_workflow_artifact(
                mark_step(
                    run.checkpoint_json,
                    step_id=self._workflow_steps_for_run(run)[-1]["id"],
                    status="completed",
                ),
                key="final_status",
                value="completed",
            )
            if task and run.run_mode != "brainstorm":
                task.result_summary = (
                    str(
                        run.output_payload_json.get("summary")
                        or run.output_payload_json.get("final_output")
                        or ""
                    )[:2000]
                    or task.result_summary
                )
                if task.status not in {"blocked", "approved", "completed", "needs_review"}:
                    next_status = "needs_review" if task.reviewer_agent_id else "completed"
                    await self._transition_task_status(task, next_status, run=run, reason="run completed")
                self._update_task_execution_memory(task, run)
                await self._detect_and_log_task_output_conflict(task, run)
            await self._emit_run_event(
                run,
                event_type="completed",
                message="Run completed successfully.",
                payload=run.output_payload_json,
            )
            await self._persist_agent_memory_from_run(
                run,
                await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id),
                task,
            )
            if task:
                await self._sync_run_completion_to_github(run, task)
            if task and task.github_issue_link_id and run.run_mode != "brainstorm":
                await self.repo.create_approval(
                    project_id=run.project_id,
                    task_id=task.id,
                    run_id=run.id,
                    issue_link_id=task.github_issue_link_id,
                    requested_by_user_id=run.triggered_by_user_id,
                    approval_type="github_comment",
                    status="pending",
                    payload_json={
                        "draft_comment": task.result_summary or "Task completed.",
                        "close_issue": False,
                    },
                )
            await self.db.commit()
            if task:
                await self._apply_project_escalation_rules(project, run=run, task=task, trigger="run_completed")
            return run
        except BlockedExecution as exc:
            run.status = "blocked"
            run.error_message = str(exc)
            step = current_step(run.checkpoint_json)
            if step:
                await self._mark_run_step(
                    run,
                    step_id=str(step.get("id")),
                    status="blocked",
                    level="warning",
                    message=f"Checkpoint captured at blocked step '{step.get('title')}'.",
                    error=str(exc),
                )
            if task:
                await self._transition_task_status(task, "blocked", run=run, reason=str(exc))
            await self._emit_run_event(
                run,
                event_type="blocked",
                level="warning",
                message=str(exc),
            )
            await self.db.commit()
            if task:
                await self._apply_project_escalation_rules(project, run=run, task=task, trigger="task_blocked")
            return run
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            step = current_step(run.checkpoint_json)
            if step:
                await self._mark_run_step(
                    run,
                    step_id=str(step.get("id")),
                    status="failed",
                    level="error",
                    message=f"Failure captured for step '{step.get('title')}'.",
                    error=str(exc),
                )
            if task:
                if task.status != "blocked":
                    await self._transition_task_status(task, "failed", run=run, reason=str(exc))
            await self._emit_run_event(
                run,
                event_type="failed",
                level="error",
                message=str(exc),
            )
            await self.db.commit()
            if task:
                await self._apply_project_escalation_rules(project, run=run, task=task, trigger="run_failed")
            return run

    async def list_providers(self, user: User, project_id: str | None = None):
        return await self.repo.list_providers(user.id, project_id)

    async def create_provider(self, user: User, payload: dict[str, Any]):
        await self._ensure_catalog_seeded()
        if payload.get("is_default"):
            for provider in await self.repo.list_providers(user.id, payload.get("project_id")):
                provider.is_default = False
        metadata = dict(payload.get("metadata") or {})
        provider = await self.repo.create_provider(
            owner_id=user.id,
            project_id=payload.get("project_id"),
            name=payload["name"],
            provider_type=payload["provider_type"],
            base_url=payload.get("base_url"),
            encrypted_api_key=encrypt_secret(payload["api_key"]) if payload.get("api_key") else None,
            api_key_hint=mask_secret(payload.get("api_key")),
            organization=payload.get("organization"),
            default_model=payload["default_model"],
            fallback_model=payload.get("fallback_model"),
            temperature=payload.get("temperature", 0.2),
            max_tokens=payload.get("max_tokens", 4096),
            timeout_seconds=payload.get("timeout_seconds", 120),
            is_default=payload.get("is_default", False),
            is_enabled=payload.get("is_enabled", True),
            metadata_json=metadata,
        )
        if provider.provider_type == "ollama":
            try:
                await self._refresh_provider_models(provider)
            except Exception as exc:
                provider.metadata_json = {
                    **(provider.metadata_json or {}),
                    "last_discovery_error": str(exc),
                }
        await self._validate_provider_models(provider)
        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def update_provider(self, user: User, provider_id: str, updates: dict[str, Any]):
        await self._ensure_catalog_seeded()
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        if updates.get("is_default"):
            for item in await self.repo.list_providers(user.id, provider.project_id):
                item.is_default = False
        for field, value in updates.items():
            if field == "api_key":
                provider.encrypted_api_key = encrypt_secret(value) if value else None
                provider.api_key_hint = mask_secret(value)
            elif field == "metadata":
                provider.metadata_json = value
            else:
                setattr(provider, field, value)
        if provider.provider_type == "ollama":
            try:
                await self._refresh_provider_models(provider)
            except Exception as exc:
                provider.metadata_json = {
                    **(provider.metadata_json or {}),
                    "last_discovery_error": str(exc),
                }
        await self._validate_provider_models(provider)
        await self.db.commit()
        await self.db.refresh(provider)
        return provider

    async def test_provider(self, user: User, provider_id: str):
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        result = await self._healthcheck_provider(provider)
        await self.db.commit()
        return result

    async def list_provider_models_for_user(self, user: User, provider_id: str) -> dict[str, Any]:
        provider = await self.repo.get_provider(user.id, provider_id)
        if not provider:
            raise HTTPException(status_code=404, detail="Provider not found")
        models = await self._refresh_provider_models(provider)
        await self.db.commit()
        return {
            "provider_id": provider.id,
            "provider_type": provider.provider_type,
            "models": models,
        }

    async def list_model_capabilities(self) -> list[ModelCapability]:
        await self._ensure_catalog_seeded()
        return await self.repo.list_model_capabilities()

    async def compare_providers(self, user: User, payload: dict[str, Any]) -> dict[str, Any]:
        provider_a = await self.repo.get_provider(user.id, payload["provider_a_id"])
        provider_b = await self.repo.get_provider(user.id, payload["provider_b_id"])
        if not provider_a or not provider_b:
            raise HTTPException(status_code=404, detail="One or more providers were not found")
        prompt_parts = [f"Task title: {payload['task_title']}"]
        if payload.get("task_description"):
            prompt_parts.append(f"Task description: {payload['task_description']}")
        if payload.get("acceptance_criteria"):
            prompt_parts.append(f"Acceptance criteria: {payload['acceptance_criteria']}")
        if payload.get("task_metadata"):
            prompt_parts.append(
                f"Task metadata: {json.dumps(payload['task_metadata'], indent=2, default=str)}"
            )
        prompt_parts.append(
            "Produce a concise execution proposal with key steps, risks, and expected output."
        )
        final_prompt = "\n\n".join(prompt_parts)
        result_a = await execute_prompt(
            provider_a,
            model_name=payload.get("model_a") or provider_a.default_model,
            system_prompt="You are an AI task execution planner.",
            user_prompt=final_prompt,
        )
        result_b = await execute_prompt(
            provider_b,
            model_name=payload.get("model_b") or provider_b.default_model,
            system_prompt="You are an AI task execution planner.",
            user_prompt=final_prompt,
        )
        return {
            "prompt_preview": final_prompt[:3000],
            "result_a": {
                "provider_id": provider_a.id,
                "provider_name": provider_a.name,
                "provider_type": provider_a.provider_type,
                "model_name": result_a.model_name,
                "latency_ms": result_a.latency_ms,
                "input_tokens": result_a.input_tokens,
                "output_tokens": result_a.output_tokens,
                "token_total": result_a.total_tokens,
                "estimated_cost_usd": self._estimate_cost_micros(
                    provider_a, result_a.input_tokens, result_a.output_tokens, model_name=result_a.model_name
                )
                / 1_000_000,
                "output_text": result_a.output_text,
                "is_healthy": bool(provider_a.is_healthy),
            },
            "result_b": {
                "provider_id": provider_b.id,
                "provider_name": provider_b.name,
                "provider_type": provider_b.provider_type,
                "model_name": result_b.model_name,
                "latency_ms": result_b.latency_ms,
                "input_tokens": result_b.input_tokens,
                "output_tokens": result_b.output_tokens,
                "token_total": result_b.total_tokens,
                "estimated_cost_usd": self._estimate_cost_micros(
                    provider_b, result_b.input_tokens, result_b.output_tokens, model_name=result_b.model_name
                )
                / 1_000_000,
                "output_text": result_b.output_text,
                "is_healthy": bool(provider_b.is_healthy),
            },
        }

    async def create_brainstorm(self, user: User, payload: dict[str, Any]):
        project = await self.get_project(user, payload["project_id"])
        if payload.get("task_id"):
            await self.get_task(user, project.id, payload["task_id"])
        stop_conditions = self._normalize_brainstorm_stop_conditions(payload)
        participant_ids: list[str] = []
        seen_participants: set[str] = set()
        for raw_id in payload.get("participant_agent_ids", []):
            agent_id = str(raw_id).strip()
            if not agent_id or agent_id in seen_participants:
                continue
            seen_participants.add(agent_id)
            participant_ids.append(agent_id)
        if len(participant_ids) < 2:
            raise HTTPException(
                status_code=400,
                detail="A brainstorm requires at least two unique participant agents.",
            )
        moderator_agent_id = payload.get("moderator_agent_id")
        if moderator_agent_id:
            await self.get_agent(user, moderator_agent_id)
        else:
            manager = await self._project_default_manager(project.id, project=project)
            moderator_agent_id = manager.id if manager else participant_ids[0]
        item = await self.repo.create_brainstorm(
            project_id=project.id,
            task_id=payload.get("task_id"),
            initiator_user_id=user.id,
            moderator_agent_id=moderator_agent_id,
            topic=payload["topic"],
            max_rounds=payload.get("max_rounds", 3),
            stop_conditions_json=stop_conditions,
            decision_log_json=[],
        )
        profiles: list[AgentProfile] = []
        for agent_id in participant_ids:
            profiles.append(await self.get_agent(user, agent_id))
        for i, left in enumerate(profiles):
            for right in profiles[i + 1 :]:
                if not self._brainstorm_pair_allowed(left, right):
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Brainstorm collaboration rules disallow pairing '{left.slug}' "
                            f"with '{right.slug}' (allowed_brainstorm_with)."
                        ),
                    )
        for index, agent_id in enumerate(participant_ids):
            await self.repo.create_brainstorm_participant(
                brainstorm_id=item.id,
                agent_id=agent_id,
                order_index=index,
            )
        await self.db.commit()
        await self.db.refresh(item)
        await self._decorate_brainstorms([item])
        return item

    async def list_brainstorms(self, user: User, project_id: str | None = None):
        items = await self.repo.list_brainstorms(user.id, project_id)
        await self._decorate_brainstorms(items)
        return items

    async def get_brainstorm(self, user: User, brainstorm_id: str):
        item = await self.repo.get_brainstorm(user.id, brainstorm_id)
        if not item:
            raise HTTPException(status_code=404, detail="Brainstorm not found")
        await self._decorate_brainstorms([item])
        return item

    async def list_brainstorm_participants(self, user: User, brainstorm_id: str):
        await self.get_brainstorm(user, brainstorm_id)
        return await self.repo.list_brainstorm_participants(brainstorm_id)

    async def list_brainstorm_messages(self, user: User, brainstorm_id: str):
        await self.get_brainstorm(user, brainstorm_id)
        return await self.repo.list_brainstorm_messages(brainstorm_id)

    async def start_brainstorm(self, user: User, brainstorm_id: str):
        await self._enforce_orchestration_run_rate_limit(user.id)
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status == "completed":
            raise HTTPException(status_code=409, detail="Brainstorm is already completed")
        current_round = self._brainstorm_current_round(brainstorm)
        if current_round >= brainstorm.max_rounds:
            raise HTTPException(status_code=409, detail="Brainstorm already reached the round limit")
        run = await self.repo.create_run(
            project_id=brainstorm.project_id,
            task_id=brainstorm.task_id,
            triggered_by_user_id=user.id,
            orchestrator_agent_id=brainstorm.moderator_agent_id,
            brainstorm_id=brainstorm.id,
            run_mode="brainstorm",
            status="queued",
            input_payload_json={"topic": brainstorm.topic, "target_round": current_round + 1},
        )
        brainstorm.status = "running"
        await self._emit_run_event(
            run,
            event_type="brainstorm_queued",
            message=f"Brainstorm round {current_round + 1} queued.",
        )
        from backend.modules.orchestration.durable_execution import submit_orchestration_run

        submit_orchestration_run(run.id)
        return run

    async def promote_brainstorm_to_tasks(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to promote")
        tasks: list[OrchestratorTask] = []
        for line in final_output.splitlines():
            cleaned = line.strip(" -0123456789.")
            if len(cleaned) < 6:
                continue
            tasks.append(
                await self.repo.create_task(
                    project_id=brainstorm.project_id,
                    created_by_user_id=user.id,
                    assigned_agent_id=None,
                    reviewer_agent_id=None,
                    title=cleaned[:255],
                    description=f"Generated from brainstorm {brainstorm.topic}",
                    source="brainstorm",
                    task_type="generated",
                    priority="normal",
                    status="backlog",
                    acceptance_criteria=None,
                    due_date=None,
                    labels_json=["brainstorm"],
                    result_payload_json={"brainstorm_output_type": self._brainstorm_output_type(brainstorm)},
                    metadata_json={"brainstorm_id": brainstorm.id, "promoted_from": "brainstorm"},
                    position=await self.repo.get_next_task_position(brainstorm.project_id),
                )
            )
        await self.db.commit()
        return tasks

    async def force_brainstorm_summary(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        if brainstorm.status == "completed":
            return brainstorm
        await self._finalize_brainstorm_output(brainstorm, reason="forced_summary")
        await self.db.commit()
        await self._decorate_brainstorms([brainstorm])
        return brainstorm

    async def promote_brainstorm_to_adr(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to promote")
        decision = await self.repo.create_project_decision(
            project_id=brainstorm.project_id,
            task_id=brainstorm.task_id,
            brainstorm_id=brainstorm.id,
            title=f"ADR: {brainstorm.topic[:240]}",
            decision=final_output,
            rationale=brainstorm.summary,
            author_label="Brainstorm",
        )
        await self.db.commit()
        await self.db.refresh(decision)
        return decision

    async def promote_brainstorm_to_document(self, user: User, brainstorm_id: str):
        brainstorm = await self.get_brainstorm(user, brainstorm_id)
        final_output = self._brainstorm_final_output(brainstorm)
        if not final_output:
            raise HTTPException(status_code=409, detail="Brainstorm has no finalized output to promote")
        item = await self.repo.create_document(
            project_id=brainstorm.project_id,
            task_id=brainstorm.task_id,
            uploaded_by_user_id=user.id,
            filename=f"{self._slugify(brainstorm.topic)}-{self._brainstorm_output_type(brainstorm)}.md"[:255],
            content_type="text/markdown",
            source_text=final_output,
            object_key=None,
            size_bytes=len(final_output.encode("utf-8")),
            summary_text=(brainstorm.summary or final_output[:500])[:2000],
            ingestion_status="pending",
            chunk_count=0,
            ttl_days=None,
            expires_at=None,
            metadata_json={
                "brainstorm_id": brainstorm.id,
                "source": "brainstorm",
                "source_kind": "brainstorm",
                "output_type": self._brainstorm_output_type(brainstorm),
            },
        )
        await self._index_project_document(item)
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def build_github_app_install_url(self, user: User) -> str:
        if not settings.GITHUB_APP_SLUG:
            raise HTTPException(status_code=503, detail="GitHub App is not configured")
        state_payload = f"{user.id}:{int(time.time())}"
        encoded_state = base64.urlsafe_b64encode(state_payload.encode("utf-8")).decode("utf-8").rstrip("=")
        return f"https://github.com/apps/{settings.GITHUB_APP_SLUG}/installations/new?state={encoded_state}"

    async def finalize_github_app_installation(
        self,
        user: User,
        *,
        installation_id: int,
        setup_action: str | None = None,
        api_url: str = "https://api.github.com",
    ) -> GithubConnection:
        installation = await self._github_app_get_installation(installation_id, api_url=api_url)
        account = installation.get("account") or {}
        account_login = account.get("login") or f"installation-{installation_id}"
        existing = await self.repo.get_github_connection_by_installation(user.id, installation_id)
        if existing:
            existing.name = f"{settings.GITHUB_APP_NAME} · {account_login}"
            existing.api_url = api_url
            existing.account_login = account_login
            existing.is_active = True
            existing.metadata_json = {
                **(existing.metadata_json or {}),
                "connection_mode": "github_app",
                "installation_id": installation_id,
                "account_login": account_login,
                "account_type": account.get("type"),
                "html_url": account.get("html_url"),
                "repositories_url": installation.get("repositories_url"),
                "setup_action": setup_action,
            }
            await self.db.commit()
            await self.db.refresh(existing)
            return existing
        item = await self.repo.create_github_connection(
            owner_id=user.id,
            name=f"{settings.GITHUB_APP_NAME} · {account_login}",
            api_url=api_url,
            encrypted_token=encrypt_secret("github-app-installation"),
            token_hint="app",
            account_login=account_login,
            metadata_json={
                "connection_mode": "github_app",
                "installation_id": installation_id,
                "account_login": account_login,
                "account_type": account.get("type"),
                "html_url": account.get("html_url"),
                "repositories_url": installation.get("repositories_url"),
                "setup_action": setup_action,
            },
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def create_github_connection(self, user: User, payload: dict[str, Any]):
        if payload.get("connection_mode") == "github_app":
            installation_id = payload.get("installation_id")
            if not installation_id:
                raise HTTPException(status_code=422, detail="installation_id is required for GitHub App connections")
            return await self.finalize_github_app_installation(
                user,
                installation_id=int(installation_id),
                setup_action=payload.get("setup_action"),
                api_url=payload.get("api_url", "https://api.github.com"),
            )
        token = payload.get("token")
        if not token:
            raise HTTPException(status_code=422, detail="token is required for legacy token connections")
        account_login = await self._fetch_github_login(payload["api_url"], payload["token"])
        item = await self.repo.create_github_connection(
            owner_id=user.id,
            name=payload["name"],
            api_url=payload.get("api_url", "https://api.github.com"),
            encrypted_token=encrypt_secret(payload["token"]),
            token_hint=mask_secret(payload["token"]),
            account_login=account_login,
            metadata_json={"connection_mode": "token"},
        )
        await self.db.commit()
        await self.db.refresh(item)
        return item

    async def list_github_connections(self, user: User):
        return await self.repo.list_github_connections(user.id)

    async def sync_github_repositories(self, user: User, connection_id: str):
        connection = await self.repo.get_github_connection(user.id, connection_id)
        if not connection:
            raise HTTPException(status_code=404, detail="GitHub connection not found")
        repos = await self._list_github_repositories(connection)
        created = []
        existing = {item.full_name: item for item in await self.repo.list_github_repositories(user.id)}
        for repo in repos:
            if repo["full_name"] in existing:
                continue
            created.append(
                await self.repo.create_github_repository(
                    connection_id=connection.id,
                    owner_name=repo["owner"]["login"],
                    repo_name=repo["name"],
                    full_name=repo["full_name"],
                    default_branch=repo.get("default_branch"),
                    repo_url=repo.get("html_url"),
                    metadata_json=repo,
                )
            )
        await self.db.commit()
        return created

    async def list_github_repositories(self, user: User):
        return await self.repo.list_github_repositories(user.id)

    async def import_github_issues(self, user: User, payload: dict[str, Any]):
        project = await self.get_project(user, payload["project_id"])
        repository = await self.repo.get_github_repository(user.id, payload["repository_id"])
        if not repository:
            raise HTTPException(status_code=404, detail="GitHub repository not found")
        repository.project_id = project.id
        connection = await self.repo.get_github_connection(user.id, repository.connection_id)
        if not connection:
            raise HTTPException(status_code=404, detail="GitHub connection not found")
        repo_pool = self._repo_pool_config(project, repository=repository)
        default_worker = str(
            payload.get("auto_assign_agent_id")
            or repo_pool.get("default_assignee_agent_id")
            or ""
        ).strip() or None
        default_reviewer = str(repo_pool.get("default_reviewer_agent_id") or "").strip() or None
        issues = await self._fetch_github_issues(connection, repository, payload.get("issue_numbers", []))
        results = []
        for issue in issues:
            link = await self.repo.get_issue_link_by_repo_and_number(repository.id, issue["number"])
            if link is None:
                link = await self.repo.create_issue_link(
                    repository_id=repository.id,
                    issue_number=issue["number"],
                    title=issue["title"],
                    body=issue.get("body"),
                    state=issue["state"],
                    labels_json=[item["name"] for item in issue.get("labels", [])],
                    assignee_login=(issue.get("assignee") or {}).get("login"),
                    issue_url=issue.get("html_url"),
                    last_synced_at=datetime.now(UTC),
                    metadata_json=issue,
                )
            if link.task_id is None:
                task = await self.repo.create_task(
                    project_id=project.id,
                    created_by_user_id=user.id,
                    assigned_agent_id=default_worker,
                    reviewer_agent_id=default_reviewer,
                    title=issue["title"][:255],
                    description=issue.get("body"),
                    source="github",
                    task_type="github_issue",
                    priority="normal",
                    status="backlog",
                    acceptance_criteria=None,
                    due_date=None,
                    labels_json=[item["name"] for item in issue.get("labels", [])],
                    result_payload_json={},
                    metadata_json={
                        "github_issue_number": issue["number"],
                        "github_milestone_number": ((issue.get("milestone") or {}).get("number")),
                    },
                    position=await self.repo.get_next_task_position(project.id),
                )
                link.task_id = task.id
                task.github_issue_link_id = link.id
                results.append(task)
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=link.id,
                action="import_issue",
                status="completed",
                detail=f"Issue #{issue['number']} imported.",
                payload_json={"issue_number": issue["number"]},
            )
        await self.db.commit()
        return results

    async def list_github_issue_links(self, user: User, project_id: str | None = None):
        return await self.repo.list_issue_links(user.id, project_id)

    async def list_github_sync_events(self, user: User, project_id: str | None = None):
        return await self.repo.list_sync_events(user.id, project_id)

    async def refresh_github_issue_link_from_api(self, link: GithubIssueLink) -> None:
        repository = await self.db.get(GithubRepository, link.repository_id)
        if repository is None:
            return
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None or not connection.is_active:
            return
        response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/issues/{link.issue_number}",
        )
        if response.status_code >= 400:
            link.last_error = response.text[:500]
            link.last_synced_at = datetime.now(UTC)
            return
        issue = response.json()
        link.title = (issue.get("title") or link.title)[:255]
        link.state = str(issue.get("state") or link.state)
        link.body = issue.get("body") or link.body
        link.labels_json = [item["name"] for item in issue.get("labels", []) if isinstance(item, dict)]
        assignee = issue.get("assignee") or {}
        link.assignee_login = assignee.get("login") if isinstance(assignee, dict) else None
        link.issue_url = issue.get("html_url") or link.issue_url
        link.metadata_json = {**(link.metadata_json or {}), "last_poll": issue}
        link.last_synced_at = datetime.now(UTC)
        link.last_error = None

    async def poll_stale_github_issue_links(self) -> int:
        """Background poll for issue state when webhooks are unavailable."""
        before = datetime.now(UTC) - timedelta(minutes=max(1, settings.GITHUB_ISSUE_POLL_INTERVAL_MINUTES))
        links = await self.repo.list_issue_links_stale(older_than=before, limit=50)
        updated = 0
        for link in links:
            try:
                await self.refresh_github_issue_link_from_api(link)
                updated += 1
            except Exception:
                link.last_error = "poll_failed"
                link.last_synced_at = datetime.now(UTC)
        if links:
            await self.db.commit()
        return updated

    async def sweep_expired_memory_globally(self) -> dict[str, int]:
        """Expire knowledge documents and agent memory rows past ``expires_at`` (all tenants)."""
        now = datetime.now(UTC)
        doc_result = await self.db.execute(
            update(ProjectDocument)
            .where(
                ProjectDocument.expires_at.isnot(None),
                ProjectDocument.expires_at <= now,
                ProjectDocument.deleted_at.is_(None),
            )
            .values(deleted_at=now)
        )
        mem_result = await self.db.execute(
            update(AgentMemoryEntry)
            .where(
                AgentMemoryEntry.expires_at.isnot(None),
                AgentMemoryEntry.expires_at <= now,
                AgentMemoryEntry.deleted_at.is_(None),
            )
            .values(deleted_at=now, status="expired")
        )
        await self.db.commit()
        return {
            "expired_documents": doc_result.rowcount or 0,
            "expired_memory_entries": mem_result.rowcount or 0,
        }

    async def create_github_comment_approval(
        self,
        user: User,
        issue_link_id: str,
        body: str,
        close_issue: bool,
    ):
        issue_link = await self.repo.get_issue_link(user.id, issue_link_id)
        if not issue_link:
            raise HTTPException(status_code=404, detail="Issue link not found")
        approval = await self.repo.create_approval(
            project_id=None,
            issue_link_id=issue_link.id,
            requested_by_user_id=user.id,
            approval_type="github_comment",
            status="pending",
            payload_json={"body": body, "close_issue": close_issue},
        )
        await self.db.commit()
        await self.db.refresh(approval)
        return approval

    async def list_approvals(self, user: User):
        return await self.repo.list_approvals(user.id)

    async def decide_approval(self, user: User, approval_id: str, status: str, reason: str | None):
        approval = await self.repo.get_approval(user.id, approval_id)
        if not approval:
            raise HTTPException(status_code=404, detail="Approval request not found")
        if status == "rejected" and not str(reason or "").strip():
            raise HTTPException(status_code=422, detail="A rejection reason is required.")
        approval.status = status
        approval.reason = reason
        approval.approved_by_user_id = user.id
        approval.resolved_at = datetime.now(UTC)
        if status == "approved" and approval.approval_type in {
            "github_comment",
            "github_progress_comment",
            "github_manager_closure",
        } and approval.issue_link_id:
            await self._post_approved_github_comment(approval)
        elif status == "approved" and approval.approval_type == "github_create_pr":
            await self._approve_github_create_pr(approval)
        elif status == "approved" and approval.approval_type == "github_pr_review_comment":
            await self._approve_github_pr_review_comment(approval)
        elif status == "approved" and approval.approval_type == "github_issue_sync":
            await self._approve_github_issue_sync(approval)
        elif approval.approval_type == "agent_memory_write":
            memory_entry_id = (approval.payload_json or {}).get("memory_entry_id")
            if memory_entry_id:
                memory = await self.repo.get_agent_memory(user.id, memory_entry_id)
                if memory:
                    if status == "approved":
                        memory.status = "approved"
                        memory.approved_by_user_id = user.id
                        if memory.project_id:
                            proj = await self.db.get(OrchestratorProject, memory.project_id)
                            if proj:
                                await self._maybe_promote_agent_memory_to_semantic(user, proj, memory)
                    else:
                        memory.status = "rejected"
                        memory.deleted_at = datetime.now(UTC)
        elif approval.approval_type == "semantic_memory_write":
            payload = approval.payload_json or {}
            op = payload.get("operation")
            req_user_id = approval.requested_by_user_id or user.id
            req_user = await self.db.get(User, req_user_id) or user
            if approval.project_id and status == "approved":
                project = await self.get_project(req_user, approval.project_id)
                if op == "create":
                    await self._persist_semantic_memory_row(
                        req_user, project, dict(payload.get("payload") or {})
                    )
                elif op == "update":
                    entry_id = str(payload.get("entry_id") or "")
                    updates = dict(payload.get("updates") or {})
                    entry = await self.get_semantic_memory_entry_for_project(
                        req_user, approval.project_id, entry_id
                    )
                    await self._apply_semantic_entry_updates(entry, updates)
                    await self.db.commit()
                    await self.db.refresh(entry)
                    self._schedule_semantic_embedding(entry.id)
                elif op == "delete":
                    entry_id = str(payload.get("entry_id") or "")
                    entry = await self.get_semantic_memory_entry_for_project(
                        req_user, approval.project_id, entry_id
                    )
                    await self.db.delete(entry)
                    await self.db.commit()
        elif approval.approval_type == "task_assignment_change":
            if status == "approved" and approval.task_id:
                task = await self.db.get(OrchestratorTask, approval.task_id)
                if task:
                    payload = approval.payload_json or {}
                    task.assigned_agent_id = payload.get("to_assigned_agent_id")
        elif approval.approval_type == "task_mark_complete":
            if status == "approved" and approval.task_id:
                task = await self.db.get(OrchestratorTask, approval.task_id)
                if task:
                    payload = approval.payload_json or {}
                    target_status = str(payload.get("to_status") or "completed")
                    if target_status not in TASK_STATUS_VALUES:
                        target_status = "completed"
                    await self._transition_task_status(
                        task,
                        target_status,
                        reason="approval granted for task completion",
                    )
        elif approval.approval_type == "shared_memory_write":
            if status == "approved" and approval.task_id:
                task = await self.db.get(OrchestratorTask, approval.task_id)
                if task:
                    payload = approval.payload_json or {}
                    meta = dict(task.metadata_json or {})
                    cur = dict(meta.get(MEMORY_COORDINATION_KEY) or {})
                    cur["shared"] = str(payload.get("shared") or "")
                    meta[MEMORY_COORDINATION_KEY] = cur
                    task.metadata_json = meta
        elif status == "approved" and approval.run_id:
            # Approved actions unblock the task run
            run = await self.db.get(TaskRun, approval.run_id)
            if run and run.status == "blocked":
                run.status = "in_progress"
                await self._emit_run_event(
                    run,
                    event_type="unblocked",
                    level="info",
                    message="Run unblocked by human approval.",
                    payload={"approval_id": approval.id, "reason": reason},
                )
        elif status == "rejected" and approval.task_id:
            task = await self.db.get(OrchestratorTask, approval.task_id)
            if task and task.status in {"approved", "completed"}:
                await self._transition_task_status(
                    task,
                    "planned",
                    reason="approval rejected, reopening work",
                )
            # Rejected approvals trigger re-plan
            if approval.run_id:
                run = await self.db.get(TaskRun, approval.run_id)
                if run and run.status not in {"completed", "failed", "cancelled"}:
                    run.status = "failed"
                    run.error_message = f"Approval rejected: {reason or 'No reason provided'}"
                    await self._emit_run_event(
                        run,
                        event_type="approval_rejected",
                        level="warning",
                        message=f"Run marked as failed due to rejected approval: {reason or 'No reason provided'}",
                        payload={"approval_id": approval.id, "reason": reason},
                    )
                    if task:
                        await self._transition_task_status(
                            task,
                            "planned",
                            run=run,
                            reason="re-plan triggered by rejected approval",
                        )
        await self.audit_repo.log(
            actor_user_id=user.id,
            action_type=f"orchestration.approval.{status}",
            entity_type="approval_request",
            entity_id=approval.id,
            metadata_json={
                "approval_type": approval.approval_type,
                "project_id": approval.project_id,
                "task_id": approval.task_id,
                "run_id": approval.run_id,
                "reason": reason,
            },
        )
        await self.db.commit()
        await self.db.refresh(approval)
        return approval

    async def get_pending_approvals_count(self, user: User) -> int:
        """Return the count of pending approvals for the user."""
        approvals = await self.repo.list_approvals(user.id, status="pending")
        return len(approvals)

    def action_requires_approval(
        self,
        project: OrchestratorProject,
        action_type: str,
    ) -> bool:
        """Check if an action type requires approval based on project gate config.

        If the project autonomy_level is 'autonomous', all gates are short-circuited.
        Otherwise, checks if the action_type is in the project's approval_gates list.
        """
        settings = self._project_execution_settings(project)
        autonomy_level = settings.get("autonomy_level", "assisted")

        # Autonomous mode short-circuits all gates
        if autonomy_level == "autonomous":
            return False

        approval_gates = settings.get("approval_gates", [])
        return action_type in approval_gates

    async def upload_document(
        self,
        user: User,
        project_id: str,
        task_id: str | None,
        file: UploadFile,
        *,
        ttl_days: int | None = None,
    ):
        await self.get_project(user, project_id)
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded document is empty")
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(status_code=400, detail="Document must be UTF-8 text") from exc
        object_key = None
        if object_storage.is_configured:
            suffix = Path(file.filename or "document.md").name
            object_key = f"orchestration/{project_id}/{datetime.now(UTC).timestamp()}-{suffix}"
            await object_storage.upload_bytes(
                object_key=object_key,
                body=payload,
                content_type=file.content_type or "text/markdown",
            )
        item = await self.repo.create_document(
            project_id=project_id,
            task_id=task_id,
            uploaded_by_user_id=user.id,
            filename=file.filename or "document.md",
            content_type=file.content_type or "text/markdown",
            source_text=content,
            object_key=object_key,
            size_bytes=len(payload),
            summary_text=content[:500],
            ingestion_status="pending",
            chunk_count=0,
            ttl_days=ttl_days,
            expires_at=(datetime.now(UTC) + timedelta(days=ttl_days)) if ttl_days else None,
            metadata_json={"source_kind": "uploaded"},
        )
        await self.repo.create_memory_ingest_job(
            owner_id=user.id,
            project_id=project_id,
            job_type="document_ingest",
            payload_json={"project_id": project_id, "document_id": item.id},
            status="pending",
        )
        await self.db.commit()
        try:
            from backend.workers.orchestration import queue_memory_ingest_jobs

            queue_memory_ingest_jobs()
        except Exception as exc:
            logger.warning("queue memory ingest jobs failed for upload_document: %s", exc)
        await self.db.refresh(item)
        return item

    async def list_documents(self, user: User, project_id: str, task_id: str | None = None):
        await self.get_project(user, project_id)
        await self._expire_project_memory(project_id)
        return await self.repo.list_documents(project_id, task_id)

    async def delete_document(self, user: User, project_id: str, document_id: str) -> None:
        await self.get_project(user, project_id)
        item = await self.repo.get_document(project_id, document_id)
        if not item:
            raise HTTPException(status_code=404, detail="Document not found")
        item.deleted_at = datetime.now(UTC)
        item.updated_at = datetime.now(UTC)
        await self.db.commit()

    async def search_project_knowledge(
        self,
        user: User,
        project_id: str,
        query: str,
        *,
        task_id: str | None = None,
        top_k: int = 5,
        source_kind: str | None = None,
        include_decisions: bool = False,
    ) -> list[dict[str, Any]]:
        await self.get_project(user, project_id)
        return await self._search_project_knowledge(
            project_id,
            query,
            task_id=task_id,
            top_k=top_k,
            source_kind=source_kind,
            include_decisions=include_decisions,
        )

    async def _search_project_knowledge(
        self,
        project_id: str,
        query: str,
        *,
        task_id: str | None = None,
        top_k: int = 5,
        source_kind: str | None = None,
        include_decisions: bool = False,
    ) -> list[dict[str, Any]]:
        """Semantic / RAG retrieval only.

        Results may enrich prompts but must never determine run lifecycle, task status
        transitions, or approval outcomes. Authoritative execution state is relational;
        see ``execution_state`` and the task/run execution-snapshot read APIs.
        """
        await self._expire_project_memory(project_id)
        cap = max(1, min(top_k, 20))
        query_embedding = (await self.ai_providers.embed_texts([query]))[0]
        try:
            vector_hits = await self.repo.search_document_chunks_by_vector(
                project_id,
                query_embedding,
                task_id=task_id,
                source_kind=source_kind,
                top_k=top_k,
            )
        except Exception:
            vector_hits = []
        merged: list[dict[str, Any]] = []
        if vector_hits:
            merged = [
                {
                    "hit_kind": "chunk",
                    "document_id": row["project_document_id"],
                    "chunk_id": row["chunk_id"],
                    "filename": row["filename"],
                    "chunk_index": row["chunk_index"],
                    "score": round(float(row["score"]), 4),
                    "content": row["content"],
                    "metadata": row["metadata_json"] or {},
                    "decision_id": None,
                }
                for row in vector_hits[:cap]
            ]
        else:
            chunks = await self.repo.list_document_chunks(project_id, task_id=task_id, source_kind=source_kind)
            if not chunks and not include_decisions:
                return []
            documents = {item.id: item for item in await self.repo.list_documents(project_id, task_id)}
            for chunk in chunks:
                doc = documents.get(chunk.project_document_id)
                if doc is None:
                    continue
                merged.append(
                    {
                        "hit_kind": "chunk",
                        "document_id": doc.id,
                        "chunk_id": chunk.id,
                        "filename": doc.filename,
                        "chunk_index": chunk.chunk_index,
                        "score": round(_cosine_similarity(query_embedding, chunk.embedding_json), 4),
                        "content": chunk.content,
                        "metadata": chunk.metadata_json or {},
                        "decision_id": None,
                    }
                )
            merged.sort(key=lambda item: item["score"], reverse=True)
            merged = merged[:cap]

        if include_decisions:
            decisions = await self.repo.list_project_decisions(project_id)
            dec_hits: list[dict[str, Any]] = []
            for d in decisions[:300]:
                title = d.title or ""
                body = d.decision or ""
                sc = self._decision_text_relevance_score(query, title, body)
                if sc <= 0 and query.strip():
                    continue
                dec_hits.append(
                    {
                        "hit_kind": "decision",
                        "document_id": d.id,
                        "chunk_id": d.id,
                        "filename": "decision",
                        "chunk_index": 0,
                        "score": round(float(sc), 4),
                        "content": "\n".join(x for x in [title, body, (d.rationale or "")] if x),
                        "metadata": {
                            "title": title,
                            "rationale": d.rationale,
                            "author_label": d.author_label,
                        },
                        "decision_id": d.id,
                    }
                )
            dec_hits.sort(key=lambda item: item["score"], reverse=True)
            merged = sorted([*merged, *dec_hits[:cap]], key=lambda item: item["score"], reverse=True)[:cap]

        return merged

    async def list_project_memory(
        self,
        user: User,
        project_id: str,
        *,
        agent_id: str | None = None,
        status: str | None = None,
    ) -> list[AgentMemoryEntry]:
        await self.get_project(user, project_id)
        await self._expire_project_memory(project_id)
        return await self.repo.list_agent_memory(
            user.id,
            project_id=project_id,
            agent_id=agent_id,
            status=status,
        )

    async def delete_memory_entry(self, user: User, project_id: str, memory_id: str) -> None:
        await self.get_project(user, project_id)
        entry = await self.repo.get_agent_memory(user.id, memory_id)
        if entry is None or entry.project_id != project_id:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        entry.deleted_at = datetime.now(UTC)
        entry.status = "deleted"
        await self.db.commit()

    async def list_agent_templates(self) -> list[dict]:
        await self._ensure_catalog_seeded()
        templates = await self.repo.list_agent_templates()
        return [self._template_model_to_payload(item) for item in templates]

    async def create_agent_template(self, payload: dict) -> dict:
        data = {
            "slug": payload["slug"],
            "name": payload["name"],
            "role": payload.get("role", "specialist"),
            "description": payload.get("description"),
            "parent_template_slug": payload.get("parent_template_slug"),
            "system_prompt": payload.get("system_prompt", ""),
            "mission_markdown": payload.get("mission_markdown", ""),
            "rules_markdown": payload.get("rules_markdown", ""),
            "output_contract_markdown": payload.get("output_contract_markdown", ""),
            "capabilities_json": payload.get("capabilities", []),
            "allowed_tools_json": payload.get("allowed_tools", []),
            "skills_json": payload.get("skills", []),
            "tags_json": payload.get("tags", []),
            "model_policy_json": payload.get("model_policy", {}),
            "budget_json": payload.get("budget", {}),
            "memory_policy_json": payload.get("memory_policy", {}),
            "output_schema_json": payload.get("output_schema", {}),
            "metadata_json": payload.get("metadata", {}),
        }
        template = await self.repo.create_agent_template(**data)
        await self.db.commit()
        await self.db.refresh(template)
        return self._template_model_to_payload(template)

    async def update_agent_template(self, slug: str, payload: dict) -> dict:
        template = await self.repo.get_agent_template_by_slug(slug)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
        if "slug" in payload and payload["slug"] != slug:
            existing = await self.repo.get_agent_template_by_slug(payload["slug"])
            if existing is not None:
                raise HTTPException(status_code=409, detail="Template slug already exists")
        field_map = {
            "slug": "slug",
            "name": "name",
            "role": "role",
            "description": "description",
            "parent_template_slug": "parent_template_slug",
            "system_prompt": "system_prompt",
            "mission_markdown": "mission_markdown",
            "rules_markdown": "rules_markdown",
            "output_contract_markdown": "output_contract_markdown",
            "capabilities": "capabilities_json",
            "allowed_tools": "allowed_tools_json",
            "skills": "skills_json",
            "tags": "tags_json",
            "model_policy": "model_policy_json",
            "budget": "budget_json",
            "memory_policy": "memory_policy_json",
            "output_schema": "output_schema_json",
            "metadata": "metadata_json",
        }
        for key, value in payload.items():
            target = field_map.get(key)
            if target is not None:
                setattr(template, target, value)
        await self.db.commit()
        await self.db.refresh(template)
        return self._template_model_to_payload(template)

    async def delete_agent_template(self, slug: str) -> None:
        template = await self.repo.get_agent_template_by_slug(slug)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{slug}' not found")
        await self.db.delete(template)
        await self.db.commit()

    async def list_skill_catalog(self) -> list[dict[str, Any]]:
        await self._ensure_catalog_seeded()
        skills = await self.repo.list_skill_packs()
        return [self._skill_model_to_payload(item) for item in skills]

    async def create_skill_pack(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        existing = await self.repo.get_skill_pack_by_slug(payload["slug"])
        if existing is not None:
            raise HTTPException(status_code=409, detail="Skill slug already exists")
        skill = await self.repo.create_skill_pack(
            slug=payload["slug"],
            name=payload["name"],
            description=payload.get("description"),
            capabilities_json=payload.get("capabilities", []),
            allowed_tools_json=payload.get("allowed_tools", []),
            rules_markdown=payload.get("rules_markdown", ""),
            tags_json=payload.get("tags", []),
        )
        await self.db.commit()
        await self.db.refresh(skill)
        return self._skill_model_to_payload(skill)

    async def update_skill_pack(self, slug: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        skill = await self.repo.get_skill_pack_by_slug(slug)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
        field_map = {
            "name": "name",
            "description": "description",
            "capabilities": "capabilities_json",
            "allowed_tools": "allowed_tools_json",
            "rules_markdown": "rules_markdown",
            "tags": "tags_json",
        }
        for key, value in payload.items():
            target = field_map.get(key)
            if target is not None:
                setattr(skill, target, value)
        await self.db.commit()
        await self.db.refresh(skill)
        return self._skill_model_to_payload(skill)

    async def delete_skill_pack(self, slug: str) -> None:
        await self._ensure_catalog_seeded()
        skill = await self.repo.get_skill_pack_by_slug(slug)
        if skill is None:
            raise HTTPException(status_code=404, detail=f"Skill '{slug}' not found")
        await self.db.delete(skill)
        await self.db.commit()

    async def list_team_templates(self) -> list[dict[str, Any]]:
        await self._ensure_team_template_catalog_seeded()
        items = await self.repo.list_team_templates()
        return [self._team_template_model_to_payload(item) for item in items]

    async def create_team_template(self, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_team_template_catalog_seeded()
        existing = await self.repo.get_team_template_by_slug(payload["slug"])
        if existing is not None:
            raise HTTPException(status_code=409, detail="Team template slug already exists")
        item = await self.repo.create_team_template(
            slug=payload["slug"],
            name=payload["name"],
            description=payload.get("description"),
            outcome=payload.get("outcome", ""),
            roles_json=payload.get("roles", []),
            tools_json=payload.get("tools", []),
            autonomy=payload.get("autonomy", "medium"),
            visibility=payload.get("visibility", "private"),
            agent_template_slugs_json=payload.get("agent_template_slugs", []),
        )
        await self.db.commit()
        await self.db.refresh(item)
        return self._team_template_model_to_payload(item)

    async def update_team_template(self, template_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        await self._ensure_team_template_catalog_seeded()
        item = await self.repo.get_team_template(template_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Team template not found")
        field_map = {
            "name": "name",
            "description": "description",
            "outcome": "outcome",
            "roles": "roles_json",
            "tools": "tools_json",
            "autonomy": "autonomy",
            "visibility": "visibility",
            "agent_template_slugs": "agent_template_slugs_json",
        }
        for key, value in payload.items():
            target = field_map.get(key)
            if target is not None:
                setattr(item, target, value)
        await self.db.commit()
        await self.db.refresh(item)
        return self._team_template_model_to_payload(item)

    async def delete_team_template(self, template_id: str) -> None:
        await self._ensure_team_template_catalog_seeded()
        item = await self.repo.get_team_template(template_id)
        if item is None:
            raise HTTPException(status_code=404, detail="Team template not found")
        await self.db.delete(item)
        await self.db.commit()

    async def create_agent_from_template(
        self, user: User, template_slug: str, overrides: dict[str, Any]
    ) -> AgentProfile:
        await self._ensure_catalog_seeded()
        template = await self.repo.get_agent_template_by_slug(template_slug)
        if not template:
            raise HTTPException(status_code=404, detail=f"Template '{template_slug}' not found")
        payload = {
            **self._template_model_to_payload(template),
            **{k: v for k, v in overrides.items() if v is not None},
        }
        payload["slug"] = overrides.get("slug") or template.slug
        payload["name"] = overrides.get("name") or template.name
        payload["parent_template_slug"] = overrides.get("parent_template_slug") or template.parent_template_slug or template.slug
        payload["metadata"] = {
            **payload.get("metadata", {}),
            "from_template": template_slug,
        }
        payload = await self._validate_and_normalize_agent_payload(user, payload, existing_agent_id=None)
        payload["is_active"] = bool(payload.get("is_active", False))
        await self._ensure_unique_agent_slug(user.id, payload["slug"], None)
        agent = await self.repo.create_agent(owner_id=user.id, **self._agent_payload_to_model(payload))
        await self._snapshot_agent(agent, user.id)
        await self.audit_repo.log(
            "orchestration.agent.created_from_template",
            user_id=user.id,
            resource_type="agent",
            resource_id=agent.id,
            metadata={"template_slug": template_slug},
        )
        await self.db.commit()
        await self.db.refresh(agent)
        return agent

    async def test_run_agent(
        self, user: User, agent_id: str, payload: dict[str, Any]
    ) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        agent = await self.get_agent(user, agent_id)
        inheritance = await self.resolve_agent_inheritance(agent)
        provider_config_id = payload.get("provider_config_id")
        provider = None
        if provider_config_id:
            provider = await self.db.get(ProviderConfig, provider_config_id)
        elif agent.provider_config_id:
            provider = await self.db.get(ProviderConfig, agent.provider_config_id)
        else:
            providers = await self.repo.list_providers(user.id, agent.project_id)
            provider = next((p for p in providers if p.is_default), None) or (providers[0] if providers else None)

        model_name = payload.get("model_name") or (provider.default_model if provider else None)
        task_prompt_parts = [f"Task title: {payload.get('task_title', 'Test task')}"]
        if payload.get("task_description"):
            task_prompt_parts.append(f"Task description: {payload['task_description']}")
        if payload.get("acceptance_criteria"):
            task_prompt_parts.append(f"Acceptance criteria: {payload['acceptance_criteria']}")
        if payload.get("task_labels"):
            task_prompt_parts.append(f"Task labels: {payload['task_labels']}")
        if payload.get("task_metadata"):
            task_prompt_parts.append(f"Task metadata: {json.dumps(payload['task_metadata'], indent=2)}")
        base_prompt = "\n\n".join(task_prompt_parts)

        trace: list[dict[str, Any]] = [
            {"step": "build_prompt", "message": "Built dry-run task prompt.", "payload": {"chars": len(base_prompt)}},
        ]
        tool_calls = (payload.get("task_metadata") or {}).get("tool_calls", [])
        simulated_tool_results = [
            {
                "tool": call.get("tool"),
                "status": "simulated",
                "result": {"dry_run": True, "arguments": call.get("arguments", {})},
            }
            for call in tool_calls
            if isinstance(call, dict)
        ]
        if simulated_tool_results:
            trace.append(
                {
                    "step": "simulate_tools",
                    "message": "Simulated configured tool calls without side effects.",
                    "payload": {"tool_count": len(simulated_tool_results)},
                }
            )
        final_prompt = "\n\n".join(
            [
                base_prompt,
                "This is a dry-run test. Do not perform external side effects.",
                f"Simulated tool results:\n{json.dumps(simulated_tool_results, indent=2)}" if simulated_tool_results else "",
            ]
        )
        trace.append(
            {
                "step": "model_request",
                "message": f"Sending dry-run request to model ({model_name or 'local'}).",
                "payload": {"model_name": model_name},
            }
        )
        _, result = await self._execute_with_routing(
            None,
            provider=provider,
            agent=agent,
            system_prompt=inheritance["effective"].get("system_prompt") or agent.system_prompt or "You are a helpful software agent.",
            user_prompt=final_prompt,
            purpose="agent dry-run",
            append_metrics=False,
        )
        trace.append(
            {
                "step": "model_response",
                "message": "Received dry-run response.",
                "payload": {
                    "input_tokens": result.input_tokens,
                    "output_tokens": result.output_tokens,
                    "latency_ms": result.latency_ms,
                },
            }
        )
        budget = inheritance["effective"].get("budget") or agent.budget_json or {}
        token_budget = budget.get("token_budget")
        if token_budget and result.total_tokens > int(token_budget):
            trace.append(
                {
                    "step": "budget_check",
                    "level": "warning",
                    "message": f"Token budget ({token_budget}) exceeded.",
                    "payload": {"token_budget": token_budget, "used": result.total_tokens},
                }
            )

        cost_usd = self._estimate_cost_micros(
            provider, result.input_tokens, result.output_tokens, model_name=result.model_name
        ) / 1_000_000

        return {
            "agent_id": agent.id,
            "agent_name": agent.name,
            "model_used": result.model_name,
            "input_tokens": result.input_tokens,
            "output_tokens": result.output_tokens,
            "token_total": result.total_tokens,
            "latency_ms": result.latency_ms,
            "estimated_cost_usd": cost_usd,
            "output_text": result.output_text,
            "trace": trace,
            "simulated_tool_results": simulated_tool_results,
            "inheritance": inheritance,
        }

    def _estimate_cost_micros(
        self,
        provider: ProviderConfig | None,
        input_tokens: int,
        output_tokens: int,
        *,
        model_name: str | None = None,
    ) -> int:
        capability = None
        if model_name:
            capability = next(
                (
                    item
                    for item in getattr(self, "_cached_model_capabilities", [])
                    if item.model_slug == model_name
                    and (provider is None or item.provider_type in {provider.provider_type, "openai_compatible"})
                ),
                None,
            )
        if capability:
            cost_in = float(capability.cost_per_1k_input)
            cost_out = float(capability.cost_per_1k_output)
        elif provider and provider.metadata_json:
            cost_in = float(provider.metadata_json.get("cost_per_1k_input", 1.0))
            cost_out = float(provider.metadata_json.get("cost_per_1k_output", 2.0))
        else:
            cost_in, cost_out = 1.0, 2.0
        micros = int((input_tokens / 1000.0 * cost_in + output_tokens / 1000.0 * cost_out) * 1_000_000)
        return micros

    async def _model_capabilities(self) -> list[ModelCapability]:
        items = await self.repo.list_model_capabilities()
        self._cached_model_capabilities = items
        return items

    async def _model_capability(self, model_name: str, provider_type: str | None = None) -> ModelCapability | None:
        items = await self._model_capabilities()
        for item in items:
            if item.model_slug != model_name:
                continue
            if provider_type is None or item.provider_type == provider_type:
                return item
        return None

    def _normalize_discovered_models(self, models: list[dict[str, Any]]) -> list[dict[str, Any]]:
        normalized: list[dict[str, Any]] = []
        for item in models:
            name = str(item.get("name") or item.get("model") or "").strip()
            if not name:
                continue
            normalized.append(
                {
                    "name": name,
                    "size": item.get("size"),
                    "modified_at": item.get("modified_at"),
                    "digest": item.get("digest"),
                    "details": item.get("details") or {},
                }
            )
        return normalized

    async def _refresh_provider_models(self, provider: ProviderConfig) -> list[dict[str, Any]]:
        try:
            models = await list_provider_models(provider)
        except Exception:
            if provider.provider_type == "ollama":
                provider.metadata_json = {
                    **(provider.metadata_json or {}),
                    "discovered_models": [],
                }
            raise
        normalized = self._normalize_discovered_models(models)
        provider.metadata_json = {
            **(provider.metadata_json or {}),
            "discovered_models": normalized,
        }
        if provider.provider_type == "ollama":
            existing = {
                item.model_slug for item in await self.repo.list_model_capabilities("ollama", active_only=False)
            }
            for item in normalized:
                if item["name"] in existing:
                    continue
                await self.repo.create_model_capability(
                    provider_type="ollama",
                    model_slug=item["name"],
                    display_name=item["name"],
                    supports_tools=False,
                    supports_vision=False,
                    max_context_tokens=8192,
                    cost_per_1k_input=0.0,
                    cost_per_1k_output=0.0,
                    metadata_json={"source": "discovered"},
                    is_active=True,
                )
        return normalized

    async def _provider_model_exists(self, provider: ProviderConfig, model_name: str | None) -> bool:
        if not model_name:
            return True
        if model_name in {provider.default_model, provider.fallback_model}:
            return True
        capability = await self._model_capability(model_name, provider.provider_type)
        if capability:
            return True
        discovered = {
            str(item.get("name") or "").strip()
            for item in (provider.metadata_json or {}).get("discovered_models", [])
        }
        return model_name in discovered

    async def _validate_provider_models(self, provider: ProviderConfig) -> None:
        if not await self._provider_model_exists(provider, provider.default_model):
            raise HTTPException(
                status_code=422,
                detail=f"Default model '{provider.default_model}' is not available for provider type '{provider.provider_type}'.",
            )
        if provider.fallback_model and not await self._provider_model_exists(provider, provider.fallback_model):
            raise HTTPException(
                status_code=422,
                detail=f"Fallback model '{provider.fallback_model}' is not available for provider type '{provider.provider_type}'.",
            )

    async def _healthcheck_provider(self, provider: ProviderConfig) -> dict[str, Any]:
        if provider.provider_type == "ollama":
            try:
                await self._refresh_provider_models(provider)
            except Exception:
                pass
        checked_at = datetime.now(UTC)
        try:
            result = await test_provider(provider)
            provider.last_healthcheck_status = result["status"]
            provider.last_healthcheck_latency_ms = int(result["latency_ms"])
            provider.last_healthcheck_at = checked_at
            provider.is_healthy = True
            provider.metadata_json = {
                **(provider.metadata_json or {}),
                "last_discovery_error": None,
            }
            provider.updated_at = checked_at
            return result
        except Exception as exc:
            provider.last_healthcheck_status = "unhealthy"
            provider.last_healthcheck_latency_ms = None
            provider.last_healthcheck_at = checked_at
            provider.is_healthy = False
            provider.metadata_json = {
                **(provider.metadata_json or {}),
                "last_healthcheck_error": str(exc),
            }
            provider.updated_at = checked_at
            return {"status": "unhealthy", "error": str(exc), "latency_ms": None}

    async def run_provider_health_checks(self) -> list[dict[str, Any]]:
        await self._ensure_catalog_seeded()
        providers = await self.repo.list_all_providers(enabled_only=True)
        results: list[dict[str, Any]] = []
        for provider in providers:
            result = await self._healthcheck_provider(provider)
            results.append({"provider_id": provider.id, "provider_name": provider.name, **result})
        await self.db.commit()
        return results

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

    async def _execute_single_agent_run(self, run: TaskRun) -> None:
        agent = await self._load_agent_for_run(run.worker_agent_id or run.orchestrator_agent_id)
        provider = await self._resolve_provider_for_run(run, agent)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        prompt = self._workflow_checkpoint_artifact(run, "single_agent.prompt")
        if not isinstance(prompt, str) or not prompt.strip():
            await self._mark_run_step(
                run,
                step_id="build_prompt",
                status="in_progress",
                message="Building task prompt.",
            )
            await self._emit_run_event(run, event_type="prompt_building", message="Building task prompt...")
            prompt = await self._build_task_prompt(run, agent)
            self._set_workflow_checkpoint_artifact(run, key="single_agent.prompt", value=prompt)
            await self._mark_run_step(
                run,
                step_id="build_prompt",
                status="completed",
                message="Task prompt checkpoint saved.",
            )

        execution_plan = self._workflow_checkpoint_artifact(run, "single_agent.plan")
        if not isinstance(execution_plan, dict) or not execution_plan:
            await self._mark_run_step(
                run,
                step_id="plan_execution",
                status="in_progress",
                message="Planning single-agent execution.",
            )
            execution_plan = await self._plan_agent_execution(
                run,
                provider=provider,
                agent=agent,
                prompt=prompt,
                purpose="single-agent task execution",
            )
            self._set_workflow_checkpoint_artifact(run, key="single_agent.plan", value=execution_plan)
            await self._mark_run_step(
                run,
                step_id="plan_execution",
                status="completed",
                message="Execution plan checkpoint saved.",
                metadata={"tool_call_count": len(execution_plan.get("tool_calls", []))},
            )

        tool_results = self._workflow_checkpoint_artifact(run, "single_agent.tool_results")
        if not isinstance(tool_results, list):
            await self._mark_run_step(
                run,
                step_id="run_tools",
                status="in_progress",
                message="Executing planned tools.",
            )
            tool_results = await self._execute_tool_calls(
                run,
                project=project,
                task=task,
                tool_calls=execution_plan.get("tool_calls", []),
                allowed_tools=(agent.allowed_tools_json if agent else []),
                agent=agent,
            )
            self._set_workflow_checkpoint_artifact(
                run, key="single_agent.tool_results", value=tool_results
            )
            await self._mark_run_step(
                run,
                step_id="run_tools",
                status="completed",
                message="Tool results checkpoint saved.",
                metadata={"completed_tools": len(tool_results)},
            )

        final_prompt = self._build_final_prompt(
            base_prompt=prompt,
            execution_plan=execution_plan,
            tool_results=tool_results,
        )
        model_name = run.model_name or (provider.default_model if provider else None)
        await self._mark_run_step(
            run,
            step_id="model_response",
            status="in_progress",
            message=f"Requesting model response ({model_name or 'default'}).",
        )
        await self._emit_run_event(
            run,
            event_type="llm_request",
            message=f"Sending request to model ({model_name or 'default'})...",
            payload={"prompt_chars": len(final_prompt), "tool_calls": len(tool_results)},
        )
        provider, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=agent,
            system_prompt=agent.system_prompt if agent else "You are a helpful software agent.",
            user_prompt=final_prompt,
            purpose="single-agent execution",
            response_format=self._structured_output_response_format(agent),
        )
        run.output_payload_json = {
            "plan": execution_plan,
            "tool_results": tool_results,
            "summary": result.output_text[:1200],
            "final_output": result.output_text,
            "structured_output_json": result.output_json,
        }
        self._set_workflow_checkpoint_artifact(
            run,
            key="single_agent.output_payload",
            value=run.output_payload_json,
        )
        await self._mark_run_step(
            run,
            step_id="model_response",
            status="completed",
            message="Model response checkpoint saved.",
            metadata={"output_chars": len(result.output_text)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="in_progress",
            message="Persisting execution artifacts.",
        )
        await self._write_artifact(
            run,
            kind="run_output",
            title="Execution output",
            content=result.output_text,
            metadata={"tool_calls": len(tool_results)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="completed",
            message="Execution artifacts persisted.",
        )

    async def _execute_manager_worker_run(self, run: TaskRun) -> None:
        manager = await self._load_agent_for_run(run.orchestrator_agent_id)
        explicit_worker = await self._load_agent_for_run(run.worker_agent_id)
        if manager and explicit_worker and not self._delegation_edge_allowed(manager, explicit_worker):
            raise RuntimeError(
                "Manager cannot delegate to the selected worker (hierarchy or delegation_rules allowlist)."
            )
        provider = await self._resolve_provider_for_run(run, explicit_worker or manager)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        await self._emit_run_event(
            run,
            event_type="manager_planning",
            message="Manager agent building execution graph...",
        )
        manager_plan = self._workflow_checkpoint_artifact(run, "manager_worker.plan")
        routed_sub_tasks = self._workflow_checkpoint_artifact(run, "manager_worker.routed_sub_tasks")
        branch_results = self._workflow_checkpoint_artifact(run, "manager_worker.branch_results")

        if not isinstance(manager_plan, dict) or not manager_plan:
            await self._mark_run_step(
                run,
                step_id="supervisor_plan",
                status="in_progress",
                message="Supervisor is planning delegated work.",
            )
            planning_prompt = await self._build_task_prompt(
                run,
                manager,
                prefix=(
                    "Produce a JSON execution graph with sub_tasks, required_tools, required_capabilities, "
                    "and whether each branch can run in parallel."
                ),
            )
            manager_plan = await self._plan_agent_execution(
                run,
                provider=provider,
                agent=manager,
                prompt=planning_prompt,
                purpose="manager delegation graph",
                default_tool_calls=[],
            )
            self._set_workflow_checkpoint_artifact(run, key="manager_worker.plan", value=manager_plan)
            await self._mark_run_step(
                run,
                step_id="supervisor_plan",
                status="completed",
                message="Supervisor plan checkpoint saved.",
                metadata={"sub_task_count": len(manager_plan.get("sub_tasks") or [])},
            )

        sub_tasks = manager_plan.get("sub_tasks") or [
            {
                "title": task.title if task else "Primary task",
                "description": task.description if task else "",
                "required_tools": self._extract_required_tools(task),
                "required_capabilities": self._extract_required_tools(task),
                "parallelizable": False,
            }
        ]

        if not isinstance(routed_sub_tasks, list) or not routed_sub_tasks:
            await self._mark_run_step(
                run,
                step_id="route_workers",
                status="in_progress",
                message="Supervisor is routing subtasks to workers.",
            )
            candidate_workers = await self._candidate_workers(
                project.id, manager=manager, explicit_worker=explicit_worker, task=task
            )
            routed_sub_tasks = await self._route_sub_tasks_to_agents(
                project.id,
                sub_tasks,
                candidate_workers,
                manager=manager,
                parent_task=task,
            )
            self._set_workflow_checkpoint_artifact(
                run,
                key="manager_worker.routed_sub_tasks",
                value=routed_sub_tasks,
            )
            await self._emit_run_event(
                run,
                event_type="manager_plan",
                message="Manager created an execution graph.",
                payload={"sub_tasks": routed_sub_tasks},
            )
            await self._mark_run_step(
                run,
                step_id="route_workers",
                status="completed",
                message="Worker routing checkpoint saved.",
            )

        if not isinstance(branch_results, list):
            await self._mark_run_step(
                run,
                step_id="run_branches",
                status="in_progress",
                message="Executing delegated branches.",
            )
            parallel, sequential = self._partition_subtasks(routed_sub_tasks)
            branch_results = []
            if parallel:
                branch_results.extend(
                    await asyncio.gather(
                        *[
                            self._execute_subtask_branch(run, provider, item, project=project, manager=manager)
                            for item in parallel
                        ]
                    )
                )
            for item in sequential:
                branch_results.append(
                    await self._execute_subtask_branch(
                        run, provider, item, project=project, manager=manager
                    )
                )
            self._set_workflow_checkpoint_artifact(
                run,
                key="manager_worker.branch_results",
                value=branch_results,
            )
            await self._mark_run_step(
                run,
                step_id="run_branches",
                status="completed",
                message="Branch execution checkpoint saved.",
                metadata={"branch_count": len(branch_results)},
            )

        blocked = [item for item in branch_results if item.get("status") == "blocked"]
        if blocked:
            if manager:
                _, handoff_result = await self._execute_with_routing(
                    run,
                    provider=provider,
                    agent=manager,
                    system_prompt=manager.system_prompt or "You are an escalation manager.",
                    user_prompt=(
                        "One or more delegated branches are blocked. Resolve the blockers or escalate.\n\n"
                        f"{json.dumps(blocked, indent=2)}"
                    ),
                    purpose="manager escalation",
                )
                await self._emit_run_event(
                    run,
                    event_type="manager_handoff",
                    message="Manager reviewed blocked branches.",
                    payload={"blocked_count": len(blocked)},
                )
            raise BlockedExecution("Delegated sub-task execution is blocked and requires escalation")
        synthesis_input = json.dumps(branch_results, indent=2)
        synth_agent = explicit_worker or manager
        await self._mark_run_step(
            run,
            step_id="synthesize",
            status="in_progress",
            message="Supervisor is synthesizing branch outputs.",
        )
        _, synthesis_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=synth_agent,
            system_prompt=(manager.system_prompt if manager else "You are an orchestration manager."),
            user_prompt=(
                "Synthesize the delegated worker outputs into a final deliverable with decisions, "
                "tradeoffs, and next steps.\n\n"
                f"{synthesis_input}"
            ),
            purpose="manager synthesis",
            response_format=self._structured_output_response_format(synth_agent),
        )
        run.output_payload_json = {
            "manager_plan": manager_plan,
            "branches": branch_results,
            "summary": synthesis_result.output_text[:1200],
            "final_output": synthesis_result.output_text,
        }
        self._set_workflow_checkpoint_artifact(
            run,
            key="manager_worker.output_payload",
            value=run.output_payload_json,
        )
        await self._mark_run_step(
            run,
            step_id="synthesize",
            status="completed",
            message="Supervisor synthesis checkpoint saved.",
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="in_progress",
            message="Persisting manager execution graph.",
        )
        await self._write_artifact(
            run,
            kind="execution_graph",
            title="Manager execution graph",
            content=json.dumps(manager_plan, indent=2),
            metadata={"sub_task_count": len(routed_sub_tasks)},
        )
        await self._mark_run_step(
            run,
            step_id="persist_output",
            status="completed",
            message="Manager execution graph persisted.",
        )

    async def _execute_review_run(self, run: TaskRun) -> None:
        reviewer = await self._load_agent_for_run(run.reviewer_agent_id or run.worker_agent_id)
        provider = await self._resolve_provider_for_run(run, reviewer)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        gh_review = (run.input_payload_json or {}).get("github_pr_review")
        extra_ctx = ""
        if isinstance(gh_review, dict):
            extra_ctx = (
                "\n\nExternal GitHub PR review context:\n"
                f"State: {gh_review.get('state')}\n"
                f"Author: {gh_review.get('author_login')}\n"
                f"Body:\n{gh_review.get('body') or ''}\n"
            )
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=reviewer,
            system_prompt=(reviewer.system_prompt if reviewer else "You are a careful reviewer."),
            user_prompt=(
                "Review this task result and return a single JSON object with:\n"
                '- decision: "approved" or "rework"\n'
                '- summary: short string\n'
                '- reasons: array of strings (each a concrete issue or gap)\n'
                '- checklist: array of actionable strings the worker must verify before resubmitting\n\n'
                f"Task title: {task.title if task else 'Unknown'}\n"
                f"Task summary: {task.result_summary if task else ''}\n"
                f"Acceptance criteria: {task.acceptance_criteria if task else ''}\n"
                f"Latest structured reopen (if any): {json.dumps((task.metadata_json or {}).get('latest_reopen'), default=str) if task else {}}"
                f"{extra_ctx}"
            ),
            response_format="json",
            purpose="review",
        )
        review_payload = (
            result.output_json
            if isinstance(result.output_json, dict) and result.output_json.get("decision")
            else self._coerce_review_payload(result.output_text)
        )
        run.output_payload_json = {
            "summary": str(review_payload.get("summary") or result.output_text)[:1200],
            "review": result.output_text,
            "decision": review_payload.get("decision"),
        }
        if task:
            if review_payload.get("decision") == "approved":
                project = await self.db.get(OrchestratorProject, task.project_id)
                advanced = await self._advance_task_reviewer_chain(task, project, run.reviewer_agent_id)
                if advanced:
                    run.output_payload_json["next_reviewer_agent_id"] = task.reviewer_agent_id
                    await self._emit_run_event(
                        run,
                        event_type="review_handoff",
                        message="Review approved and handed off to the next reviewer in chain.",
                        payload={"next_reviewer_agent_id": task.reviewer_agent_id},
                    )
                else:
                    await self._transition_task_status(task, "approved", run=run, reason="review approved")
            else:
                self._append_structured_reopen_record(task, review_payload, run=run)
                await self._transition_task_status(task, "planned", run=run, reason="review requested rework")
                await self._emit_run_event(
                    run,
                    event_type="reopened",
                    level="warning",
                    message="Task reopened for rework after review (structured checklist recorded).",
                    payload=review_payload,
                )
            await self._post_reviewer_pr_comment(
                run,
                task,
                str(review_payload.get("summary") or result.output_text),
            )

    async def _decorate_brainstorms(self, items: list[Brainstorm]) -> None:
        counts = await self.repo.count_brainstorm_participants([item.id for item in items])
        for item in items:
            stop_conditions = item.stop_conditions_json or {}
            latest_round_summary = None
            for decision in reversed(item.decision_log_json or []):
                if decision.get("type") == "round_summary":
                    latest_round_summary = decision.get("summary")
                    break
            item.__orchestration_view__ = {
                "mode": stop_conditions.get("mode", "exploration"),
                "output_type": stop_conditions.get("output_type", "implementation_plan"),
                "participant_count": counts.get(item.id, 0),
                "current_round": self._brainstorm_current_round(item),
                "consensus_status": stop_conditions.get("consensus_status", "open"),
                "latest_round_summary": latest_round_summary,
            }

    def _normalize_brainstorm_stop_conditions(self, payload: dict[str, Any]) -> dict[str, Any]:
        stop_conditions = dict(payload.get("stop_conditions") or {})
        mode = self._normalize_brainstorm_mode(
            payload.get("mode") or stop_conditions.get("mode") or "exploration"
        )
        output_type = self._normalize_brainstorm_output_type(
            payload.get("output_type") or stop_conditions.get("output_type") or self._brainstorm_default_output_type(mode)
        )
        stop_conditions["mode"] = mode
        stop_conditions["output_type"] = output_type
        stop_conditions["max_cost_usd"] = float(payload.get("max_cost_usd") or stop_conditions.get("max_cost_usd") or 10)
        stop_conditions["max_repetition_score"] = float(payload.get("max_repetition_score") or stop_conditions.get("max_repetition_score") or 0.92)
        stop_conditions["stop_on_consensus"] = bool(stop_conditions.get("stop_on_consensus", True))
        stop_conditions["escalate_on_no_consensus"] = bool(stop_conditions.get("escalate_on_no_consensus", True))
        stop_conditions.setdefault("consensus_status", "open")
        stop_conditions["soft_consensus_min_similarity"] = float(
            stop_conditions.get("soft_consensus_min_similarity", 0.72)
        )
        stop_conditions["accept_soft_consensus"] = bool(stop_conditions.get("accept_soft_consensus", True))
        stop_conditions["conflict_pairwise_max_similarity"] = float(
            stop_conditions.get("conflict_pairwise_max_similarity", 0.38)
        )
        stop_conditions["conflict_requires_moderation"] = bool(
            stop_conditions.get("conflict_requires_moderation", True)
        )
        return stop_conditions

    def _normalize_brainstorm_mode(self, value: Any) -> str:
        raw = re.sub(r"[^a-z0-9]+", "_", str(value or "exploration").strip().lower()).strip("_")
        aliases = {
            "exploration": "exploration",
            "solution_design": "solution_design",
            "code_review": "code_review",
            "code_review_debate": "code_review",
            "incident_triage": "incident_triage",
            "root_cause": "root_cause",
            "root_cause_analysis": "root_cause",
            "architecture_proposal": "architecture_proposal",
        }
        return aliases.get(raw, "exploration")

    def _normalize_brainstorm_output_type(self, value: Any) -> str:
        raw = re.sub(r"[^a-z0-9]+", "_", str(value or "implementation_plan").strip().lower()).strip("_")
        aliases = {
            "adr": "adr",
            "architecture_decision_record": "adr",
            "implementation_plan": "implementation_plan",
            "delivery_plan": "implementation_plan",
            "test_plan": "test_plan",
            "verification_plan": "test_plan",
            "risk_register": "risk_register",
        }
        return aliases.get(raw, "implementation_plan")

    def _brainstorm_default_output_type(self, mode: str) -> str:
        defaults = {
            "exploration": "implementation_plan",
            "solution_design": "implementation_plan",
            "code_review": "test_plan",
            "incident_triage": "risk_register",
            "root_cause": "risk_register",
            "architecture_proposal": "adr",
        }
        return defaults.get(mode, "implementation_plan")

    def _brainstorm_mode(self, brainstorm: Brainstorm) -> str:
        return str((brainstorm.stop_conditions_json or {}).get("mode") or "exploration")

    def _brainstorm_output_type(self, brainstorm: Brainstorm) -> str:
        return str((brainstorm.stop_conditions_json or {}).get("output_type") or "implementation_plan")

    def _brainstorm_current_round(self, brainstorm: Brainstorm) -> int:
        summaries = [int(item.get("round", 0)) for item in (brainstorm.decision_log_json or []) if item.get("type") == "round_summary"]
        return max(summaries, default=0)

    def _brainstorm_final_output(self, brainstorm: Brainstorm) -> str | None:
        final_entry = next(
            (item for item in reversed(brainstorm.decision_log_json or []) if item.get("type") == "final_output"),
            None,
        )
        if final_entry and final_entry.get("content"):
            return str(final_entry["content"])
        return brainstorm.final_recommendation or brainstorm.summary

    def _brainstorm_mode_instruction(self, mode: str) -> str:
        prompts = {
            "exploration": "Surface broad options, assumptions, open questions, and promising directions.",
            "solution_design": "Converge on an implementation design with architecture, interfaces, and tradeoffs.",
            "code_review": "Critique proposed changes, find risks, and recommend fixes and tests.",
            "incident_triage": "Prioritize likely causes, blast radius, mitigations, and immediate next actions.",
            "root_cause": "Reason from symptoms to root causes, evidence gaps, and validation steps.",
            "architecture_proposal": "Produce a structured architecture recommendation with constraints and alternatives.",
        }
        return prompts.get(mode, prompts["exploration"])

    def _brainstorm_output_instruction(self, output_type: str) -> str:
        prompts = {
            "adr": "Return an ADR-style document with Context, Decision, Consequences, and Follow-ups.",
            "implementation_plan": "Return an implementation plan with phases, owners, dependencies, and risks.",
            "test_plan": "Return a test plan with scenarios, acceptance checks, fixtures, and failure modes.",
            "risk_register": "Return a risk register with severity, impact, mitigation, and contingency.",
        }
        return prompts.get(output_type, prompts["implementation_plan"])

    def _message_similarity(self, left: str, right: str) -> float:
        left_tokens = {token for token in re.findall(r"[a-z0-9_]+", left.lower()) if len(token) > 2}
        right_tokens = {token for token in re.findall(r"[a-z0-9_]+", right.lower()) if len(token) > 2}
        if not left_tokens or not right_tokens:
            return 0.0
        intersection = len(left_tokens.intersection(right_tokens))
        union = len(left_tokens.union(right_tokens))
        return intersection / union if union else 0.0

    def _brainstorm_first_line(self, text: str) -> str:
        for line in (text or "").splitlines():
            stripped = line.strip()
            if stripped:
                return stripped.lower()[:160]
        return (text or "").strip().lower()[:160]

    def _brainstorm_consensus_metrics_from_contents(
        self, contents: list[str], soft_thr: float, conflict_thr: float
    ) -> dict[str, Any]:
        n = len(contents)
        if n < 2:
            return {
                "pairwise_min_similarity": None,
                "pairwise_max_similarity": None,
                "repetition_score": 0.0,
                "conflict_signal": False,
                "consensus_kind": "none",
                "soft_consensus_match": False,
            }
        pairwise: list[float] = []
        for i in range(n):
            for j in range(i + 1, n):
                pairwise.append(self._message_similarity(contents[i], contents[j]))
        min_s = min(pairwise)
        max_s = max(pairwise)
        adj_scores = [
            self._message_similarity(contents[i - 1], contents[i]) for i in range(1, n)
        ]
        rep = max(adj_scores, default=0.0)
        normalized = {c.strip().lower()[:120] for c in contents if c.strip()}
        hard = len(normalized) == 1
        soft_match = min_s >= soft_thr
        distinct_lines = {self._brainstorm_first_line(c) for c in contents}
        conflict = max_s <= conflict_thr and len(distinct_lines) >= min(3, n)
        consensus_kind = "hard" if hard else "soft" if soft_match else "none"
        return {
            "pairwise_min_similarity": round(float(min_s), 4),
            "pairwise_max_similarity": round(float(max_s), 4),
            "repetition_score": round(float(rep), 4),
            "conflict_signal": bool(conflict),
            "consensus_kind": consensus_kind,
            "soft_consensus_match": bool(soft_match),
        }

    def _structured_output_response_format(self, agent: AgentProfile | None) -> str:
        policy = (agent.model_policy_json if agent else {}) or {}
        if policy.get("structured_output_enabled") is True:
            return "json"
        return "text"

    def _tool_calling_allowed(self, agent: AgentProfile | None) -> bool:
        if agent is None:
            return True
        policy = agent.model_policy_json or {}
        if "tool_calling_enabled" in policy:
            return bool(policy.get("tool_calling_enabled"))
        return True

    def _slugify(self, value: str) -> str:
        slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
        return slug or "brainstorm-output"

    async def _generate_brainstorm_round_summary(
        self,
        run: TaskRun,
        provider: ProviderConfig | None,
        moderator: AgentProfile | None,
        mode: str,
        round_number: int,
        round_messages: list[dict[str, Any]],
    ) -> str:
        run.input_payload_json = {**(run.input_payload_json or {}), "fallback_model": provider.default_model if provider else None}
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=moderator,
            system_prompt=(moderator.system_prompt if moderator else "You summarize multi-agent discussion rounds."),
            user_prompt=(
                f"Summarize brainstorm mode '{mode}' after round {round_number}. "
                "Be concise. Capture consensus, unresolved disagreements, and the best next move.\n\n"
                f"{json.dumps(round_messages, indent=2)}"
            ),
            purpose="brainstorm round summary",
        )
        return result.output_text[:2000]

    async def _finalize_brainstorm_output(
        self,
        brainstorm: Brainstorm,
        *,
        run: TaskRun | None = None,
        provider: ProviderConfig | None = None,
        moderator: AgentProfile | None = None,
        reason: str,
    ) -> None:
        messages = await self.repo.list_brainstorm_messages(brainstorm.id)
        transcript = [
            {
                "round": item.round_number,
                "agent_id": item.agent_id,
                "message_type": item.message_type,
                "content": item.content,
            }
            for item in messages
        ]
        if provider is None and run is not None:
            moderator = moderator or await self._load_agent_for_run(brainstorm.moderator_agent_id)
            provider = await self._resolve_provider_for_run(run, moderator)
        elif provider is None:
            moderator = moderator or await self._load_agent_for_run(brainstorm.moderator_agent_id)
            if moderator and moderator.provider_config_id:
                provider = await self.db.get(ProviderConfig, moderator.provider_config_id)
            if provider is None:
                project = await self.db.get(OrchestratorProject, brainstorm.project_id)
                providers = await self.repo.list_providers(brainstorm.initiator_user_id, project.id if project else None)
                provider = next((item for item in providers if item.is_default), None) or (providers[0] if providers else None)
        output_type = self._brainstorm_output_type(brainstorm)
        _, result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=moderator,
            system_prompt=(moderator.system_prompt if moderator else "You are a structured discussion moderator."),
            user_prompt=(
                f"Finalize brainstorm '{brainstorm.topic}'. Reason: {reason}. "
                f"Output target: {output_type}. {self._brainstorm_output_instruction(output_type)}\n\n"
                f"Transcript:\n{json.dumps(transcript, indent=2)}"
            ),
            append_metrics=run is not None,
            purpose="brainstorm finalization",
        )
        brainstorm.summary = (brainstorm.summary or result.output_text[:2000])[:4000]
        brainstorm.final_recommendation = result.output_text[:4000]
        brainstorm.status = "completed"
        brainstorm.updated_at = datetime.now(UTC)
        stop_conditions = dict(brainstorm.stop_conditions_json or {})
        stop_conditions["consensus_status"] = stop_conditions.get("consensus_status", "open")
        brainstorm.stop_conditions_json = stop_conditions
        decision_log = list(brainstorm.decision_log_json or [])
        decision_log.append(
            {
                "type": "final_output",
                "reason": reason,
                "output_type": output_type,
                "content": result.output_text[:12000],
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        brainstorm.decision_log_json = decision_log

    async def _execute_brainstorm_run(self, run: TaskRun) -> None:
        brainstorm = await self.db.get(Brainstorm, run.brainstorm_id) if run.brainstorm_id else None
        if brainstorm is None:
            raise RuntimeError("Brainstorm run missing brainstorm context.")
        participants = await self.repo.list_brainstorm_participants(brainstorm.id)
        if not participants:
            raise RuntimeError("Brainstorm has no participants.")
        moderator = await self._load_agent_for_run(brainstorm.moderator_agent_id)
        provider = await self._resolve_provider_for_run(run, moderator)
        stop_conditions = dict(brainstorm.stop_conditions_json or {})
        mode = self._brainstorm_mode(brainstorm)
        current_round = self._brainstorm_current_round(brainstorm)
        target_round = int(run.input_payload_json.get("target_round") or current_round + 1)
        prior_messages = await self.repo.list_brainstorm_messages(brainstorm.id)
        conversation = [
            {
                "round": item.round_number,
                "agent_id": item.agent_id,
                "message_type": item.message_type,
                "content": item.content,
            }
            for item in prior_messages
        ]
        round_messages: list[dict[str, Any]] = []
        mode_instruction = self._brainstorm_mode_instruction(mode)
        for participant in participants:
            agent = await self._load_agent_for_run(participant.agent_id)
            context = "\n\n".join(
                f"Round {item['round']} {item.get('agent_id')}: {item['content']}"
                for item in conversation[-6:]
            )
            _, result = await self._execute_with_routing(
                run,
                provider=provider,
                agent=agent,
                system_prompt=(agent.system_prompt if agent else "You are a brainstorming participant."),
                user_prompt=(
                    f"Brainstorm topic: {brainstorm.topic}\n"
                    f"Mode: {mode}\n"
                    f"Round: {target_round}\n"
                    f"Instruction: {mode_instruction}\n"
                    f"Prior discussion:\n{context or 'No prior discussion.'}\n\n"
                    "State your position, supporting evidence, major tradeoffs, and your recommended next move."
                ),
                purpose="brainstorm round",
            )
            text = result.output_text.strip()
            round_messages.append(
                {
                    "agent_id": participant.agent_id,
                    "agent_name": agent.name if agent else participant.agent_id,
                    "content": text,
                }
            )
            await self.repo.create_brainstorm_message(
                brainstorm_id=brainstorm.id,
                agent_id=participant.agent_id,
                round_number=target_round,
                message_type="argument",
                content=text,
                metadata_json={"mode": mode},
            )
            await self._emit_run_event(
                run,
                event_type="brainstorm_round",
                message=f"Round {target_round} response from {agent.name if agent else participant.agent_id}.",
                payload={"round": target_round, "agent_id": participant.agent_id},
            )
        repetition_score = 0.0
        if len(round_messages) >= 2:
            message_scores = []
            for index in range(1, len(round_messages)):
                message_scores.append(
                    self._message_similarity(
                        round_messages[index - 1]["content"],
                        round_messages[index]["content"],
                    )
                )
            repetition_score = max(message_scores, default=0.0)
        consensus_metrics = self._brainstorm_consensus_metrics_from_contents(
            [item["content"] for item in round_messages],
            float(stop_conditions.get("soft_consensus_min_similarity", 0.72)),
            float(stop_conditions.get("conflict_pairwise_max_similarity", 0.38)),
        )
        if len(round_messages) >= 2:
            consensus_metrics["repetition_score"] = round(float(repetition_score), 4)
        consensus_reached = False
        normalized_positions = {item["content"].strip().lower()[:120] for item in round_messages}
        hard_consensus = len(round_messages) >= 2 and len(normalized_positions) == 1
        soft_match = bool(consensus_metrics.get("soft_consensus_match"))
        if stop_conditions.get("stop_on_consensus", True) and len(round_messages) >= 2:
            consensus_reached = hard_consensus or (
                soft_match and bool(stop_conditions.get("accept_soft_consensus", True))
            )
        if consensus_reached:
            stop_conditions["consensus_status"] = "consensus" if hard_consensus else "soft_consensus"
        elif bool(consensus_metrics.get("conflict_signal")):
            stop_conditions["consensus_status"] = "conflict"
        elif repetition_score >= float(stop_conditions.get("max_repetition_score", 0.92)):
            stop_conditions["consensus_status"] = "loop_detected"
        else:
            stop_conditions["consensus_status"] = "open"
        round_summary = await self._generate_brainstorm_round_summary(
            run,
            provider,
            moderator,
            mode,
            target_round,
            round_messages,
        )
        decision_log = list(brainstorm.decision_log_json or [])
        decision_log.append(
            {
                "type": "round_summary",
                "round": target_round,
                "summary": round_summary,
                "repetition_score": repetition_score,
                "consensus_reached": consensus_reached,
                "consensus_kind": "hard" if hard_consensus else "soft" if soft_match else "open",
                "conflict_signal": bool(consensus_metrics.get("conflict_signal")),
                "pairwise_min_similarity": consensus_metrics.get("pairwise_min_similarity"),
                "pairwise_max_similarity": consensus_metrics.get("pairwise_max_similarity"),
                "created_at": datetime.now(UTC).isoformat(),
            }
        )
        brainstorm.decision_log_json = decision_log
        brainstorm.summary = round_summary
        brainstorm.updated_at = datetime.now(UTC)
        cost_usd = run.estimated_cost_micros / 1_000_000
        force_finalize = False
        force_reason = ""
        if consensus_reached:
            force_finalize = True
            force_reason = "consensus"
        elif target_round >= brainstorm.max_rounds:
            force_finalize = True
            force_reason = "max_rounds"
        elif cost_usd >= float(stop_conditions.get("max_cost_usd", 10)):
            force_finalize = True
            force_reason = "max_cost"
        elif repetition_score >= float(stop_conditions.get("max_repetition_score", 0.92)):
            force_finalize = True
            force_reason = "loop_detected"

        brainstorm.stop_conditions_json = stop_conditions
        run.output_payload_json = {
            "summary": round_summary,
            "round_messages": round_messages,
            "consensus_reached": consensus_reached,
            "rounds_completed": target_round,
            "mode": mode,
            "output_type": self._brainstorm_output_type(brainstorm),
            "repetition_score": repetition_score,
            "consensus_metrics": consensus_metrics,
            "hard_consensus": hard_consensus,
            "soft_consensus_match": soft_match,
        }
        await self._emit_run_event(
            run,
            event_type="brainstorm_round_summary",
            message=f"Round {target_round} summary generated.",
            payload={"round": target_round, "repetition_score": repetition_score, "consensus_reached": consensus_reached},
        )
        if force_finalize:
            await self._finalize_brainstorm_output(
                brainstorm,
                run=run,
                provider=provider,
                moderator=moderator,
                reason=force_reason,
            )
            await self._emit_run_event(
                run,
                event_type="brainstorm_finalized",
                message=f"Brainstorm finalized after round {target_round}.",
                payload={"reason": force_reason},
            )
        else:
            brainstorm.status = "running"
        if (
            not consensus_reached
            and target_round >= brainstorm.max_rounds
            and stop_conditions.get("escalate_on_no_consensus", True)
        ):
            task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
            await self._escalate_blocker(
                run,
                task=task,
                reason="Brainstorm ended without consensus after configured limit.",
                metadata={"brainstorm_id": brainstorm.id, "round": target_round},
            )
        project = await self.db.get(OrchestratorProject, run.project_id)
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        if project and task:
            await self._apply_project_escalation_rules(
                project,
                run=run,
                task=task,
                trigger="brainstorm_finished",
                rounds_completed=target_round,
                consensus_reached=consensus_reached,
            )

    async def _execute_debate_run(self, run: TaskRun) -> None:
        project = await self.db.get(OrchestratorProject, run.project_id)
        if project is None:
            raise RuntimeError("Run project not found")
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        moderator = await self._load_agent_for_run(run.orchestrator_agent_id)
        participants = await self._debate_participants(
            project.id,
            preferred_ids=[run.worker_agent_id, run.reviewer_agent_id],
            task=task,
        )
        if len(participants) < 2:
            raise RuntimeError("Debate mode requires at least two agents")
        provider = await self._resolve_provider_for_run(run, moderator or participants[0])
        prompt = await self._build_task_prompt(run, moderator, prefix="Moderate a structured two-sided debate.")
        statements: list[dict[str, Any]] = []
        prior = ""
        for round_number in range(1, 3):
            for side, agent in enumerate(participants[:2], start=1):
                _, result = await self._execute_with_routing(
                    run,
                    provider=provider,
                    agent=agent,
                    system_prompt=agent.system_prompt or "You are a specialist debating a task approach.",
                    user_prompt=(
                        f"{prompt}\n\nDebate round {round_number}. You are side {side}. "
                        f"Respond to the prior position and defend your recommendation.\n\nPrior:\n{prior or 'No prior argument.'}"
                    ),
                    purpose="debate argument",
                )
                prior = result.output_text
                statements.append({"round": round_number, "agent_id": agent.id, "text": result.output_text})
                await self._emit_run_event(
                    run,
                    event_type="debate_argument",
                    message=f"Round {round_number} argument from {agent.name}.",
                    payload={"agent_id": agent.id},
                )
        _, moderator_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=moderator,
            system_prompt=(moderator.system_prompt if moderator else "You are a moderator."),
            user_prompt=(
                "Resolve this debate and provide the final recommendation.\n\n"
                f"{json.dumps(statements, indent=2)}"
            ),
            purpose="debate moderation",
            response_format=self._structured_output_response_format(moderator),
        )
        run.output_payload_json = {
            "summary": moderator_result.output_text[:1200],
            "final_output": moderator_result.output_text,
            "debate_messages": statements,
        }
        await self._write_artifact(
            run,
            kind="debate_transcript",
            title="Debate transcript",
            content=json.dumps(statements, indent=2),
            metadata={"participant_count": 2},
        )

    async def _emit_run_event(
        self,
        run: TaskRun,
        *,
        event_type: str,
        message: str,
        level: str = "info",
        payload: dict[str, Any] | None = None,
        input_tokens: int = 0,
        output_tokens: int = 0,
        cost_usd_micros: int = 0,
    ) -> None:
        await self.repo.create_run_event(
            run_id=run.id,
            task_id=run.task_id,
            event_type=event_type,
            level=level,
            message=message,
            payload_json=payload or {},
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            cost_usd_micros=cost_usd_micros,
        )
        await self._refresh_run_scratchpad(run)
        await self.db.commit()

    async def _transition_task_status(
        self,
        task: OrchestratorTask,
        next_status: str,
        *,
        run: TaskRun | None = None,
        reason: str | None = None,
    ) -> None:
        current = task.status
        if current == next_status:
            return
        allowed = TASK_TRANSITIONS.get(current, set())
        if next_status not in allowed:
            raise HTTPException(
                status_code=409,
                detail=f"Invalid task transition from {current} to {next_status}",
            )
        task.status = next_status
        task.updated_at = datetime.now(UTC)
        if next_status == "blocked":
            await self._apply_blocked_handoff_suggestion(task, run, reason)
        if run is not None:
            payload_json: dict[str, Any] = {"from": current, "to": next_status, "reason": reason}
            if next_status == "blocked":
                hid = (task.metadata_json or {}).get("suggested_handoff_agent_id")
                if hid:
                    payload_json["suggested_handoff_agent_id"] = hid
                    payload_json["handoff_suggested_via"] = (task.metadata_json or {}).get("handoff_suggested_via")
            await self.repo.create_run_event(
                run_id=run.id,
                task_id=task.id,
                event_type="task_status_changed",
                message=f"Task transitioned from {current} to {next_status}.",
                payload_json=payload_json,
            )
            await self.db.commit()

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

    _TOOL_MIN_PERMISSION: dict[str, str] = {
        "fs_read": "read-only",
        "repo_search": "read-only",
        "web_fetch": "read-only",
        "web_search": "read-only",
        "github_comment": "comment-only",
        "github_label_issue": "code-write",
        "github_create_pr": "code-write",
        "fs_write": "code-write",
        "code_execute": "code-write",
        "db_query": "code-write",
    }
    _PERMISSION_RANK: dict[str, int] = {"read-only": 1, "comment-only": 2, "code-write": 3, "merge-blocked": 3}
    _MERGE_BLOCKED_TOOLS: frozenset[str] = frozenset({"github_create_pr", "github_label_issue"})

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

    def _decision_text_relevance_score(self, query: str, title: str, body: str) -> float:
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", (query or "").lower())}
        if not q_tokens:
            return 0.0
        blob = f"{title} {body}".lower()
        t_tokens = set(re.findall(r"[a-z0-9]{3,}", blob))
        if not t_tokens:
            return 0.0
        return len(q_tokens & t_tokens) / max(len(q_tokens), 1)

    async def _plan_agent_execution(
        self,
        run: TaskRun,
        *,
        provider: ProviderConfig | None,
        agent,
        prompt: str,
        purpose: str,
        default_tool_calls: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        explicit = run.input_payload_json.get("tool_calls")
        explicit_subtasks = run.input_payload_json.get("sub_tasks")
        if explicit or explicit_subtasks:
            return {
                "summary": "Using explicit input payload plan.",
                "tool_calls": explicit or default_tool_calls or [],
                "sub_tasks": explicit_subtasks or [],
            }
        _, planning_result = await self._execute_with_routing(
            run,
            provider=provider,
            agent=agent,
            system_prompt=(agent.system_prompt if agent else "You are a planning agent."),
            user_prompt=(
                f"{prompt}\n\nReturn JSON for {purpose} with keys: summary, blocked_reason, tool_calls, "
                "and sub_tasks. Each tool call must contain tool and arguments."
            ),
            response_format="json",
            purpose=purpose,
        )
        payload = planning_result.output_json or {}
        if not isinstance(payload, dict):
            payload = {}
        tool_calls = payload.get("tool_calls")
        if not isinstance(tool_calls, list):
            tool_calls = default_tool_calls or []
        sub_tasks = payload.get("sub_tasks")
        if not isinstance(sub_tasks, list):
            sub_tasks = []
        blocked_reason = payload.get("blocked_reason")
        if blocked_reason:
            raise BlockedExecution(str(blocked_reason))
        return {
            "summary": str(payload.get("summary") or planning_result.output_text[:500]),
            "tool_calls": tool_calls,
            "sub_tasks": sub_tasks,
        }

    async def _execute_tool_calls(
        self,
        run: TaskRun,
        *,
        project: OrchestratorProject,
        task: OrchestratorTask | None,
        tool_calls: list[dict[str, Any]],
        allowed_tools: list[str] | None,
        agent: AgentProfile | None = None,
    ) -> list[dict[str, Any]]:
        if not tool_calls:
            return []
        if agent and not self._tool_calling_allowed(agent):
            await self._emit_run_event(
                run,
                event_type="tool_calls_skipped",
                level="warning",
                message="Tool calls were skipped because tool_calling_enabled is false for this agent.",
                payload={"requested": [str(c.get("tool") or "") for c in tool_calls]},
            )
            return [
                {
                    "tool": str(call.get("tool") or ""),
                    "status": "skipped",
                    "error": "Tool calling disabled by agent model policy.",
                }
                for call in tool_calls
            ]
        toolbox = OrchestrationToolbox(db=self.db, repo=self.repo, project=project, task=task, run=run)
        results: list[dict[str, Any]] = []
        failures = 0
        effective_allowed = set(allowed_tools or [])
        dangerous_tools = {"code_execute", "db_query", "fs_write", "github_create_pr", "github_label_issue"}
        hitl_settings = (project.settings_json or {}).get("hitl") or {}
        secret_scope = str(hitl_settings.get("secret_scope") or "project_default")
        for index, call in enumerate(tool_calls, start=1):
            tool_name = str(call.get("tool") or "").strip()
            self._tool_allowed_for_agent_permissions(tool_name, agent)
            if self.action_requires_approval(project, "run_tool") and tool_name in dangerous_tools:
                approval = await self.repo.create_approval(
                    project_id=project.id,
                    task_id=task.id if task else None,
                    run_id=run.id,
                    issue_link_id=task.github_issue_link_id if task else None,
                    requested_by_user_id=run.triggered_by_user_id,
                    approval_type="dangerous_tool_call",
                    status="pending",
                    payload_json={"tool": tool_name, "arguments": call.get("arguments") or {}},
                )
                await self.db.commit()
                raise BlockedExecution(
                    f"Dangerous tool '{tool_name}' requires approval (approval_id={approval.id})."
                )
            if secret_scope == "deny_external" and tool_name in {
                "github_comment",
                "github_label_issue",
                "github_create_pr",
                "web_fetch",
                "web_search",
            }:
                raise BlockedExecution(
                    f"Tool '{tool_name}' blocked by secret scope policy ({secret_scope})."
                )
            if effective_allowed and tool_name not in effective_allowed:
                raise BlockedExecution(f"Tool '{tool_name}' is not allowed for this agent")
            await self._emit_run_event(
                run,
                event_type="tool_call_started",
                message=f"Executing tool {tool_name}.",
                payload={"index": index, "tool": tool_name},
            )
            try:
                result = await toolbox.execute(call)
            except ToolExecutionError as exc:
                failures += 1
                await self._emit_run_event(
                    run,
                    event_type="tool_call_failed",
                    level="warning",
                    message=str(exc),
                    payload={"tool": tool_name, "index": index},
                )
                results.append({"tool": tool_name, "status": "failed", "error": str(exc)})
                if failures >= 2:
                    await self._escalate_blocker(
                        run,
                        task=task,
                        reason="Multiple tool failures detected during execution.",
                        metadata={"tool_failures": failures},
                    )
                    raise BlockedExecution("Task blocked after repeated tool-call failures")
                continue
            results.append({"tool": tool_name, "status": "completed", "result": result})
            await self._emit_run_event(
                run,
                event_type="tool_call_completed",
                message=f"Tool {tool_name} completed.",
                payload={"index": index, "tool": tool_name, "result_preview": json.dumps(result, default=str)[:500]},
            )
            await self._write_artifact(
                run,
                kind="tool_result",
                title=f"Tool result: {tool_name}",
                content=json.dumps(result, default=str, indent=2)[:12000],
                metadata={"tool": tool_name},
            )
        return results

    def _build_final_prompt(
        self,
        *,
        base_prompt: str,
        execution_plan: dict[str, Any],
        tool_results: list[dict[str, Any]],
    ) -> str:
        sections = [base_prompt]
        if execution_plan.get("summary"):
            sections.append(f"Execution plan summary:\n{execution_plan['summary']}")
        if tool_results:
            sections.append(f"Tool results:\n{json.dumps(tool_results, indent=2, default=str)}")
        sections.append(
            "Produce the final task output. Include concrete next steps, note blockers if any remain, "
            "and keep the response usable as a task artifact."
        )
        return "\n\n".join(section for section in sections if section)

    async def _write_artifact(
        self,
        run: TaskRun,
        *,
        kind: str,
        title: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        if run.task_id is None:
            return
        await self.repo.create_task_artifact(
            task_id=run.task_id,
            run_id=run.id,
            kind=kind,
            title=title,
            content=content,
            metadata_json=metadata or {},
        )
        await self.db.commit()

    async def _apply_result_metrics(
        self,
        run: TaskRun,
        provider: ProviderConfig | None,
        results: list,
        *,
        agent=None,
        append: bool = False,
    ) -> None:
        total_in = sum(item.input_tokens for item in results)
        total_out = sum(item.output_tokens for item in results)
        total_latency = sum(item.latency_ms for item in results)
        if append:
            run.token_input += total_in
            run.token_output += total_out
            run.latency_ms = (run.latency_ms or 0) + total_latency
        else:
            run.token_input = total_in
            run.token_output = total_out
            run.latency_ms = total_latency
        run.token_total = run.token_input + run.token_output
        model_name = results[-1].model_name if results else run.model_name
        run.estimated_cost_micros = self._estimate_cost_micros(
            provider,
            run.token_input,
            run.token_output,
            model_name=model_name,
        )
        token_budget = (agent.budget_json or {}).get("token_budget") if agent else None
        if token_budget and run.token_total > int(token_budget):
            await self._emit_run_event(
                run,
                event_type="budget_exceeded",
                level="warning",
                message=f"Token budget {token_budget} exceeded ({run.token_total} used).",
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
        for item in sub_tasks:
            required_capabilities = {
                str(value).strip()
                for value in item.get("required_capabilities", []) + item.get("required_tools", [])
                if str(value).strip()
            }
            chosen = None
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
            routed.append(
                {
                    **item,
                    "assigned_agent_id": chosen.id if chosen else None,
                    "assigned_agent_name": chosen.name if chosen else None,
                    "queue_depth": queue_depths.get(chosen.id, 0) if chosen else None,
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
                "branch_title": sub_task.get("title"),
                "assigned_agent_id": sub_task.get("assigned_agent_id"),
                "trace": self._workflow_trace_payload(run),
            },
        )
        if worker is None:
            await self._emit_run_event(
                run,
                event_type="branch_unassigned",
                level="warning",
                message=f"No capable worker found for sub-task '{sub_task.get('title', 'Untitled')}'.",
                payload=sub_task,
            )
            return {**sub_task, "status": "blocked", "reason": "no_capable_worker"}
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
            run,
            provider=provider,
            agent=worker,
            system_prompt=(worker.system_prompt if worker else "You are a specialist worker."),
            user_prompt=prompt,
            purpose="delegated sub-task",
            response_format=self._structured_output_response_format(worker),
        )
        await self._emit_run_event(
            run,
            event_type="worker_response",
            message=f"Worker {worker.name} completed sub-task '{sub_task.get('title', 'Untitled')}'.",
            payload={"agent_id": worker.id, "branch_title": sub_task.get("title")},
        )
        return {
            **sub_task,
            "status": "completed",
            "agent_id": worker.id,
            "agent_name": worker.name,
            "output": result.output_text,
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

    def _normalize_project_settings(self, settings: dict[str, Any] | None) -> dict[str, Any]:
        raw = dict(settings or {})
        execution = dict(raw.get("execution") or {})
        execution.setdefault("autonomy_level", "assisted")
        execution.setdefault("manager_agent_id", None)
        execution.setdefault("reviewer_agent_ids", [])
        execution.setdefault("reviewer_chain_mode", "sequential")
        execution.setdefault("provider_config_id", None)
        execution.setdefault("model_name", None)
        execution.setdefault("fallback_model", None)
        execution.setdefault("escalation_rules", [])
        execution.setdefault("routing_mode", "capability_based")
        execution.setdefault("sibling_load_balance", "queue_depth")
        execution.setdefault("skip_unhealthy_worker_providers", True)
        execution.setdefault("offline_local_only_mode", False)
        execution.setdefault("enforce_project_model_policy", False)
        execution.setdefault("allowed_provider_types", [])
        execution.setdefault("allowed_model_slugs", [])
        blocked_handoff = dict(execution.get("blocked_handoff") or {})
        blocked_handoff.setdefault("mode", "escalation_path")
        blocked_handoff.setdefault("target_agent_id", None)
        blocked_handoff.setdefault("fallback_to_manager", True)
        execution["blocked_handoff"] = blocked_handoff
        sla = dict(execution.get("sla") or {})
        sla.setdefault("enabled", True)
        sla.setdefault("warn_hours_before_due", 24)
        sla.setdefault("escalate_hours_after_due", 0)
        execution["sla"] = sla
        execution.setdefault("approval_gates", [
            "post_to_github",
            "open_pr",
            "mark_complete",
            "change_task_ownership",
            "write_memory",
            "use_expensive_model",
            "run_tool",
        ])
        execution.setdefault("expensive_model_cost_per_1k_usd", 0.01)
        execution["policy_routing"] = self._normalize_policy_routing(execution.get("policy_routing"))
        raw["execution"] = execution
        github = dict(raw.get("github") or {})
        github.setdefault("branch_prefix", "troop/{task_id}-{slug}")
        github.setdefault("enforce_branch_naming", True)
        github.setdefault("auto_post_progress", False)
        github.setdefault("auto_review_on_pr_review", False)
        github.setdefault("auto_activate_review_on_pr_open", True)
        github.setdefault("draft_prs_by_default", True)
        github.setdefault("close_issue_with_manager_summary", True)
        github.setdefault("write_requires_approval", True)
        github.setdefault("sync_labels_to_github", True)
        github.setdefault("sync_assignees_to_github", True)
        github.setdefault("sync_state_to_github", True)
        github.setdefault("sync_milestone_to_github", True)
        github.setdefault("repo_agent_pools", {})
        raw["github"] = github
        hitl = dict(raw.get("hitl") or {})
        hitl.setdefault("sandbox_note", "")
        hitl.setdefault("secret_scope", "project_default")
        hitl.setdefault("sandbox_mode", "allow_host_fallback")
        raw["hitl"] = hitl
        mem_defaults = merge_memory_settings({})
        mem_in = dict(raw.get("memory") or {})
        raw["memory"] = {**mem_defaults, **mem_in}
        return raw

    def _merge_nested_project_settings(
        self, base: dict[str, Any], incoming: dict[str, Any]
    ) -> dict[str, Any]:
        out = dict(base)
        for key, val in incoming.items():
            if key == "execution" and isinstance(val, dict):
                out["execution"] = {**(base.get("execution") or {}), **val}
            elif key == "memory" and isinstance(val, dict):
                out["memory"] = {**(base.get("memory") or {}), **val}
            else:
                out[key] = val
        return out

    def _project_execution_settings(self, project: OrchestratorProject) -> dict[str, Any]:
        return self._normalize_project_settings(project.settings_json).get("execution", {})

    def _project_github_settings(self, project: OrchestratorProject | None) -> dict[str, Any]:
        if project is None:
            return self._normalize_project_settings({}).get("github", {})
        return self._normalize_project_settings(project.settings_json).get("github", {})

    def _repo_pool_config(
        self,
        project: OrchestratorProject | None,
        *,
        repository: GithubRepository | None = None,
        repository_id: str | None = None,
        repository_full_name: str | None = None,
    ) -> dict[str, Any]:
        github = self._project_github_settings(project)
        pools = dict(github.get("repo_agent_pools") or {})
        keys = [repository_id, repository_full_name]
        if repository is not None:
            keys = [repository.id, repository.full_name, *keys]
        for key in keys:
            text = str(key or "").strip()
            if text and isinstance(pools.get(text), dict):
                return dict(pools[text])
        return {}

    async def _task_github_repository(self, task: OrchestratorTask | None) -> GithubRepository | None:
        if task is None or not task.github_issue_link_id:
            return None
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return None
        return await self.db.get(GithubRepository, issue_link.repository_id)

    async def _task_repo_pool_config(self, task: OrchestratorTask | None) -> dict[str, Any]:
        if task is None:
            return {}
        project = await self.db.get(OrchestratorProject, task.project_id)
        repository = await self._task_github_repository(task)
        return self._repo_pool_config(project, repository=repository)

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

    async def _provider_health_snapshots(
        self, agents: list[AgentProfile]
    ) -> dict[str, tuple[bool, datetime | None]]:
        ids = list({a.provider_config_id for a in agents if a.provider_config_id})
        if not ids:
            return {}
        result = await self.db.execute(
            select(ProviderConfig.id, ProviderConfig.is_healthy, ProviderConfig.last_healthcheck_at).where(
                ProviderConfig.id.in_(ids)
            )
        )
        return {row[0]: (bool(row[1]), row[2]) for row in result.all()}

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

    async def _advance_task_reviewer_chain(
        self,
        task: OrchestratorTask,
        project: OrchestratorProject | None,
        reviewer_agent_id: str | None,
    ) -> bool:
        chain = self._reviewer_chain_for_project(project)
        if not chain or not reviewer_agent_id:
            return False
        try:
            current_index = chain.index(str(reviewer_agent_id))
        except ValueError:
            return False
        if current_index >= len(chain) - 1:
            return False
        next_reviewer_id = chain[current_index + 1]
        metadata = dict(task.metadata_json or {})
        metadata["review_chain"] = {
            "reviewer_agent_ids": chain,
            "current_index": current_index + 1,
            "last_completed_reviewer_agent_id": reviewer_agent_id,
        }
        task.metadata_json = metadata
        task.reviewer_agent_id = next_reviewer_id
        if hasattr(task, "_sa_instance_state"):
            orm_attributes.flag_modified(task, "metadata_json")
        return True

    async def _apply_project_escalation_rules(
        self,
        project: OrchestratorProject,
        *,
        run: TaskRun,
        task: OrchestratorTask,
        trigger: str,
        rounds_completed: int | None = None,
        consensus_reached: bool | None = None,
    ) -> None:
        rules = self._project_execution_settings(project).get("escalation_rules", [])
        if not isinstance(rules, list):
            return
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            escalate_to = rule.get("escalate_to") or self._project_execution_settings(project).get("manager_agent_id")
            condition = rule.get("condition")
            if condition == "stuck_for_minutes" and trigger in {"task_blocked", "run_failed"}:
                threshold = int(rule.get("value", 0) or 0)
                if threshold <= 0:
                    continue
                started_at = run.started_at or run.created_at
                elapsed_minutes = int((datetime.now(UTC) - started_at).total_seconds() / 60)
                if elapsed_minutes >= threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={"condition": condition, "value": threshold, "elapsed_minutes": elapsed_minutes, "escalate_to": escalate_to},
                    )
            if condition == "cost_exceeds_usd" and trigger == "run_completed":
                threshold = float(rule.get("value", 0) or 0)
                cost_usd = run.estimated_cost_micros / 1_000_000
                if threshold > 0 and cost_usd > threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={"condition": condition, "value": threshold, "cost_usd": cost_usd, "escalate_to": escalate_to},
                    )
            if condition == "no_consensus_after_rounds" and trigger == "brainstorm_finished":
                threshold = int(rule.get("value", 0) or 0)
                if threshold > 0 and consensus_reached is False and (rounds_completed or 0) >= threshold:
                    await self.repo.create_approval(
                        project_id=project.id,
                        task_id=task.id,
                        run_id=run.id,
                        requested_by_user_id=run.triggered_by_user_id,
                        approval_type="rule_escalation",
                        status="pending",
                        payload_json={"condition": condition, "value": threshold, "rounds_completed": rounds_completed, "escalate_to": escalate_to},
                    )
        await self.db.commit()

    async def _escalate_blocker(
        self,
        run: TaskRun,
        *,
        task: OrchestratorTask | None,
        reason: str,
        metadata: dict[str, Any] | None = None,
    ) -> None:
        escalate_to_agent_id = run.orchestrator_agent_id or task.reviewer_agent_id if task else None
        await self.repo.create_approval(
            project_id=run.project_id,
            task_id=task.id if task else None,
            run_id=run.id,
            requested_by_user_id=run.triggered_by_user_id,
            approval_type="task_escalation",
            status="pending",
            payload_json={
                "reason": reason,
                "escalate_to_agent_id": escalate_to_agent_id,
                "metadata": metadata or {},
            },
        )
        await self.db.commit()

    def _coerce_review_payload(self, text: str) -> dict[str, Any]:
        stripped = text.strip()
        if stripped.startswith("{"):
            try:
                data = json.loads(stripped)
                if isinstance(data, dict) and data.get("decision"):
                    reasons = data.get("reasons")
                    if isinstance(reasons, str):
                        reasons = [reasons]
                    elif not isinstance(reasons, list):
                        reasons = []
                    checklist = data.get("checklist")
                    if not isinstance(checklist, list):
                        checklist = []
                    return {
                        "decision": str(data.get("decision")),
                        "summary": str(data.get("summary") or stripped[:1200]),
                        "reasons": [str(x) for x in reasons],
                        "checklist": [str(x) for x in checklist],
                    }
            except json.JSONDecodeError:
                pass
        lowered = stripped.lower()
        decision = "approved" if "approve" in lowered and "rework" not in lowered else "rework"
        return {"decision": decision, "summary": stripped[:1200], "reasons": [], "checklist": []}

    async def _resolve_provider_for_run(
        self, run: TaskRun, agent: AgentProfile | None
    ) -> ProviderConfig | None:
        project = await self.db.get(OrchestratorProject, run.project_id)
        execution_settings = self._project_execution_settings(project) if project else {}
        offline_local_only_mode = bool(execution_settings.get("offline_local_only_mode"))

        async def _local_provider_for_project() -> ProviderConfig | None:
            if project is None:
                return None
            providers = await self.repo.list_providers(project.owner_id, project.id)
            return next(
                (
                    item
                    for item in providers
                    if item.is_enabled and item.provider_type in {"ollama", "local"}
                ),
                None,
            )

        if run.provider_config_id:
            provider = await self.db.get(ProviderConfig, run.provider_config_id)
            if provider:
                if offline_local_only_mode and provider.provider_type not in {"ollama", "local"}:
                    return await _local_provider_for_project()
                return provider
        if project is not None:
            if execution_settings.get("provider_config_id"):
                provider = await self.db.get(ProviderConfig, execution_settings["provider_config_id"])
                if provider:
                    if offline_local_only_mode and provider.provider_type not in {"ollama", "local"}:
                        return await _local_provider_for_project()
                    return provider
        if agent and agent.provider_config_id:
            provider = await self.db.get(ProviderConfig, agent.provider_config_id)
            if provider:
                if offline_local_only_mode and provider.provider_type not in {"ollama", "local"}:
                    return await _local_provider_for_project()
                return provider
        if agent and agent.project_id:
            providers = await self.repo.list_providers(agent.owner_id, agent.project_id)
            default = next((item for item in providers if item.is_default), None)
            if default:
                if offline_local_only_mode and default.provider_type not in {"ollama", "local"}:
                    return await _local_provider_for_project()
                return default
        if offline_local_only_mode:
            return await _local_provider_for_project()
        return None

    async def _index_project_document(self, document: ProjectDocument) -> None:
        chunks = _chunk_text(
            document.source_text,
            settings.AI_DOCUMENT_CHUNK_SIZE,
            settings.AI_DOCUMENT_CHUNK_OVERLAP,
        )
        embeddings = await self.ai_providers.embed_texts(chunks) if chunks else []
        await self.repo.replace_document_chunks(
            document,
            [
                (
                    index,
                    chunk,
                    _estimate_embedding_tokens(chunk),
                    embeddings[index],
                    dict(document.metadata_json or {}),
                )
                for index, chunk in enumerate(chunks)
            ],
        )
        document.ingestion_status = "completed"
        document.chunk_count = len(chunks)
        document.summary_text = (document.summary_text or document.source_text[:500])[:1000]
        document.updated_at = datetime.now(UTC)

    async def _expire_project_memory(self, project_id: str) -> None:
        now = datetime.now(UTC)
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            return
        for document in await self.repo.list_documents(project_id):
            if document.expires_at and document.expires_at <= now and document.deleted_at is None:
                document.deleted_at = now
        result = await self.repo.list_agent_memory(
            owner_id=project.owner_id,
            project_id=project_id,
        )
        for item in result:
            if item.expires_at and item.expires_at <= now and item.deleted_at is None:
                item.deleted_at = now
                item.status = "expired"

    async def _build_agent_memory_context(
        self, agent: AgentProfile | None, project_id: str
    ) -> str:
        if agent is None:
            return ""
        memory_scope = (agent.memory_policy_json or {}).get("scope", "none")
        if memory_scope == "none":
            return ""
        items = await self.repo.list_agent_memory(
            agent.owner_id,
            project_id=project_id if memory_scope != "long-term" else None,
            agent_id=agent.id,
            status="approved",
        )
        lines = [f"{item.key}: {item.value_text}" for item in items[:8] if not item.deleted_at]
        return "\n".join(lines[:8])

    async def _build_project_knowledge_context(
        self, run: TaskRun, task: OrchestratorTask | None
    ) -> str:
        query_bits = [
            task.title if task else "",
            task.description if task and task.description else "",
            task.acceptance_criteria if task and task.acceptance_criteria else "",
        ]
        query = "\n".join(bit for bit in query_bits if bit).strip()
        if not query:
            return ""
        matches = await self._search_project_knowledge(
            run.project_id,
            query,
            task_id=task.id if task else None,
            top_k=4,
            include_decisions=True,
        )
        return "\n\n".join(
            f"{item['filename']} [score={item['score']}]\n{item['content'][:500]}"
            for item in matches
        )

    async def _build_run_scratchpad_context(self, run: TaskRun) -> tuple[str, str]:
        scratchpad = str((run.checkpoint_json or {}).get("scratchpad_summary") or "")
        if run.task_id is None:
            return scratchpad, ""
        previous = await self.repo.get_latest_run_for_task(
            run.project_id,
            run.task_id,
            exclude_run_id=run.id,
        )
        if previous is None:
            return scratchpad, ""
        previous_summary = str(
            (previous.output_payload_json or {}).get("summary")
            or (previous.output_payload_json or {}).get("final_output")
            or ""
        )[:1200]
        current_summary = str(
            (run.output_payload_json or {}).get("summary")
            or (run.output_payload_json or {}).get("final_output")
            or ""
        )[:1200]
        diff = "\n".join(
            [
                f"Previous run ({previous.id}) status: {previous.status}",
                f"Previous summary: {previous_summary or 'n/a'}",
                f"Current known summary: {current_summary or 'n/a'}",
            ]
        )
        return scratchpad, diff

    async def _refresh_run_scratchpad(self, run: TaskRun) -> None:
        events = await self.repo.list_run_events(run.id)
        recent = events[-8:]
        summary = "\n".join(f"{item.event_type}: {item.message[:180]}" for item in recent)
        run.checkpoint_json = {
            **(run.checkpoint_json or {}),
            "scratchpad_summary": summary[:2000],
            "last_event_count": len(events),
        }

    async def _persist_agent_memory_from_run(
        self, run: TaskRun, agent: AgentProfile | None, task: OrchestratorTask | None
    ) -> None:
        if agent is None:
            return
        scope = str((agent.memory_policy_json or {}).get("scope") or "none")
        if scope == "none":
            return
        final_output = str(
            (run.output_payload_json or {}).get("final_output")
            or (run.output_payload_json or {}).get("summary")
            or ""
        ).strip()
        if not final_output:
            return
        preferred_style = final_output[:400]
        past_decisions = (
            f"Task: {task.title if task else 'n/a'}\n"
            f"Mode: {run.run_mode}\n"
            f"Summary: {final_output[:800]}"
        )
        ttl_days = 30 if scope == "project-only" else 180
        status = "pending" if scope == "long-term" else "approved"
        for key, value_text in {
            "preferred_style": preferred_style,
            "past_decisions": past_decisions,
        }.items():
            memory = await self.repo.create_agent_memory(
                owner_id=agent.owner_id,
                agent_id=agent.id,
                project_id=run.project_id,
                source_run_id=run.id,
                key=key,
                value_text=value_text,
                scope=scope,
                status=status,
                ttl_days=ttl_days,
                expires_at=datetime.now(UTC) + timedelta(days=ttl_days),
                metadata_json={"task_id": task.id if task else None},
            )
            if scope == "long-term":
                await self.repo.create_approval(
                    project_id=run.project_id,
                    task_id=task.id if task else None,
                    run_id=run.id,
                    requested_by_user_id=run.triggered_by_user_id,
                    approval_type="agent_memory_write",
                    status="pending",
                    payload_json={"memory_entry_id": memory.id, "key": key, "value_text": value_text},
                )

    async def _assemble_user_context_packet(
        self,
        run: TaskRun,
        agent: AgentProfile | None,
        *,
        prefix: str | None = None,
    ) -> ContextPacket:
        task = await self.db.get(OrchestratorTask, run.task_id) if run.task_id else None
        project: OrchestratorProject | None = None
        project_name = ""
        project_goals = ""
        context_docs = ""
        recent_comments = ""
        recent_artifacts = ""
        if task:
            project = await self.db.get(OrchestratorProject, task.project_id)
            if project:
                project_name = project.name
                project_goals = project.goals_markdown
            context_docs = await self._build_project_knowledge_context(run, task)
            comments = await self.repo.list_task_comments(task.id)
            recent_comments = "\n".join(comment.body[:300] for comment in comments[-3:])
            artifacts = await self.repo.list_task_artifacts(task.id)
            recent_artifacts = "\n".join(
                f"{artifact.title}: {(artifact.content or '')[:300]}" for artifact in artifacts[:3]
            )
        agent_memory = await self._build_agent_memory_context(agent, run.project_id) if agent else ""
        scratchpad_summary, previous_run_diff = await self._build_run_scratchpad_context(run)
        replay = (run.input_payload_json or {}).get("orchestration_replay") if run.input_payload_json else None
        replay_block = ""
        if isinstance(replay, dict) and replay.get("prior_transcript"):
            replay_block = (
                "Replay context (carry forward from a previous run; continue without repeating completed steps):\n"
                f"{replay.get('prior_transcript')}"
            )
        wm_block = format_working_memory_for_prompt(working_memory_from_checkpoint(run.checkpoint_json))
        playbook_ex = await self._procedural_playbook_excerpt(project, task)
        proc_block = build_procedural_snippets(
            agent, task, project_playbooks_excerpt=playbook_ex
        )
        semantic_block = ""
        if task and project:
            semantic_block = await self._semantic_context_snippets_for_prompt(task, project)
        episodic_recall_block = ""
        deep_recall_block = ""
        if task and project:
            ms = merge_memory_settings(project.settings_json)
            depth = int(ms.get("episodic_retrieval_depth") or 8)
            cand = int(ms.get("deep_recall_episodic_candidates") or 24)
            q_title = (task.title or "")[:200]
            if ms.get("deep_recall_mode") and not settings.ORCHESTRATION_OFFLINE_MODE:
                try:
                    q_text = "\n".join(
                        [
                            task.title or "",
                            (task.description or "")[:500],
                            wm_block[:1200] if wm_block else "",
                        ]
                    ).strip()[:6000]
                    qv = (await self.ai_providers.embed_texts([q_text or q_title]))[0]
                    epi_vec = await self.repo.search_episodic_index_by_vector(
                        project.owner_id, project.id, qv, limit=min(cand, 40)
                    )
                    sem_vec = await self.repo.search_semantic_memory_by_vector(
                        project.owner_id, project.id, qv, limit=min(8, cand // 3)
                    )
                    lines_e = [f"- [episodic] {(r.text_content or '')[:320]}" for r in epi_vec[:cand]]
                    lines_s = [
                        f"- [semantic:{e.entry_type}] {e.title}: {(e.body or '')[:240]}"
                        for e in sem_vec[:8]
                    ]
                    deep_recall_block = "\n".join(lines_e + lines_s)
                except Exception as exc:
                    logger.warning("deep_recall_mode assembly failed: %s", exc)
            elif ms.get("second_stage_rag"):
                hits = await self.repo.search_episodic_for_project(
                    project.id, query=q_title or None, limit=min(depth, 24)
                )
                if hits:
                    lines = [f"- [{h['kind']}] {h['snippet'][:280]}" for h in hits[:depth]]
                    episodic_recall_block = "\n".join(lines)
        shared_bb, priv_bb = "", ""
        if task:
            aid = agent.id if agent else None
            shared_bb, priv_bb = extract_blackboard_sections(task.metadata_json, agent_id=aid)

        sections: dict[str, str] = {}
        if prefix:
            sections["prefix"] = prefix
        if agent:
            sections["agent_label"] = f"Agent: {agent.name}"
        if task:
            sections["task_title"] = f"Task title: {task.title}"
            if task.description:
                sections["task_description"] = f"Task description: {task.description}"
            if task.acceptance_criteria:
                sections["acceptance"] = f"Acceptance criteria: {task.acceptance_criteria}"
        if project_name:
            sections["project_name"] = f"Project name: {project_name}"
        if project_goals:
            sections["project_goals"] = f"Project goals: {project_goals}"
        if semantic_block:
            sections["semantic_memory"] = semantic_block
        if episodic_recall_block:
            sections["episodic_recall"] = f"Episodic recall (second stage):\n{episodic_recall_block}"
        if deep_recall_block:
            sections["deep_recall"] = f"Deep recall (vector episodic + semantic):\n{deep_recall_block}"
        if shared_bb:
            sections["shared_blackboard"] = f"Shared task blackboard:\n{shared_bb}"
        if priv_bb:
            sections["private_scratchpad"] = f"Private scratchpad (only this agent):\n{priv_bb}"
        if agent_memory:
            sections["agent_memory"] = f"Agent memory:\n{agent_memory}"
        if proc_block:
            sections["procedural_snippets"] = f"Procedural excerpts (task-scoped):\n{proc_block}"
        if context_docs:
            sections["knowledge"] = f"Additional context:\n{context_docs}"
        if recent_comments:
            sections["comments"] = f"Recent comments:\n{recent_comments}"
        if recent_artifacts:
            sections["artifacts"] = f"Recent artifacts:\n{recent_artifacts}"
        if scratchpad_summary:
            sections["scratchpad"] = f"Execution scratchpad:\n{scratchpad_summary}"
        if wm_block:
            sections["working_memory"] = f"Structured working memory:\n{wm_block}"
        if previous_run_diff:
            sections["previous_run"] = f"What changed since last run:\n{previous_run_diff}"
        if replay_block:
            sections["replay"] = replay_block
        if run.input_payload_json:
            sections["input_payload"] = f"Run input payload:\n{json.dumps(run.input_payload_json, indent=2)}"

        packet = ContextPacket(sections=sections)
        log_context_packet_telemetry(packet, run_id=run.id)
        return packet

    async def _build_task_prompt(
        self,
        run: TaskRun,
        agent: AgentProfile | None,
        *,
        prefix: str | None = None,
    ) -> str:
        packet = await self._assemble_user_context_packet(run, agent, prefix=prefix)
        return packet.combined_user_prompt()

    async def _load_agent_for_run(self, agent_id: str | None) -> AgentProfile | None:
        if not agent_id:
            return None
        return await self.db.get(AgentProfile, agent_id)

    def _is_agent_descendant(self, manager: AgentProfile, worker: AgentProfile) -> bool:
        return manager.id == worker.id or worker.parent_agent_id == manager.id

    async def get_agent_serialization(self, agent: AgentProfile) -> dict[str, Any]:
        payload = self._agent_model_to_payload(agent)
        inheritance = await self.resolve_agent_inheritance(agent)
        payload["inheritance"] = inheritance
        payload["skills"] = list(agent.skills_json or [])
        return payload

    async def resolve_agent_inheritance(self, agent: AgentProfile) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        template = None
        if agent.parent_template_slug:
            template = await self.repo.get_agent_template_by_slug(agent.parent_template_slug)
        inherited_fields: dict[str, Any] = {}
        if template is not None:
            inherited_fields = await self._resolve_template_effective_profile(template)
        effective = self._merge_agent_with_inheritance(agent, inherited_fields)
        overridden = self._compute_overridden_fields(agent, inherited_fields)
        return {
            "parent_template_slug": agent.parent_template_slug,
            "inherited_fields": inherited_fields,
            "overridden_fields": overridden,
            "effective": effective,
        }

    async def _snapshot_agent(self, agent: AgentProfile, user_id: str | None) -> None:
        snapshot = self._agent_model_to_payload(agent)
        await self.repo.create_agent_version(
            agent_profile_id=agent.id,
            version_number=agent.version,
            source_markdown=agent.source_markdown,
            snapshot_json=snapshot,
            created_by_user_id=user_id,
        )

    def _agent_payload_to_model(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {
            "project_id": payload.get("project_id"),
            "parent_agent_id": payload.get("parent_agent_id"),
            "reviewer_agent_id": payload.get("reviewer_agent_id"),
            "provider_config_id": payload.get("provider_config_id"),
            "parent_template_slug": payload.get("parent_template_slug"),
            "name": payload["name"],
            "slug": payload["slug"],
            "description": payload.get("description"),
            "role": payload.get("role", "specialist"),
            "system_prompt": payload.get("system_prompt", ""),
            "mission_markdown": payload.get("mission_markdown", ""),
            "rules_markdown": payload.get("rules_markdown", ""),
            "output_contract_markdown": payload.get("output_contract_markdown", ""),
            "source_markdown": payload.get("source_markdown", ""),
            "capabilities_json": payload.get("capabilities", []),
            "allowed_tools_json": payload.get("allowed_tools", []),
            "skills_json": payload.get("skills", []),
            "model_policy_json": payload.get("model_policy", {}),
            "visibility": payload.get("visibility", "private"),
            "is_active": payload.get("is_active", True),
            "tags_json": payload.get("tags", []),
            "budget_json": payload.get("budget", {}),
            "timeout_seconds": payload.get("timeout_seconds", 900),
            "retry_limit": payload.get("retry_limit", 1),
            "memory_policy_json": payload.get("memory_policy", {}),
            "output_schema_json": payload.get("output_schema", {}),
            "version": payload.get("version", 1),
            "metadata_json": {
                **payload.get("metadata", {}),
                "task_filters": payload.get("task_filters", []),
            },
        }

    def _agent_model_to_payload(self, agent: AgentProfile) -> dict[str, Any]:
        return {
            "project_id": agent.project_id,
            "parent_agent_id": agent.parent_agent_id,
            "reviewer_agent_id": agent.reviewer_agent_id,
            "provider_config_id": agent.provider_config_id,
            "parent_template_slug": agent.parent_template_slug,
            "name": agent.name,
            "slug": agent.slug,
            "description": agent.description,
            "role": agent.role,
            "system_prompt": agent.system_prompt,
            "mission_markdown": agent.mission_markdown,
            "rules_markdown": agent.rules_markdown,
            "output_contract_markdown": agent.output_contract_markdown,
            "source_markdown": agent.source_markdown,
            "capabilities_json": agent.capabilities_json,
            "allowed_tools_json": agent.allowed_tools_json,
            "skills_json": agent.skills_json,
            "model_policy_json": agent.model_policy_json,
            "visibility": agent.visibility,
            "is_active": agent.is_active,
            "tags_json": agent.tags_json,
            "budget_json": agent.budget_json,
            "timeout_seconds": agent.timeout_seconds,
            "retry_limit": agent.retry_limit,
            "memory_policy_json": agent.memory_policy_json,
            "output_schema_json": agent.output_schema_json,
            "version": agent.version,
            "metadata_json": agent.metadata_json,
        }

    def _apply_agent_updates(self, agent: AgentProfile, updates: dict[str, Any]) -> None:
        mapping = {
            "capabilities": "capabilities_json",
            "allowed_tools": "allowed_tools_json",
            "skills": "skills_json",
            "model_policy": "model_policy_json",
            "tags": "tags_json",
            "budget": "budget_json",
            "memory_policy": "memory_policy_json",
            "output_schema": "output_schema_json",
            "metadata": "metadata_json",
        }
        for field, value in updates.items():
            target = mapping.get(field, field)
            if hasattr(agent, target) and value is not None:
                setattr(agent, target, value)

    async def _ensure_catalog_seeded(self) -> None:
        existing_skills = await self.repo.list_skill_packs()
        existing_models = await self.repo.list_model_capabilities(active_only=False)

        existing_templates = await self.repo.list_agent_templates()

        existing_model_keys = {
            (item.provider_type, item.model_slug) for item in existing_models
        }
        for item in BUILTIN_MODEL_CAPABILITIES:
            key = (item["provider_type"], item["model_slug"])
            if key in existing_model_keys:
                continue
            await self.repo.create_model_capability(
                provider_type=item["provider_type"],
                model_slug=item["model_slug"],
                display_name=item.get("display_name"),
                supports_tools=bool(item.get("supports_tools", False)),
                supports_vision=bool(item.get("supports_vision", False)),
                max_context_tokens=int(item.get("max_context_tokens", 8192)),
                cost_per_1k_input=float(item.get("cost_per_1k_input", 0.0)),
                cost_per_1k_output=float(item.get("cost_per_1k_output", 0.0)),
                metadata_json=item.get("metadata", {}),
                is_active=True,
            )
        if not existing_skills or not existing_templates or len(existing_model_keys) != len(BUILTIN_MODEL_CAPABILITIES):
            await self.db.commit()

    async def _ensure_team_template_catalog_seeded(self) -> None:
        existing_templates = await self.repo.list_team_templates()
        if existing_templates:
            return

        await self.db.commit()

    async def _validate_and_normalize_agent_payload(
        self,
        user: User,
        payload: dict[str, Any],
        *,
        existing_agent_id: str | None,
    ) -> dict[str, Any]:
        await self._ensure_catalog_seeded()
        normalized = self._normalize_agent_payload_shape(payload)
        lint = await self.lint_agent_payload_detailed(
            user, normalized, existing_agent_id=existing_agent_id
        )
        if lint["errors"]:
            raise HTTPException(
                status_code=422,
                detail={"errors": lint["errors"], "warnings": lint["warnings"]},
            )
        return normalized

    async def lint_agent_payload(
        self,
        user: User,
        payload: dict[str, Any],
        *,
        existing_agent_id: str | None = None,
    ) -> list[str]:
        lint = await self.lint_agent_payload_detailed(
            user, payload, existing_agent_id=existing_agent_id
        )
        return lint["errors"]

    async def lint_agent_payload_detailed(
        self,
        user: User,
        payload: dict[str, Any],
        *,
        existing_agent_id: str | None = None,
    ) -> dict[str, list[str] | bool]:
        errors: list[str] = []
        warnings: list[str] = []
        allowed_tools = {
            "github_comment",
            "github_label_issue",
            "github_create_pr",
            "web_fetch",
            "web_search",
            "code_execute",
            "fs_read",
            "fs_write",
            "db_query",
            "repo_search",
        }
        for tool in payload.get("allowed_tools", []):
            if tool not in allowed_tools:
                errors.append(f"Tool '{tool}' is not available in the orchestration runtime.")

        skill_map = {skill.slug: skill for skill in await self.repo.list_skill_packs()}
        for skill_slug in payload.get("skills", []):
            if skill_slug not in skill_map:
                errors.append(f"Skill '{skill_slug}' is not defined.")

        parent_template_slug = payload.get("parent_template_slug")
        if parent_template_slug and await self.repo.get_agent_template_by_slug(parent_template_slug) is None:
            errors.append(f"Parent template '{parent_template_slug}' does not exist.")

        model_policy = payload.get("model_policy") or {}
        model_name = model_policy.get("model")
        fallback_model = model_policy.get("fallback_model")
        provider = None
        provider_config_id = payload.get("provider_config_id")
        if provider_config_id:
            provider = await self.repo.get_provider(user.id, provider_config_id)
            if provider is None:
                errors.append("Selected provider_config_id does not exist.")
        else:
            providers = await self.repo.list_providers(user.id, payload.get("project_id"))
            provider = next((item for item in providers if item.is_default), None) or (providers[0] if providers else None)
        if model_name and provider and not await self._provider_model_exists(provider, model_name):
            errors.append(
                f"Primary model '{model_name}' is not available on the selected/default provider."
            )
        if fallback_model and provider and not await self._provider_model_exists(provider, fallback_model):
            errors.append(
                f"Fallback model '{fallback_model}' is not available on the selected/default provider."
            )
        if model_name and provider:
            capability = await self._model_capability(model_name, provider.provider_type)
            if capability is None and provider.provider_type != "ollama":
                errors.append(f"Primary model '{model_name}' is missing from the capability matrix.")
        if fallback_model and provider:
            capability = await self._model_capability(fallback_model, provider.provider_type)
            if capability is None and provider.provider_type != "ollama":
                errors.append(f"Fallback model '{fallback_model}' is missing from the capability matrix.")

        budget = payload.get("budget") or {}
        token_budget = budget.get("token_budget")
        time_budget = budget.get("time_budget_seconds")
        retry_budget = budget.get("retry_budget")
        if token_budget is not None and (not isinstance(token_budget, (int, float)) or token_budget <= 0 or token_budget > 1_000_000):
            errors.append("budget.token_budget must be between 1 and 1,000,000.")
        if time_budget is not None and (not isinstance(time_budget, (int, float)) or time_budget < 10 or time_budget > 86_400):
            errors.append("budget.time_budget_seconds must be between 10 and 86400.")
        if retry_budget is not None and (not isinstance(retry_budget, (int, float)) or retry_budget < 0 or retry_budget > 20):
            errors.append("budget.retry_budget must be between 0 and 20.")
        cost_cap = budget.get("cost_cap_usd")
        if cost_cap is not None and (
            not isinstance(cost_cap, (int, float)) or float(cost_cap) <= 0 or float(cost_cap) > 50_000
        ):
            errors.append("budget.cost_cap_usd must be between 0 and 50000 (USD, rolling window).")

        task_filters = payload.get("task_filters") or payload.get("metadata", {}).get("task_filters", [])
        for value in task_filters:
            text = str(value).strip()
            if not text:
                continue
            if any(char in text for char in "^$[]().*+?{}\\|"):
                try:
                    re.compile(text)
                except re.error as exc:
                    errors.append(f"task_filter regex '{text}' is invalid: {exc}")

        memory_scope = (payload.get("memory_policy") or {}).get("scope")
        if memory_scope and memory_scope not in {"none", "project-only", "long-term"}:
            errors.append("memory_policy.scope must be one of: none, project-only, long-term.")

        output_format = (payload.get("output_schema") or {}).get("format")
        if output_format and output_format not in {"checklist", "json", "patch_proposal", "issue_reply", "adr"}:
            errors.append("output_schema.format is not supported.")

        permission_level = (payload.get("model_policy") or {}).get("permissions")
        if isinstance(permission_level, str) and permission_level not in {"read-only", "comment-only", "code-write", "merge-blocked"}:
            errors.append("permissions must be one of: read-only, comment-only, code-write, merge-blocked.")
        if not str(payload.get("description") or "").strip():
            warnings.append("Description is missing.")
        if not str(payload.get("mission_markdown") or "").strip():
            warnings.append("Mission section is missing.")
        if not str(payload.get("rules_markdown") or "").strip():
            warnings.append("Rules section is missing.")
        if not str(payload.get("output_contract_markdown") or "").strip():
            warnings.append("Output Contract section is missing.")
        if not payload.get("capabilities"):
            warnings.append("Capabilities are empty.")
        if not payload.get("allowed_tools"):
            warnings.append("Allowed tools are empty.")
        if not (payload.get("model_policy") or {}).get("model"):
            warnings.append("Primary model is not configured.")
        if not permission_level:
            warnings.append("Permissions are not configured.")
        if not memory_scope:
            warnings.append("Memory policy scope is not configured.")
        if budget.get("token_budget") is None:
            warnings.append("Token budget is not configured.")
        if budget.get("time_budget_seconds") is None:
            warnings.append("Time budget is not configured.")
        if not task_filters:
            warnings.append("Task filters are empty.")
        if not output_format:
            warnings.append("Output schema format is not configured.")
        if not (payload.get("model_policy") or {}).get("escalation_path"):
            warnings.append("Escalation path is not configured.")
        return {
            "errors": errors,
            "warnings": warnings,
            "activation_ready": not errors,
        }

    async def summarize_agent_lint(self, user: User, agent: AgentProfile) -> dict[str, Any]:
        payload = self._normalize_agent_payload_shape(self._agent_model_to_payload(agent))
        lint = await self.lint_agent_payload_detailed(user, payload, existing_agent_id=agent.id)
        return {
            "errors": list(lint["errors"]),
            "warnings": list(lint["warnings"]),
            "activation_ready": bool(lint["activation_ready"]),
        }

    def _normalize_agent_payload_shape(self, payload: dict[str, Any]) -> dict[str, Any]:
        normalized = dict(payload)
        if "skills_json" in normalized and "skills" not in normalized:
            normalized["skills"] = normalized["skills_json"]
        if "capabilities_json" in normalized and "capabilities" not in normalized:
            normalized["capabilities"] = normalized["capabilities_json"]
        if "allowed_tools_json" in normalized and "allowed_tools" not in normalized:
            normalized["allowed_tools"] = normalized["allowed_tools_json"]
        if "tags_json" in normalized and "tags" not in normalized:
            normalized["tags"] = normalized["tags_json"]
        if "model_policy_json" in normalized and "model_policy" not in normalized:
            normalized["model_policy"] = normalized["model_policy_json"]
        if "budget_json" in normalized and "budget" not in normalized:
            normalized["budget"] = normalized["budget_json"]
        if "memory_policy_json" in normalized and "memory_policy" not in normalized:
            normalized["memory_policy"] = normalized["memory_policy_json"]
        if "output_schema_json" in normalized and "output_schema" not in normalized:
            normalized["output_schema"] = normalized["output_schema_json"]
        if "metadata_json" in normalized and "metadata" not in normalized:
            normalized["metadata"] = normalized["metadata_json"]
        normalized["skills"] = [
            str(item).strip() for item in normalized.get("skills", []) if str(item).strip()
        ]
        normalized["capabilities"] = [
            str(item).strip()
            for item in normalized.get("capabilities", [])
            if str(item).strip()
        ]
        normalized["allowed_tools"] = [
            str(item).strip()
            for item in normalized.get("allowed_tools", [])
            if str(item).strip()
        ]
        normalized["tags"] = [
            str(item).strip() for item in normalized.get("tags", []) if str(item).strip()
        ]
        normalized["budget"] = normalized.get("budget") or {}
        normalized["memory_policy"] = normalized.get("memory_policy") or {}
        normalized["model_policy"] = normalized.get("model_policy") or {}
        normalized["output_schema"] = normalized.get("output_schema") or {}
        normalized["metadata"] = normalized.get("metadata") or {}
        return normalized

    async def _resolve_template_effective_profile(self, template: AgentTemplateCatalog) -> dict[str, Any]:
        inherited: dict[str, Any] = {}
        if template.parent_template_slug:
            parent = await self.repo.get_agent_template_by_slug(template.parent_template_slug)
            if parent is not None and parent.slug != template.slug:
                inherited = await self._resolve_template_effective_profile(parent)
        current_skills = list(template.skills_json or [])
        effective = {
            "system_prompt": template.system_prompt or inherited.get("system_prompt", ""),
            "mission_markdown": template.mission_markdown or inherited.get("mission_markdown", ""),
            "rules_markdown": "\n".join(
                chunk for chunk in [inherited.get("rules_markdown", ""), template.rules_markdown or ""] if chunk
            ),
            "output_contract_markdown": template.output_contract_markdown or inherited.get("output_contract_markdown", ""),
            "capabilities": self._merge_unique_lists(
                inherited.get("capabilities", []),
                template.capabilities_json or [],
            ),
            "allowed_tools": self._merge_unique_lists(
                inherited.get("allowed_tools", []),
                template.allowed_tools_json or [],
            ),
            "skills": self._merge_unique_lists(inherited.get("skills", []), current_skills),
            "tags": self._merge_unique_lists(inherited.get("tags", []), template.tags_json or []),
            "budget": {**inherited.get("budget", {}), **(template.budget_json or {})},
            "memory_policy": {**inherited.get("memory_policy", {}), **(template.memory_policy_json or {})},
            "output_schema": {**inherited.get("output_schema", {}), **(template.output_schema_json or {})},
            "model_policy": {**inherited.get("model_policy", {}), **(template.model_policy_json or {})},
            "metadata": {**inherited.get("metadata", {}), **(template.metadata_json or {})},
        }
        skill_map = {item.slug: item for item in await self.repo.list_skill_packs()}
        for skill_slug in effective["skills"]:
            skill = skill_map.get(skill_slug)
            if skill is None:
                continue
            effective["capabilities"] = self._merge_unique_lists(effective["capabilities"], skill.capabilities_json or [])
            effective["allowed_tools"] = self._merge_unique_lists(effective["allowed_tools"], skill.allowed_tools_json or [])
            effective["tags"] = self._merge_unique_lists(effective["tags"], skill.tags_json or [])
            if skill.rules_markdown:
                effective["rules_markdown"] = "\n".join(
                    chunk for chunk in [effective["rules_markdown"], skill.rules_markdown] if chunk
                )
        return effective

    def _merge_agent_with_inheritance(self, agent: AgentProfile, inherited: dict[str, Any]) -> dict[str, Any]:
        effective = {
            "system_prompt": agent.system_prompt or inherited.get("system_prompt", ""),
            "mission_markdown": agent.mission_markdown or inherited.get("mission_markdown", ""),
            "rules_markdown": "\n".join(
                chunk for chunk in [inherited.get("rules_markdown", ""), agent.rules_markdown or ""] if chunk
            ),
            "output_contract_markdown": agent.output_contract_markdown or inherited.get("output_contract_markdown", ""),
            "capabilities": self._merge_unique_lists(inherited.get("capabilities", []), agent.capabilities_json or []),
            "allowed_tools": self._merge_unique_lists(inherited.get("allowed_tools", []), agent.allowed_tools_json or []),
            "skills": self._merge_unique_lists(inherited.get("skills", []), agent.skills_json or []),
            "tags": self._merge_unique_lists(inherited.get("tags", []), agent.tags_json or []),
            "budget": {**inherited.get("budget", {}), **(agent.budget_json or {})},
            "memory_policy": {**inherited.get("memory_policy", {}), **(agent.memory_policy_json or {})},
            "output_schema": {**inherited.get("output_schema", {}), **(agent.output_schema_json or {})},
            "model_policy": {**inherited.get("model_policy", {}), **(agent.model_policy_json or {})},
        }
        return effective

    def _compute_overridden_fields(self, agent: AgentProfile, inherited: dict[str, Any]) -> dict[str, Any]:
        explicit_fields = {
            "capabilities": list(agent.capabilities_json or []),
            "allowed_tools": list(agent.allowed_tools_json or []),
            "skills": list(agent.skills_json or []),
            "tags": list(agent.tags_json or []),
            "rules_markdown": agent.rules_markdown or "",
            "memory_policy": dict(agent.memory_policy_json or {}),
            "output_schema": dict(agent.output_schema_json or {}),
            "budget": dict(agent.budget_json or {}),
            "model_policy": dict(agent.model_policy_json or {}),
        }
        overrides = {}
        for key, value in explicit_fields.items():
            if not value:
                continue
            if value != inherited.get(key):
                overrides[key] = value
        return overrides

    def _merge_unique_lists(self, base: list[str], extra: list[str]) -> list[str]:
        merged: list[str] = []
        for value in [*base, *extra]:
            text = str(value).strip()
            if text and text not in merged:
                merged.append(text)
        return merged

    def _template_model_to_payload(self, template: AgentTemplateCatalog) -> dict[str, Any]:
        return {
            "id": template.id,
            "slug": template.slug,
            "name": template.name,
            "role": template.role,
            "description": template.description or "",
            "parent_template_slug": template.parent_template_slug,
            "system_prompt": template.system_prompt,
            "mission_markdown": template.mission_markdown,
            "rules_markdown": template.rules_markdown,
            "output_contract_markdown": template.output_contract_markdown,
            "capabilities": list(template.capabilities_json or []),
            "allowed_tools": list(template.allowed_tools_json or []),
            "skills": list(template.skills_json or []),
            "tags": list(template.tags_json or []),
            "model_policy": dict(template.model_policy_json or {}),
            "budget": dict(template.budget_json or {}),
            "memory_policy": dict(template.memory_policy_json or {}),
            "output_schema": dict(template.output_schema_json or {}),
            "metadata": dict(template.metadata_json or {}),
        }

    def _skill_model_to_payload(self, skill: SkillPack) -> dict[str, Any]:
        return {
            "id": skill.id,
            "slug": skill.slug,
            "name": skill.name,
            "description": skill.description,
            "capabilities": list(skill.capabilities_json or []),
            "allowed_tools": list(skill.allowed_tools_json or []),
            "rules_markdown": skill.rules_markdown,
            "tags": list(skill.tags_json or []),
        }

    def _team_template_model_to_payload(self, template: TeamTemplateCatalog) -> dict[str, Any]:
        return {
            "id": template.id,
            "slug": template.slug,
            "name": template.name,
            "description": template.description or "",
            "outcome": template.outcome,
            "roles": list(template.roles_json or []),
            "tools": list(template.tools_json or []),
            "autonomy": template.autonomy,
            "visibility": template.visibility,
            "agent_template_slugs": list(template.agent_template_slugs_json or []),
        }

    async def _ensure_unique_agent_slug(
        self, owner_id: str, slug: str, existing_id: str | None
    ) -> None:
        existing = await self.repo.get_agent_by_slug(owner_id, slug)
        if existing and existing.id != existing_id:
            raise HTTPException(status_code=409, detail="An agent with this slug already exists")

    async def _generate_duplicate_slug(self, owner_id: str, base_slug: str) -> str:
        for index in range(2, 100):
            candidate = f"{base_slug}-{index}"
            if await self.repo.get_agent_by_slug(owner_id, candidate) is None:
                return candidate
        raise HTTPException(status_code=409, detail="Could not generate duplicate slug")

    async def _fetch_github_login(self, api_url: str, token: str) -> str:
        async with httpx.AsyncClient(timeout=30.0, base_url=api_url) as client:
            response = await client.get("/user", headers={"Authorization": f"Bearer {token}"})
        if response.status_code >= 400:
            raise HTTPException(status_code=422, detail="Failed to validate GitHub token")
        return response.json()["login"]

    def _github_connection_mode(self, connection: GithubConnection) -> str:
        return str((connection.metadata_json or {}).get("connection_mode") or "token")

    def _github_app_jwt(self) -> str:
        if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
            raise HTTPException(status_code=503, detail="GitHub App credentials are not configured")
        now = int(time.time())
        return jwt.encode(
            {"iat": now - 60, "exp": now + 540, "iss": settings.GITHUB_APP_ID},
            settings.GITHUB_APP_PRIVATE_KEY,
            algorithm="RS256",
        )

    async def _github_app_get_installation(
        self, installation_id: int, *, api_url: str = "https://api.github.com"
    ) -> dict[str, Any]:
        async with httpx.AsyncClient(timeout=30.0, base_url=api_url) as client:
            response = await client.get(
                f"/app/installations/{installation_id}",
                headers={
                    "Authorization": f"Bearer {self._github_app_jwt()}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to read GitHub App installation")
        return response.json()

    async def _github_installation_token(self, connection: GithubConnection) -> str:
        installation_id = int((connection.metadata_json or {}).get("installation_id") or 0)
        if installation_id <= 0:
            raise HTTPException(status_code=422, detail="GitHub App connection is missing installation_id")
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
            response = await client.post(
                f"/app/installations/{installation_id}/access_tokens",
                headers={
                    "Authorization": f"Bearer {self._github_app_jwt()}",
                    "Accept": "application/vnd.github+json",
                },
            )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to mint GitHub installation token")
        return str(response.json()["token"])

    async def _github_auth_headers(self, connection: GithubConnection) -> dict[str, str]:
        token = (
            await self._github_installation_token(connection)
            if self._github_connection_mode(connection) == "github_app"
            else decrypt_secret(connection.encrypted_token)
        )
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    async def _github_request(
        self,
        connection: GithubConnection,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        json_body: dict[str, Any] | None = None,
    ) -> httpx.Response:
        headers = await self._github_auth_headers(connection)
        async with httpx.AsyncClient(timeout=30.0, base_url=connection.api_url) as client:
            return await client.request(method, path, headers=headers, params=params, json=json_body)

    async def _list_github_repositories(self, connection: GithubConnection) -> list[dict[str, Any]]:
        if self._github_connection_mode(connection) == "github_app":
            response = await self._github_request(
                connection,
                "GET",
                "/installation/repositories",
                params={"per_page": 100},
            )
            if response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Failed to fetch GitHub repositories")
            return list((response.json() or {}).get("repositories", []))
        response = await self._github_request(
            connection,
            "GET",
            "/user/repos",
            params={"per_page": 100, "sort": "updated"},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub repositories")
        return response.json()

    async def _fetch_github_issues(
        self,
        connection: GithubConnection,
        repository,
        issue_numbers: list[int],
    ) -> list[dict[str, Any]]:
        if issue_numbers:
            issues = []
            for issue_number in issue_numbers:
                response = await self._github_request(
                    connection,
                    "GET",
                    f"/repos/{repository.full_name}/issues/{issue_number}",
                )
                if response.status_code >= 400:
                    raise HTTPException(status_code=502, detail=f"Failed to fetch issue #{issue_number}")
                issues.append(response.json())
            return issues
        response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/issues",
            params={"state": "open", "per_page": 100},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to fetch GitHub issues")
        return [item for item in response.json() if "pull_request" not in item]

    async def _post_approved_github_comment(self, approval: ApprovalRequest) -> None:
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id)
        if issue_link is None:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        if repository is None:
            raise HTTPException(status_code=404, detail="Repository not found")
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None:
            raise HTTPException(status_code=404, detail="Connection not found")
        payload = approval.payload_json
        comment_body = payload.get("body") or payload.get("draft_comment")
        if not comment_body:
            raise HTTPException(status_code=422, detail="Approval payload does not include a comment body")
        response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/issues/{issue_link.issue_number}/comments",
            json_body={"body": comment_body},
        )
        if response.status_code >= 400:
            raise HTTPException(status_code=502, detail="Failed to post GitHub comment")
        if payload.get("close_issue"):
            close_response = await self._github_request(
                connection,
                "PATCH",
                f"/repos/{repository.full_name}/issues/{issue_link.issue_number}",
                json_body={"state": "closed"},
            )
            if close_response.status_code >= 400:
                raise HTTPException(status_code=502, detail="Failed to close GitHub issue")
        issue_link.last_comment_posted_at = datetime.now(UTC)
        issue_link.last_synced_at = datetime.now(UTC)
        if payload.get("close_issue"):
            issue_link.state = "closed"
        if approval.task_id:
            task = await self.db.get(OrchestratorTask, approval.task_id)
            if task and task.status == "approved":
                await self._transition_task_status(task, "completed", reason="approved for external sync")
            if task and task.status == "completed":
                await self._transition_task_status(task, "synced_to_github", reason="github comment posted")
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="post_comment",
            status="completed",
            detail="Approved comment posted to GitHub.",
            payload_json={**payload, "body": comment_body},
        )

    async def _approve_github_create_pr(self, approval: ApprovalRequest) -> None:
        payload = approval.payload_json or {}
        run_id = payload.get("run_id")
        task_id = approval.task_id or payload.get("task_id")
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id) if approval.issue_link_id else None
        if not run_id or not task_id or issue_link is None:
            raise HTTPException(status_code=422, detail="PR approval payload is incomplete")
        run = await self.db.get(TaskRun, str(run_id))
        task = await self.db.get(OrchestratorTask, str(task_id))
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        if run is None or task is None or repository is None:
            raise HTTPException(status_code=404, detail="PR approval target could not be resolved")
        await self._create_github_pr_for_run(run, task, repository, issue_link)

    async def _approve_github_pr_review_comment(self, approval: ApprovalRequest) -> None:
        payload = approval.payload_json or {}
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id) if approval.issue_link_id else None
        if issue_link is None:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        connection = await self.db.get(GithubConnection, repository.connection_id) if repository else None
        pr_number = payload.get("pr_number")
        body = str(payload.get("body") or "").strip()
        if connection is None or repository is None or not pr_number or not body:
            raise HTTPException(status_code=422, detail="PR review approval payload is incomplete")
        response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/pulls/{pr_number}/reviews",
            json_body={"body": body[:5000], "event": "COMMENT"},
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="post_pr_review",
            status="completed" if response.status_code < 400 else "failed",
            detail=f"Approved reviewer PR comment posted on #{pr_number}."
            if response.status_code < 400
            else "Failed to post approved reviewer PR comment.",
            payload_json=payload,
        )

    async def _approve_github_issue_sync(self, approval: ApprovalRequest) -> None:
        issue_link = await self.db.get(GithubIssueLink, approval.issue_link_id) if approval.issue_link_id else None
        if issue_link is None:
            raise HTTPException(status_code=404, detail="Issue link not found")
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        connection = await self.db.get(GithubConnection, repository.connection_id) if repository else None
        payload = dict(approval.payload_json or {})
        body = dict(payload.get("issue_update") or {})
        if repository is None or connection is None or not body:
            raise HTTPException(status_code=422, detail="GitHub issue sync approval payload is incomplete")
        response = await self._github_request(
            connection,
            "PATCH",
            f"/repos/{repository.full_name}/issues/{issue_link.issue_number}",
            json_body=body,
        )
        if response.status_code < 400:
            issue_link.last_synced_at = datetime.now(UTC)
            if "state" in body:
                issue_link.state = str(body["state"])
            if "labels" in body and isinstance(body["labels"], list):
                issue_link.labels_json = [str(item) for item in body["labels"]]
            if "assignees" in body:
                assignees = body.get("assignees") or []
                issue_link.assignee_login = str(assignees[0]) if assignees else None
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="sync_issue_fields",
            status="completed" if response.status_code < 400 else "failed",
            detail="Approved internal task changes synced back to GitHub."
            if response.status_code < 400
            else "Failed to sync internal task changes back to GitHub.",
            payload_json=payload,
        )

    def validate_github_webhook_signature(self, body: bytes, signature: str | None) -> bool:
        if not settings.GITHUB_APP_WEBHOOK_SECRET:
            return False
        if not signature or not signature.startswith("sha256="):
            return False
        expected = "sha256=" + hmac.new(
            settings.GITHUB_APP_WEBHOOK_SECRET.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()
        return hmac.compare_digest(expected, signature)

    async def record_github_webhook_event(self, event_name: str, payload: dict[str, Any]) -> str:
        repository = payload.get("repository") or {}
        repo_model = None
        if repository.get("full_name"):
            repo_model = await self.repo.get_github_repository_by_full_name(repository["full_name"])
        issue_link = None
        issue_number = int(((payload.get("issue") or {}).get("number")) or ((payload.get("pull_request") or {}).get("number")) or 0)
        if repo_model and issue_number:
            issue_link = await self.repo.get_issue_link_by_repo_and_number(repo_model.id, issue_number)
        sync_event = await self.repo.create_sync_event(
            repository_id=repo_model.id if repo_model else None,
            issue_link_id=issue_link.id if issue_link else None,
            action=f"webhook.{event_name}.{payload.get('action')}",
            status="queued",
            detail=f"Queued GitHub webhook {event_name}.{payload.get('action')}",
            payload_json=payload,
        )
        await self.db.commit()
        return sync_event.id

    async def process_github_webhook_sync_event(self, sync_event_id: str) -> None:
        sync_event = await self.repo.get_sync_event(sync_event_id)
        if sync_event is None:
            raise RuntimeError("GitHub sync event not found")
        payload = sync_event.payload_json or {}
        if sync_event.action == "webhook.issues.opened":
            await self._process_webhook_issue_opened(sync_event, payload)
        elif sync_event.action == "webhook.issues.assigned":
            await self._process_webhook_issue_assigned(sync_event, payload)
        elif sync_event.action.startswith("webhook.issues."):
            await self._process_webhook_issue_changed(sync_event, payload)
        elif sync_event.action == "webhook.issue_comment.created":
            await self._process_webhook_issue_comment(sync_event, payload)
        elif sync_event.action == "webhook.pull_request.opened":
            await self._process_webhook_pull_request_opened(sync_event, payload)
        elif sync_event.action == "webhook.pull_request_review.submitted":
            await self._process_webhook_pull_request_review(sync_event, payload)
        elif sync_event.action == "webhook.pull_request.closed" and (payload.get("pull_request") or {}).get("merged"):
            await self._process_webhook_pull_request_merged(sync_event, payload)
        elif sync_event.action.startswith("webhook.projects_v2_item."):
            await self._process_webhook_projects_v2_item(sync_event, payload)
        else:
            sync_event.status = "ignored"
            sync_event.detail = f"No handler for {sync_event.action}"
        await self.db.commit()

    async def _process_webhook_projects_v2_item(self, sync_event, payload: dict[str, Any]) -> None:
        sync_event.status = "ignored"
        sync_event.detail = (
            "GitHub Projects (classic/v2) board sync is not implemented yet; event was recorded for auditing."
        )
        sync_event.payload_json = {
            "projects_v2_stub": True,
            "action": payload.get("action"),
            "projects_v2_node_id": (payload.get("projects_v2_item") or {}).get("node_id"),
        }

    async def _owner_id_for_repository(self, repository: GithubRepository) -> str:
        connection = await self.db.get(GithubConnection, repository.connection_id)
        if connection is None:
            raise RuntimeError("GitHub repository connection is missing")
        return connection.owner_id

    async def _ensure_repository_from_webhook_payload(self, payload: dict[str, Any]) -> GithubRepository | None:
        repository = payload.get("repository") or {}
        full_name = repository.get("full_name")
        if not full_name:
            return None
        repo_model = await self.repo.get_github_repository_by_full_name(full_name)
        if repo_model:
            repo_model.metadata_json = repository
            return repo_model
        installation_id = int(((payload.get("installation") or {}).get("id")) or 0)
        if installation_id <= 0:
            return None
        result = await self.db.execute(
            select(GithubConnection).where(
                GithubConnection.metadata_json["installation_id"].as_integer() == installation_id
            )
        )
        connection = result.scalar_one_or_none()
        if connection is None:
            return None
        return await self.repo.create_github_repository(
            connection_id=connection.id,
            project_id=None,
            owner_name=(repository.get("owner") or {}).get("login") or "",
            repo_name=repository.get("name") or "",
            full_name=full_name,
            default_branch=repository.get("default_branch"),
            repo_url=repository.get("html_url"),
            metadata_json=repository,
        )

    async def _process_webhook_issue_opened(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        if repository is None or repository.project_id is None:
            sync_event.status = "ignored"
            sync_event.detail = "Repository is not linked to an orchestration project."
            return
        owner_id = await self._owner_id_for_repository(repository)
        project = await self.db.get(OrchestratorProject, repository.project_id)
        repo_pool = self._repo_pool_config(project, repository=repository)
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        if link is None:
            link = await self.repo.create_issue_link(
                repository_id=repository.id,
                issue_number=int(issue["number"]),
                title=issue.get("title") or "",
                body=issue.get("body"),
                state=issue.get("state") or "open",
                labels_json=[item["name"] for item in issue.get("labels", [])],
                assignee_login=((issue.get("assignee") or {}).get("login")),
                issue_url=issue.get("html_url"),
                sync_status="synced",
                last_synced_at=datetime.now(UTC),
                metadata_json=issue,
            )
        if link.task_id is None:
            task = await self.repo.create_task(
                project_id=repository.project_id,
                created_by_user_id=owner_id,
                assigned_agent_id=str(repo_pool.get("default_assignee_agent_id") or "").strip() or None,
                reviewer_agent_id=str(repo_pool.get("default_reviewer_agent_id") or "").strip() or None,
                title=(issue.get("title") or "GitHub issue")[:255],
                description=issue.get("body"),
                source="github",
                task_type="github_issue",
                priority="normal",
                status="backlog",
                acceptance_criteria=None,
                due_date=None,
                labels_json=[item["name"] for item in issue.get("labels", [])],
                result_payload_json={},
                metadata_json={
                    "github_issue_number": issue.get("number"),
                    "github_milestone_number": ((issue.get("milestone") or {}).get("number")),
                },
                position=await self.repo.get_next_task_position(repository.project_id),
            )
            task.github_issue_link_id = link.id
            link.task_id = task.id
        sync_event.issue_link_id = link.id
        sync_event.status = "completed"
        sync_event.detail = f"Issue #{issue['number']} mirrored into an orchestration task."

    async def _process_webhook_issue_assigned(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        assignee_login = ((payload.get("assignee") or {}).get("login")) or ((issue.get("assignee") or {}).get("login"))
        if link is None or link.task_id is None or not assignee_login:
            sync_event.status = "ignored"
            sync_event.detail = "No linked task or assignee mapping available."
            return
        owner_id = await self._owner_id_for_repository(repository)
        project = await self.db.get(OrchestratorProject, repository.project_id) if repository.project_id else None
        repo_pool = self._repo_pool_config(project, repository=repository)
        assignee_map = dict(repo_pool.get("github_assignee_map") or {})
        mapped = assignee_map.get(assignee_login)
        agent = None
        if mapped:
            mapped_text = str(mapped).strip()
            agent = await self._load_agent_for_run(mapped_text)
            if agent is None:
                agent = await self.repo.get_agent_by_slug(owner_id, mapped_text)
        if agent is None:
            agent = await self.repo.get_agent_by_slug(owner_id, assignee_login)
        if agent is None:
            sync_event.status = "ignored"
            sync_event.detail = f"No agent slug matches GitHub assignee '{assignee_login}'."
            return
        task = await self.db.get(OrchestratorTask, link.task_id)
        if task is None:
            sync_event.status = "ignored"
            return
        task.assigned_agent_id = agent.id
        link.assignee_login = assignee_login
        sync_event.status = "completed"
        sync_event.detail = f"Issue #{issue['number']} assigned to agent {agent.slug}."
        sync_event.payload_json = {**payload, "agent_id": agent.id}

    async def _process_webhook_issue_changed(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        if link is None:
            sync_event.status = "ignored"
            sync_event.detail = "Issue link does not exist yet."
            return
        link.title = str(issue.get("title") or link.title)[:255]
        link.body = issue.get("body") or link.body
        link.state = str(issue.get("state") or link.state)
        link.labels_json = [item["name"] for item in issue.get("labels", []) if isinstance(item, dict)]
        link.assignee_login = ((issue.get("assignee") or {}).get("login"))
        link.issue_url = issue.get("html_url") or link.issue_url
        link.last_synced_at = datetime.now(UTC)
        link.metadata_json = {**(link.metadata_json or {}), "last_webhook_issue": issue}
        task = await self.db.get(OrchestratorTask, link.task_id) if link.task_id else None
        if task is not None:
            task.labels_json = list(link.labels_json or [])
            meta = dict(task.metadata_json or {})
            meta["github_milestone_number"] = ((issue.get("milestone") or {}).get("number"))
            task.metadata_json = meta
            orm_attributes.flag_modified(task, "metadata_json")
            if link.state == "closed" and task.status not in {"completed", "synced_to_github", "archived"}:
                await self._transition_task_status(task, "synced_to_github", reason="github issue closed")
            elif link.state == "open" and task.status == "synced_to_github":
                await self._transition_task_status(task, "planned", reason="github issue reopened")
        sync_event.status = "completed"
        sync_event.detail = f"Issue #{issue['number']} metadata synced from GitHub."

    async def _enqueue_github_pr_review_run(
        self,
        task: OrchestratorTask,
        project: OrchestratorProject,
        *,
        review: dict[str, Any],
        pr: dict[str, Any],
    ) -> None:
        gh = (project.settings_json or {}).get("github") or {}
        if not bool(gh.get("auto_review_on_pr_review")):
            return
        if await self.repo.task_has_active_run(task.project_id, task.id):
            return
        reviewer_id = task.reviewer_agent_id
        if not reviewer_id:
            execution = (project.settings_json or {}).get("execution") or {}
            rids = execution.get("reviewer_agent_ids") or []
            reviewer_id = rids[0] if isinstance(rids, list) and rids else None
        if not reviewer_id:
            return
        author_login = ((review.get("user") or {}).get("login") if isinstance(review.get("user"), dict) else None)
        run = await self.repo.create_run(
            project_id=task.project_id,
            task_id=task.id,
            triggered_by_user_id=project.owner_id,
            orchestrator_agent_id=None,
            worker_agent_id=task.assigned_agent_id,
            reviewer_agent_id=reviewer_id,
            provider_config_id=(project.settings_json or {}).get("execution", {}).get("provider_config_id"),
            run_mode="review",
            status="queued",
            model_name=(project.settings_json or {}).get("execution", {}).get("model_name"),
            input_payload_json={
                "github_pr_review": {
                    "state": str(review.get("state") or "commented").lower(),
                    "author_login": author_login,
                    "body": review.get("body"),
                    "pr_number": pr.get("number"),
                },
            },
        )
        await self._emit_run_event(
            run,
            event_type="queued",
            message="Review run queued from GitHub PR review webhook.",
            payload={"trigger": "github_pr_review"},
        )
        await self.db.commit()
        from backend.modules.orchestration.durable_execution import submit_orchestration_run

        submit_orchestration_run(run.id)

    async def _process_webhook_issue_comment(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        issue = payload.get("issue") or {}
        comment = payload.get("comment") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(issue["number"]))
        if link is None or link.task_id is None:
            sync_event.status = "ignored"
            return
        cid = comment.get("id")
        thread_marker = f"<!--gh:comment_id={cid}-->" if cid else ""
        in_reply = comment.get("in_reply_to_id")
        reply_line = f"\n[in_reply_to={in_reply}]" if in_reply else ""
        await self.repo.create_task_comment(
            task_id=link.task_id,
            author_user_id=None,
            author_agent_id=None,
            body=(
                f"{thread_marker}\n[GitHub @{(comment.get('user') or {}).get('login') or 'unknown'}] "
                f"{comment.get('body') or ''}{reply_line}"
            ).strip(),
        )
        sync_event.status = "completed"
        sync_event.detail = f"GitHub comment appended to task thread for issue #{issue['number']}."

    async def _process_webhook_pull_request_opened(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            task = await self.db.get(OrchestratorTask, issue_link.task_id)
            project = await self.db.get(OrchestratorProject, task.project_id) if task else None
            if task:
                task.result_payload_json = {
                    **(task.result_payload_json or {}),
                    "github_pr": {
                        "number": pr.get("number"),
                        "url": pr.get("html_url"),
                        "state": pr.get("state"),
                        "head": ((pr.get("head") or {}).get("ref")),
                        "base": ((pr.get("base") or {}).get("ref")),
                        "commits": pr.get("commits"),
                        "head_sha": ((pr.get("head") or {}).get("sha")),
                    },
                }
                if project and self._project_github_settings(project).get("enforce_branch_naming", True):
                    branch_name = (pr.get("head") or {}).get("ref")
                    if not self._github_branch_name_valid_for_task(project, task, branch_name):
                        await self.repo.create_task_comment(
                            task_id=task.id,
                            author_user_id=None,
                            author_agent_id=None,
                            body=(
                                f"[GitHub branch policy] Expected `{self._github_branch_name_for_task(project, task)}` "
                                f"but received `{branch_name}`."
                            ),
                        )
                        await self.repo.create_sync_event(
                            repository_id=repository.id,
                            issue_link_id=issue_link.id,
                            action="branch_policy_violation",
                            status="failed",
                            detail="Opened PR branch does not match the project's naming convention.",
                            payload_json={"branch": branch_name, "expected": self._github_branch_name_for_task(project, task)},
                        )
                if project and self._project_github_settings(project).get("auto_activate_review_on_pr_open", True):
                    await self._enqueue_github_pr_review_run(
                        task,
                        project,
                        review={"state": "commented", "body": "PR opened"},
                        pr=pr,
                    )
        sync_event.status = "completed"
        sync_event.detail = f"Pull request #{pr['number']} opened."

    async def _process_webhook_pull_request_review(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        review = payload.get("review") or {}
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            rid = review.get("id")
            thread_marker = f"<!--gh:review_id={rid}-->" if rid else ""
            await self.repo.create_task_comment(
                task_id=issue_link.task_id,
                author_user_id=None,
                author_agent_id=None,
                body=(
                    f"{thread_marker}\n[GitHub PR review] {(review.get('state') or 'commented').upper()}: "
                    f"{review.get('body') or ''}"
                ).strip(),
            )
            task = await self.db.get(OrchestratorTask, issue_link.task_id)
            project = await self.db.get(OrchestratorProject, task.project_id) if task else None
            if task and project:
                await self._enqueue_github_pr_review_run(task, project, review=review, pr=pr)
        sync_event.status = "completed"
        sync_event.detail = f"Pull request review received for PR #{pr['number']}."

    async def _process_webhook_pull_request_merged(self, sync_event, payload: dict[str, Any]) -> None:
        repository = await self._ensure_repository_from_webhook_payload(payload)
        pr = payload.get("pull_request") or {}
        if repository is None:
            sync_event.status = "ignored"
            return
        issue_link = await self.repo.get_issue_link_by_repo_and_number(repository.id, int(pr["number"]))
        if issue_link and issue_link.task_id:
            task = await self.db.get(OrchestratorTask, issue_link.task_id)
            if task:
                task.result_payload_json = {
                    **(task.result_payload_json or {}),
                    "github_pr": {
                        **((task.result_payload_json or {}).get("github_pr") or {}),
                        "number": pr.get("number"),
                        "url": pr.get("html_url"),
                        "state": "merged",
                        "merge_commit_sha": pr.get("merge_commit_sha"),
                    },
                }
                if task.status in {"approved", "completed", "synced_to_github"}:
                    await self._transition_task_status(task, "synced_to_github", reason="pull request merged")
        sync_event.status = "completed"
        sync_event.detail = f"Pull request #{pr['number']} merged."

    async def _sync_run_completion_to_github(self, run: TaskRun, task: OrchestratorTask) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        if repository is None:
            return
        project = await self.db.get(OrchestratorProject, task.project_id)
        github_settings = self._project_github_settings(project)
        progress_note = (
            str(run.output_payload_json.get("summary") or run.output_payload_json.get("final_output") or task.result_summary or "")
        )[:2000]
        auto_post_progress = bool(github_settings.get("auto_post_progress", False))
        if auto_post_progress:
            await self._create_github_write_approval(
                user_id=run.triggered_by_user_id,
                project_id=task.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=issue_link.id,
                approval_type="github_progress_comment",
                payload_json={
                    "body": progress_note,
                    "close_issue": False,
                    "repository_id": repository.id,
                    "issue_number": issue_link.issue_number,
                    "run_id": run.id,
                    "agent_id": run.worker_agent_id or run.orchestrator_agent_id,
                },
            )
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="agent_progress_comment_pending",
                status="pending",
                detail="Agent produced a GitHub progress note draft pending approval.",
                payload_json={"run_id": run.id, "body": progress_note, "agent_id": run.worker_agent_id or run.orchestrator_agent_id},
            )
        if (
            github_settings.get("close_issue_with_manager_summary", True)
            and run.run_mode == "manager_worker"
            and task.status in {"completed", "approved", "synced_to_github"}
        ):
            final_summary = str(run.output_payload_json.get("final_output") or progress_note)[:5000]
            await self._create_github_write_approval(
                user_id=run.triggered_by_user_id,
                project_id=task.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=issue_link.id,
                approval_type="github_manager_closure",
                payload_json={
                    "body": final_summary,
                    "close_issue": True,
                    "repository_id": repository.id,
                    "issue_number": issue_link.issue_number,
                    "run_id": run.id,
                },
            )
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="manager_closure_summary_pending",
                status="pending",
                detail="Manager generated a final issue closure summary pending approval.",
                payload_json={"run_id": run.id},
            )
        if bool(run.input_payload_json.get("create_pr")):
            await self._create_github_write_approval(
                user_id=run.triggered_by_user_id,
                project_id=task.project_id,
                task_id=task.id,
                run_id=run.id,
                issue_link_id=issue_link.id,
                approval_type="github_create_pr",
                payload_json={
                    "run_id": run.id,
                    "task_id": task.id,
                    "draft_pr": bool(run.input_payload_json.get("draft_pr", github_settings.get("draft_prs_by_default", True))),
                },
            )
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_pr_pending",
                status="pending",
                detail="Agent drafted a PR proposal pending approval.",
                payload_json={"run_id": run.id, "task_id": task.id},
            )

    def _github_branch_name_for_task(self, project: OrchestratorProject | None, task: OrchestratorTask) -> str:
        template = ((project.settings_json or {}).get("github", {}) if project else {}).get(
            "branch_prefix", "troop/{task_id}-{slug}"
        )
        branch = str(template).format(task_id=task.id, slug=self._slugify(task.title))
        branch = branch.replace("//", "/").strip("/")
        return branch[:120]

    def _github_branch_name_valid_for_task(
        self, project: OrchestratorProject | None, task: OrchestratorTask, branch_name: str | None
    ) -> bool:
        expected = self._github_branch_name_for_task(project, task)
        actual = str(branch_name or "").strip().strip("/")
        if not actual:
            return False
        return actual == expected

    def _task_state_to_github_issue_state(self, task: OrchestratorTask) -> str:
        return "closed" if task.status in {"approved", "completed", "synced_to_github", "archived"} else "open"

    async def _task_assignee_login_for_github(
        self, task: OrchestratorTask, project: OrchestratorProject | None
    ) -> str | None:
        if not task.assigned_agent_id:
            return None
        repo_pool = await self._task_repo_pool_config(task)
        assignee_map = dict(repo_pool.get("github_assignee_map") or {})
        if task.assigned_agent_id in assignee_map:
            return str(assignee_map[task.assigned_agent_id]).strip() or None
        agent = await self._load_agent_for_run(task.assigned_agent_id)
        if agent and agent.slug:
            return agent.slug
        return None

    async def _create_github_write_approval(
        self,
        *,
        user_id: str | None,
        project_id: str | None,
        task_id: str | None,
        run_id: str | None,
        issue_link_id: str | None,
        approval_type: str,
        payload_json: dict[str, Any],
    ) -> ApprovalRequest:
        approval = await self.repo.create_approval(
            project_id=project_id,
            task_id=task_id,
            run_id=run_id,
            issue_link_id=issue_link_id,
            requested_by_user_id=user_id,
            approval_type=approval_type,
            status="pending",
            payload_json=payload_json,
        )
        await self.db.flush()
        return approval

    async def _create_github_pr_for_run(
        self,
        run: TaskRun,
        task: OrchestratorTask,
        repository: GithubRepository,
        issue_link: GithubIssueLink,
    ) -> None:
        connection = await self.db.get(GithubConnection, repository.connection_id)
        project = await self.db.get(OrchestratorProject, task.project_id)
        if connection is None:
            return
        branch_name = self._github_branch_name_for_task(project, task)
        github_settings = self._project_github_settings(project)
        patch_body = str(
            run.output_payload_json.get("final_output")
            or run.output_payload_json.get("summary")
            or task.result_summary
            or ""
        )
        default_branch = repository.default_branch or "main"
        ref_response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/git/ref/heads/{default_branch}",
        )
        if ref_response.status_code >= 400:
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_pr",
                status="failed",
                detail="Failed to load default branch reference before PR creation.",
                payload_json={"run_id": run.id},
            )
            return
        base_commit_sha = ((ref_response.json() or {}).get("object") or {}).get("sha")
        commit_response = await self._github_request(
            connection,
            "GET",
            f"/repos/{repository.full_name}/git/commits/{base_commit_sha}",
        )
        base_tree_sha = (commit_response.json() or {}).get("tree", {}).get("sha")
        blob_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/blobs",
            json_body={"content": patch_body, "encoding": "utf-8"},
        )
        blob_sha = (blob_response.json() or {}).get("sha")
        tree_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/trees",
            json_body={
                "base_tree": base_tree_sha,
                "tree": [
                    {
                        "path": f".troop/patches/{task.id}-{self._slugify(task.title)}.md",
                        "mode": "100644",
                        "type": "blob",
                        "sha": blob_sha,
                    }
                ],
            },
        )
        new_tree_sha = (tree_response.json() or {}).get("sha")
        new_commit_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/commits",
            json_body={
                "message": f"troop: task {task.id} patch proposal",
                "tree": new_tree_sha,
                "parents": [base_commit_sha],
            },
        )
        new_commit_sha = (new_commit_response.json() or {}).get("sha")
        branch_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/git/refs",
            json_body={"ref": f"refs/heads/{branch_name}", "sha": new_commit_sha},
        )
        if branch_response.status_code >= 400 and branch_response.status_code != 422:
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_branch",
                status="failed",
                detail="Failed to create GitHub branch for PR generation.",
                payload_json={"branch": branch_name, "run_id": run.id},
            )
            return
        pr_body = (
            f"Closes #{issue_link.issue_number}\n\n"
            f"Generated from task `{task.id}`.\n\n"
            f"{patch_body[:6000]}"
        )
        pr_response = await self._github_request(
            connection,
            "POST",
            f"/repos/{repository.full_name}/pulls",
            json_body={
                "title": f"[Troop] {task.title}",
                "head": branch_name,
                "base": default_branch,
                "body": pr_body,
                "draft": bool(run.input_payload_json.get("draft_pr", github_settings.get("draft_prs_by_default", True))),
            },
        )
        if pr_response.status_code >= 400:
            await self.repo.create_sync_event(
                repository_id=repository.id,
                issue_link_id=issue_link.id,
                action="create_pr",
                status="failed",
                detail="Failed to open pull request from agent output.",
                payload_json={"branch": branch_name, "run_id": run.id},
            )
            return
        pr_payload = pr_response.json()
        task.result_payload_json = {
            **(task.result_payload_json or {}),
            "github_pr": {
                "number": pr_payload.get("number"),
                "url": pr_payload.get("html_url"),
                "state": pr_payload.get("state"),
                "branch": branch_name,
            },
        }
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="create_pr",
            status="completed",
            detail=f"Opened PR #{pr_payload.get('number')} from agent output.",
            payload_json={
                "run_id": run.id,
                "task_id": task.id,
                "branch": branch_name,
                "head_sha": new_commit_sha,
                "pr_number": pr_payload.get("number"),
                "agent_id": run.worker_agent_id or run.orchestrator_agent_id,
            },
        )

    async def _post_reviewer_pr_comment(self, run: TaskRun, task: OrchestratorTask, review_text: str) -> None:
        if not task.github_issue_link_id:
            return
        issue_link = await self.db.get(GithubIssueLink, task.github_issue_link_id)
        if issue_link is None:
            return
        repository = await self.db.get(GithubRepository, issue_link.repository_id)
        pr_payload = (task.result_payload_json or {}).get("github_pr") or {}
        pr_number = pr_payload.get("number")
        if repository is None or not pr_number:
            return
        await self._create_github_write_approval(
            user_id=run.triggered_by_user_id,
            project_id=task.project_id,
            task_id=task.id,
            run_id=run.id,
            issue_link_id=issue_link.id,
            approval_type="github_pr_review_comment",
            payload_json={
                "run_id": run.id,
                "task_id": task.id,
                "pr_number": pr_number,
                "body": review_text[:5000],
                "agent_id": run.reviewer_agent_id or run.worker_agent_id,
            },
        )
        await self.repo.create_sync_event(
            repository_id=repository.id,
            issue_link_id=issue_link.id,
            action="post_pr_review",
            status="pending",
            detail=f"Reviewer agent drafted a PR comment for #{pr_number} pending approval.",
            payload_json={"run_id": run.id, "pr_number": pr_number, "agent_id": run.reviewer_agent_id or run.worker_agent_id},
        )


async def run_orchestration_job(run_id: str) -> None:
    from backend.db.session import SessionLocal

    async with SessionLocal() as db:
        service = OrchestrationService(db)
        await service.execute_run(run_id)
