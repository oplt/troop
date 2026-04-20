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
from backend.modules.orchestration.services.approvals_service import OrchestrationApprovalsServiceMixin
from backend.modules.orchestration.services.evals_service import OrchestrationEvalsServiceMixin
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


class OrchestrationService(
    OrchestrationEvalsServiceMixin,
    OrchestrationApprovalsServiceMixin,
    OrchestrationGithubServiceMixin,
    OrchestrationMemoryServiceMixin,
    OrchestrationBrainstormServiceMixin,
    OrchestrationProvidersServiceMixin,
    OrchestrationRoutingServiceMixin,
    OrchestrationExecutionServiceMixin,
    OrchestrationTasksServiceMixin,
    OrchestrationProjectsServiceMixin,
    TeamServiceMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = OrchestrationRepository(db)
        self.audit_repo = AuditRepository(db)
        self.ai_providers = AiProviderRegistry()


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
