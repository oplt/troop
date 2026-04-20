from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import uuid
import re
import time
from collections import Counter
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import httpx
import jwt
from fastapi import HTTPException, UploadFile
from sqlalchemy import or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import attributes as orm_attributes

from backend.core.cache import redis_client
from backend.core.storage import StorageNotConfiguredError, object_storage
from backend.core.config import settings
from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.audit.repository import AuditRepository
from backend.modules.github.service import OrchestrationGithubServiceMixin
from backend.modules.github.models import GithubConnection, GithubIssueLink, GithubRepository
from backend.modules.identity_access.models import User
from backend.modules.memory.classifier import (
    ClassifierCandidate,
    classify_run_events,
)
from backend.modules.memory.conflict_resolver import (
    ConflictReport,
    detect as detect_memory_conflicts,
    summarize as summarize_memory_conflicts,
)
from backend.modules.memory.models import (
    AgentMemoryEntry,
    KnowledgeGraphEdge,
    ProceduralPlaybook,
    ProjectDocument,
    SemanticMemoryEntry,
    SemanticMemoryLink,
    normalize_embedding_for_vector,
)
from backend.modules.memory.promotion_rules import (
    PromotionCandidate,
    PromotionEvaluation,
    evaluate as evaluate_promotion,
)
from backend.modules.memory.provenance import (
    DEFAULT_CONFIDENCE,
    get_confidence as get_provenance_confidence,
    normalize_provenance,
)
from backend.modules.memory.retrieval_scoping import (
    staged_episodic_vector_retrieval,
    staged_semantic_vector_retrieval,
)
from backend.modules.memory.service import OrchestrationMemoryServiceMixin
from backend.modules.orchestration._helpers import (
    BlockedExecution,
    OPENAI_FAMILY_PROVIDER_TYPES,
    _chunk_text,
    _cosine_similarity,
    _default_semantic_namespace,
    _estimate_embedding_tokens,
    _provider_type_aliases,
    run_orchestration_job,
)
from backend.modules.orchestration.models import (
    ApprovalRequest,
    Brainstorm,
    EvalRecord,
    ModelCapability,
    ProviderConfig,
    RunEvent,
    TaskRun,
)
from backend.modules.orchestration.providers import (
    discover_provider_capabilities,
    execute_prompt,
    test_provider,
)
from backend.modules.orchestration.context_packet import ContextPacket, log_context_packet_telemetry
from backend.modules.orchestration.execution.execution_state import (
    EXECUTION_SNAPSHOT_SCHEMA_VERSION,
    EXECUTION_TRUTH_DESCRIPTION,
    SNAPSHOT_SOURCES_RUN,
    SNAPSHOT_SOURCES_TASK,
    checkpoint_excerpt,
    extract_execution_memory_details,
    extract_execution_metadata_views,
)
from backend.modules.orchestration.execution.execution_workflow import (
    WORKFLOW_STATE_KEY,
    consume_signal_queue,
    current_step,
    durable_handle,
    enqueue_signal,
    ensure_workflow_state,
    get_workflow_artifact,
    increment_resume_count,
    mark_step,
    set_workflow_artifact,
    summarize_trace,
    update_query_snapshot,
    workflow_state,
)
from backend.modules.memory.coordination import (
    MEMORY_COORDINATION_KEY,
    extract_blackboard_sections,
)
from backend.modules.memory.compaction import (
    AGENT_MEMORY_TTL_SNAPSHOT_KIND,
    PROJECT_DOCUMENT_TTL_SNAPSHOT_KIND,
    TASK_CLOSE_SNAPSHOT_KIND,
    build_task_close_snapshot_text,
    prune_checkpoint_after_compaction,
    snapshot_source_id,
)
from backend.modules.memory.episodic import (
    build_episodic_archive_jsonl_gz,
    episodic_object_key,
)
from backend.modules.orchestration.execution.execution_service import OrchestrationExecutionServiceMixin
from backend.modules.orchestration.services.brainstorm_service import OrchestrationBrainstormServiceMixin
from backend.modules.orchestration.services.providers_service import OrchestrationProvidersServiceMixin
from backend.modules.orchestration.services.routing_service import OrchestrationRoutingServiceMixin
from backend.modules.memory.metrics import increment_memory_metric
from backend.modules.memory.settings import merge_memory_settings
from backend.modules.orchestration.procedural_context import build_procedural_snippets
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.memory.working_memory import (
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
    ProjectRepositoryLink,
    TaskArtifact,
)
from backend.modules.projects.service import OrchestrationProjectsServiceMixin
from backend.modules.projects.tasks_service import OrchestrationTasksServiceMixin
from backend.modules.team.models import AgentProfile
from backend.modules.team.service import TeamServiceMixin


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

from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
    validate_entry_metadata as _validate_semantic_entry_metadata,
    validate_entry_type as _validate_semantic_entry_type,
)
from backend.modules.memory.namespaces import (
    build_namespace as _build_memory_namespace,
    coerce_legacy_namespace as _coerce_memory_namespace,
    parse_namespace as _parse_memory_namespace,
)

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)

GITHUB_WEBHOOK_EVENT_ALLOWLIST = frozenset(
    {
        "installation",
        "installation_repositories",
        "issues",
        "issue_comment",
        "pull_request",
        "pull_request_review",
        "pull_request_review_comment",
        "push",
        "projects_v2_item",
    }
)


class OrchestrationApprovalsServiceMixin:
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
            if bool((approval.payload_json or {}).get("promotion_suggested")):
                if status == "approved":
                    increment_memory_metric("promotion_semantic_approval_accepted")
                elif status == "rejected":
                    increment_memory_metric("promotion_semantic_approval_rejected")
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
            user_id=user.id,
            action=f"orchestration.approval.{status}",
            resource_type="approval_request",
            resource_id=approval.id,
            metadata={
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
