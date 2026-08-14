from __future__ import annotations

import asyncio
import json
import re
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy import select, update
from sqlalchemy.orm import attributes as orm_attributes

from backend.core.cache import (
    get_cached_memory_context,
    get_cached_memory_settings,
    invalidate_project_knowledge_caches,
    set_cached_memory_context,
    set_cached_memory_settings,
)
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.storage import StorageAssetClass, object_storage
from backend.modules.identity_access.models import User
from backend.modules.memory.classifier import (
    classify_run_events,
)
from backend.modules.memory.compaction import (
    AGENT_MEMORY_TTL_SNAPSHOT_KIND,
    PROJECT_DOCUMENT_TTL_SNAPSHOT_KIND,
    TASK_CLOSE_SNAPSHOT_KIND,
    build_task_close_snapshot_text,
    prune_checkpoint_after_compaction,
    snapshot_source_id,
)
from backend.modules.memory.conflict_resolver import (
    ConflictReport,
)
from backend.modules.memory.conflict_resolver import (
    detect as detect_memory_conflicts,
)
from backend.modules.memory.conflict_resolver import (
    summarize as summarize_memory_conflicts,
)
from backend.modules.memory.coordination import (
    MEMORY_COORDINATION_KEY,
    extract_blackboard_sections,
)
from backend.modules.memory.episodic_jobs import EpisodicJobsMixin
from backend.modules.memory.layer.config import resolve_memory_config
from backend.modules.memory.layer.schemas import MemoryFilters
from backend.modules.memory.layer.service import MemoryService
from backend.modules.memory.metrics import increment_memory_metric
from backend.modules.memory.models import (
    AgentMemoryEntry,
    KnowledgeGraphEdge,
    MemoryIngestJob,
    ProceduralPlaybook,
    ProjectDocument,
    SemanticMemoryEntry,
    SemanticMemoryLink,
    normalize_embedding_for_vector,
)
from backend.modules.memory.promotion_rules import (
    PromotionCandidate,
    PromotionEvaluation,
)
from backend.modules.memory.promotion_rules import (
    evaluate as evaluate_promotion,
)
from backend.modules.memory.provenance import (
    normalize_provenance,
)
from backend.modules.memory.retrieval_scoping import (
    staged_episodic_vector_retrieval,
    staged_semantic_vector_retrieval,
)
from backend.modules.memory.settings import merge_memory_settings
from backend.modules.memory.working_memory import (
    WORKING_MEMORY_KEY,
    format_working_memory_for_prompt,
    merge_working_memory_patch,
    patch_allowed_for_run_status,
    working_memory_from_checkpoint,
)
from backend.modules.orchestration._helpers import (
    _chunk_text,
    _cosine_similarity,
    _default_semantic_namespace,
    _estimate_embedding_tokens,
)
from backend.modules.orchestration.context_packet import (
    ContextPacket,
    dedupe_context_sections,
    log_context_packet_telemetry,
)
from backend.modules.orchestration.hitl_policy import action_requires_approval
from backend.modules.orchestration.models import (
    ApprovalRequest,
    TaskRun,
)
from backend.modules.orchestration.procedural_context import build_procedural_snippets
from backend.modules.projects.orchestration_models import (
    OrchestratorProject,
    OrchestratorTask,
    ProjectDecision,
    ProjectRepositoryLink,
)
from backend.modules.rag.config import resolve_rag_config
from backend.modules.rag.prompt_builder import RagPromptBuilder
from backend.modules.rag.retrieval import DocumentIngestionService, RetrieverService
from backend.modules.rag.schemas import RagChunkMatch, RagSearchFilters
from backend.modules.team.models import AgentProfile

logger = get_logger(__name__)

from backend.modules.memory.entry_types import (
    SEMANTIC_ENTRY_TYPES as _CANONICAL_SEMANTIC_ENTRY_TYPES,
)
from backend.modules.memory.entry_types import (
    validate_entry_metadata as _validate_semantic_entry_metadata,
)
from backend.modules.memory.entry_types import (
    validate_entry_type as _validate_semantic_entry_type,
)
from backend.modules.memory.namespaces import (
    coerce_legacy_namespace as _coerce_memory_namespace,
)

SEMANTIC_ENTRY_TYPES = frozenset(_CANONICAL_SEMANTIC_ENTRY_TYPES)


class OrchestrationMemoryServiceMixin(EpisodicJobsMixin):
    def _memory_layer_service(
        self, project_settings_json: dict[str, Any] | None = None
    ) -> MemoryService:
        return MemoryService(self.db, config=resolve_memory_config(project_settings_json))

    async def _build_memory_layer_context_for_run(
        self,
        run: TaskRun,
        task: OrchestratorTask | None,
        project: OrchestratorProject | None,
    ) -> str:
        if project is None:
            return ""
        ms = merge_memory_settings(project.settings_json)
        layer = ms.get("layer") if isinstance(ms.get("layer"), dict) else {}
        if not layer.get("inject_context_before_llm", True):
            return ""
        memory_service = self._memory_layer_service(project.settings_json)
        if not memory_service.enabled:
            return ""
        query_parts = []
        if task:
            query_parts.extend([task.title or "", (task.description or "")[:500]])
        wm = format_working_memory_for_prompt(working_memory_from_checkpoint(run.checkpoint_json))
        if wm:
            query_parts.append(wm[:1200])
        query = "\n".join(p for p in query_parts if p).strip() or "project context"
        agent_id = run.worker_agent_id or run.orchestrator_agent_id
        if task and not agent_id:
            agent_id = task.assigned_agent_id
        return await memory_service.build_memory_context(
            project.owner_id,
            query,
            filters=MemoryFilters(
                user_id=project.owner_id,
                project_id=project.id,
                agent_id=agent_id,
                session_id=run.id,
            ),
            max_tokens=int(
                layer.get("context_max_tokens") or ms.get("context_packet_max_tokens") or 700
            ),
        )

    async def _extract_memory_layer_from_run(
        self,
        run: TaskRun,
        task: OrchestratorTask | None,
        project: OrchestratorProject | None,
    ) -> None:
        if project is None or task is None:
            return
        memory_service = self._memory_layer_service(project.settings_json)
        if not memory_service.enabled:
            return
        events = await self.repo.list_run_events_tail(run.id, limit=20)
        messages: list[dict[str, str]] = []
        for ev in events:
            et = str(ev.event_type or "").lower()
            if et not in {"log", "decision", "finding", "summary", "completed"}:
                continue
            text = str(ev.message or "").strip()
            payload = ev.payload_json if isinstance(ev.payload_json, dict) else {}
            if isinstance(payload, dict):
                for key in ("text", "content", "summary", "final_output"):
                    val = payload.get(key)
                    if isinstance(val, str) and val.strip():
                        text = f"{text}\n{val}".strip() if text else val.strip()
                        break
            if len(text) < 20:
                continue
            role = "assistant" if et in {"summary", "completed", "finding"} else "user"
            messages.append({"role": role, "content": text[:4000]})
        final_output = str(
            (run.output_payload_json or {}).get("final_output")
            or (run.output_payload_json or {}).get("summary")
            or ""
        ).strip()
        if final_output:
            messages.append({"role": "assistant", "content": final_output[:4000]})
        if not messages:
            return
        agent_id = run.worker_agent_id or run.orchestrator_agent_id or task.assigned_agent_id
        await memory_service.extract_and_store_from_interaction(
            user_id=project.owner_id,
            messages=messages,
            project_id=project.id,
            session_id=run.id,
            agent_id=agent_id,
        )

    async def get_working_memory(self, user: User, run_id: str) -> dict[str, Any]:
        run = await self.get_run(user, run_id)
        return working_memory_from_checkpoint(run.checkpoint_json)

    async def patch_working_memory(
        self, user: User, run_id: str, patch: dict[str, Any]
    ) -> dict[str, Any]:
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
        ms = merge_memory_settings(project.settings_json)
        min_hits = max(1, int(ms.get("retrieval_stage_min_hits") or 3))
        related_cap = max(1, int(ms.get("retrieval_cross_project_limit") or 6))
        title_q = (task.title or "").strip()[:120] or None
        company_id = await self._ensure_company_id_for_project(project)
        entries: list[SemanticMemoryEntry] = []
        seen: set[str] = set()

        def _take(rows: list[SemanticMemoryEntry]) -> None:
            for e in rows:
                if e.id in seen:
                    continue
                seen.add(e.id)
                entries.append(e)

        rows = await self.repo.list_semantic_memory_entries(
            project.owner_id,
            project_id=project.id,
            namespace_prefix=f"task/{task.id}/",
            search=title_q,
            limit=8,
        )
        increment_memory_metric(
            "retrieval_kw_semantic_task_hit" if rows else "retrieval_kw_semantic_task_miss"
        )
        _take(rows)
        increment_memory_metric("retrieval_scope_semantic_task_kw")
        if len(entries) < min_hits:
            rows = await self.repo.list_semantic_memory_entries(
                project.owner_id,
                project_id=project.id,
                search=title_q,
                limit=8,
            )
            increment_memory_metric(
                "retrieval_kw_semantic_project_hit"
                if rows
                else "retrieval_kw_semantic_project_miss"
            )
            _take(rows)
            increment_memory_metric("retrieval_scope_semantic_project_kw")
        if len(entries) < min_hits and company_id:
            rows = await self.repo.list_semantic_memory_entries_for_company(
                project.owner_id,
                company_id,
                search=title_q,
                limit=6,
            )
            increment_memory_metric(
                "retrieval_kw_semantic_company_hit"
                if rows
                else "retrieval_kw_semantic_company_miss"
            )
            _take(rows)
            increment_memory_metric("retrieval_scope_semantic_company_kw")
        if len(entries) < min_hits:
            rel = await self.repo.list_related_project_ids_for_retrieval(
                project.owner_id,
                project.id,
                agent_id=task.assigned_agent_id,
                limit=related_cap,
            )
            cross_any = False
            if rel:
                rows = await self.repo.list_semantic_memory_entries_for_projects(
                    project.owner_id,
                    rel,
                    search=title_q,
                    limit=max(4, related_cap * 4),
                )
                cross_any = bool(rows)
                _take(rows)
            if rel:
                increment_memory_metric(
                    "retrieval_kw_semantic_cross_project_hit"
                    if cross_any
                    else "retrieval_kw_semantic_cross_project_miss"
                )
                increment_memory_metric("retrieval_scope_semantic_cross_project_kw")
        if not entries:
            return ""
        lines = [
            f"- [{e.entry_type}] **{e.title}** (`{e.namespace}`): {(e.body or '')[:420].strip()}"
            for e in entries[:12]
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
        source_task_id: str | None = None,
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
            source_task_id=source_task_id,
            limit=limit,
        )
        if source_task_id:
            return rows
        if vec_q and vec_q.strip() and ms.get("enable_semantic_vector_search", True):
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

    async def list_semantic_memory_for_company(
        self,
        user: User,
        company_id: str,
        *,
        q: str | None = None,
        entry_type: str | None = None,
        namespace_prefix: str | None = None,
        limit: int = 100,
    ) -> list[SemanticMemoryEntry]:
        from backend.modules.companies.repository import CompanyRepository

        company = await CompanyRepository(self.db).get(user.id, company_id)
        if company is None:
            raise HTTPException(status_code=404, detail="company not found")
        return await self.repo.list_semantic_memory_entries_for_company(
            user.id,
            company_id,
            entry_type=entry_type,
            namespace_prefix=namespace_prefix,
            search=q,
            limit=limit,
        )

    async def _persist_semantic_memory_row(
        self, user: User, project: OrchestratorProject, payload: dict[str, Any]
    ) -> SemanticMemoryEntry:
        project_id = project.id
        et = _validate_semantic_entry_type(str(payload["entry_type"]))
        title = str(payload["title"]).strip()
        body = str(payload["body"]).strip()
        if not title or not body:
            raise HTTPException(status_code=422, detail="title and body are required")
        scope = str(payload.get("scope") or "project")
        if scope not in ("project", "agent", "company"):
            raise HTTPException(status_code=422, detail="Invalid scope")
        company_id = await self._ensure_company_id_for_project(project)
        agent_id = payload.get("agent_id")
        ns_raw = str(payload.get("namespace") or "").strip()
        if ns_raw:
            ns = _coerce_memory_namespace(
                ns_raw, project_id=project_id, company_id=company_id, agent_id=agent_id
            )
        else:
            ns = _default_semantic_namespace(
                project_id,
                et,
                title,
                scope=scope,
                company_id=company_id,
                agent_id=agent_id,
            )
        metadata = _validate_semantic_entry_metadata(et, dict(payload.get("metadata") or {}))
        proj_for_row = None if scope == "company" else project_id

        provenance = normalize_provenance(
            payload.get("provenance"),
            default_source="api",
            created_by_user_id=user.id,
            source_task_id=payload.get("source_task_id"),
            source_run_id=payload.get("source_run_id"),
            source_agent_id=agent_id,
        )

        conflict_report = await self._detect_pre_write_conflicts(
            project=project,
            scope=scope,
            company_id=company_id,
            project_id=proj_for_row,
            namespace=ns,
            entry_type=et,
            title=title,
            body=body,
            agent_id=agent_id,
        )
        if conflict_report.has_any:
            metadata = dict(metadata)
            metadata.setdefault("_conflict_report", summarize_memory_conflicts(conflict_report))
            provenance = dict(provenance)
            if conflict_report.best_duplicate is not None:
                provenance["supersedes"] = list(
                    dict.fromkeys(
                        list(provenance.get("supersedes") or [])
                        + [conflict_report.best_duplicate.entry_id]
                    )
                )

        layer_meta = dict(metadata)
        layer_meta.update(
            {
                "entry_type": et,
                "title": title,
                "namespace": ns,
                "company_id": company_id,
                "source_chunk_id": payload.get("source_chunk_id"),
                "source_task_id": payload.get("source_task_id"),
                "source_run_id": payload.get("source_run_id"),
                "provenance": provenance,
            }
        )
        canonical = self._memory_layer_service(project.settings_json)
        record = await canonical.add_memory(
            project.owner_id,
            body,
            layer_meta,
            scope=scope,  # type: ignore[arg-type]
            project_id=proj_for_row,
            ttl_days=payload.get("ttl_days"),
            retention_policy=str(payload.get("retention_policy") or "default"),
        )
        if record is None:
            raise HTTPException(
                status_code=422, detail="Memory content was blocked by privacy filters"
            )
        entry = await self.repo.get_semantic_memory_entry(project.owner_id, record.id)
        if entry is None:
            raise HTTPException(status_code=500, detail="Semantic memory row missing after write")
        increment_memory_metric("semantic_entry_created")
        if project_id:
            await invalidate_project_knowledge_caches(project_id)
        return entry

    async def _detect_pre_write_conflicts(
        self,
        *,
        project: OrchestratorProject,
        scope: str,
        company_id: str | None,
        project_id: str | None,
        namespace: str,
        entry_type: str,
        title: str,
        body: str,
        agent_id: str | None,
    ) -> ConflictReport:
        try:
            query_text = f"{title}\n\n{body}"[:8000]
            try:
                cand_embedding = (await self.ai_providers.embed_texts([query_text]))[0]
                cand_vec = normalize_embedding_for_vector(cand_embedding)
            except Exception as exc:
                logger.debug("conflict embedding unavailable, fallback to tokens: %s", exc)
                cand_vec = None
            namespace_prefix = "/".join(namespace.split("/")[:3]) if namespace else None
            existing = await self.repo.list_semantic_memory_entries(
                project.owner_id,
                project_id=project_id,
                entry_type=entry_type,
                namespace_prefix=namespace_prefix,
                limit=100,
            )
            return detect_memory_conflicts(
                cand_vec,
                title,
                body,
                entry_type,
                existing,
            )
        except Exception as exc:
            logger.warning("pre-write conflict detection failed: %s", exc)
            return ConflictReport()

    async def _detect_pre_write_conflicts_from_payload(
        self, project: OrchestratorProject, payload: dict[str, Any]
    ) -> ConflictReport:
        title = str(payload.get("title") or "").strip()
        body = str(payload.get("body") or "").strip()
        entry_type = str(payload.get("entry_type") or "note")
        scope = str(payload.get("scope") or "project")
        agent_id = payload.get("agent_id")
        company_id = await self._ensure_company_id_for_project(project)
        proj_for_row = None if scope == "company" else project.id
        ns_raw = str(payload.get("namespace") or "").strip()
        if ns_raw:
            ns = _coerce_memory_namespace(
                ns_raw, project_id=project.id, company_id=company_id, agent_id=agent_id
            )
        else:
            ns = _default_semantic_namespace(
                project.id,
                entry_type,
                title,
                scope=scope,
                company_id=company_id,
                agent_id=agent_id,
            )
        if not title or not body:
            return ConflictReport()
        return await self._detect_pre_write_conflicts(
            project=project,
            scope=scope,
            company_id=company_id,
            project_id=proj_for_row,
            namespace=ns,
            entry_type=entry_type,
            title=title,
            body=body,
            agent_id=agent_id,
        )

    async def create_semantic_memory_entry_for_project(
        self,
        user: User,
        project_id: str,
        payload: dict[str, Any],
        *,
        bypass_semantic_write_gate: bool = False,
        promotion_evaluation: PromotionEvaluation | None = None,
    ) -> SemanticMemoryEntry | ApprovalRequest:
        project = await self.get_project(user, project_id)
        ms = merge_memory_settings(project.settings_json)
        conflict_report = await self._detect_pre_write_conflicts_from_payload(project, payload)
        conflict_detected = conflict_report.has_any
        requires_approval = (
            (
                action_requires_approval(
                    (project.settings_json or {}).get("execution"),
                    "write_memory",
                )
                or ms.get("semantic_write_requires_approval")
            )
            and not bypass_semantic_write_gate
        ) or conflict_detected
        if requires_approval:
            approval_payload: dict[str, Any] = {"operation": "create", "payload": dict(payload)}
            if conflict_detected:
                approval_payload["conflict_report"] = summarize_memory_conflicts(conflict_report)
            if promotion_evaluation is not None:
                approval_payload["promotion_suggested"] = True
                approval_payload["promotion_evaluation"] = {
                    "verdict": promotion_evaluation.verdict,
                    "score": promotion_evaluation.score,
                    "matched_rules": promotion_evaluation.matched_rules,
                    "rationale": promotion_evaluation.rationale,
                }
                increment_memory_metric("promotion_candidate_queued")
            approval = await self.repo.create_approval(
                project_id=project_id,
                task_id=None,
                run_id=None,
                requested_by_user_id=user.id,
                approval_type="semantic_memory_write",
                status="pending",
                payload_json=approval_payload,
            )
            await self.db.commit()
            await self.db.refresh(approval)
            increment_memory_metric("semantic_write_approval_requested")
            if conflict_detected:
                increment_memory_metric("semantic_conflict_detected")
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
            entry.entry_type = _validate_semantic_entry_type(str(updates["entry_type"]))
        if "namespace" in updates and updates["namespace"] is not None:
            ns = _coerce_memory_namespace(
                str(updates["namespace"]),
                project_id=entry.project_id,
                company_id=entry.company_id,
                agent_id=entry.agent_id,
            )
            entry.namespace = ns[:512]
        if "metadata" in updates and updates["metadata"] is not None:
            entry.metadata_json = _validate_semantic_entry_metadata(
                entry.entry_type, dict(updates["metadata"])
            )

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
        if (
            action_requires_approval(
                (project.settings_json or {}).get("execution"),
                "write_memory",
            )
            or ms.get("semantic_write_requires_approval")
        ) and not bypass_semantic_write_gate:
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
        update_metadata = dict(updates.get("metadata") or {})
        if "title" in updates and updates["title"] is not None:
            update_metadata["title"] = str(updates["title"])[:255]
        if "entry_type" in updates and updates["entry_type"] is not None:
            update_metadata["entry_type"] = _validate_semantic_entry_type(
                str(updates["entry_type"])
            )
            _validate_semantic_entry_metadata(update_metadata["entry_type"], update_metadata)
        elif "metadata" in updates and updates["metadata"] is not None:
            _validate_semantic_entry_metadata(entry.entry_type, update_metadata)
        if "namespace" in updates and updates["namespace"] is not None:
            update_metadata["namespace"] = _coerce_memory_namespace(
                str(updates["namespace"]),
                project_id=entry.project_id,
                company_id=entry.company_id,
                agent_id=entry.agent_id,
            )
        if "ttl_days" in updates:
            update_metadata["ttl_days"] = updates["ttl_days"]
        if "retention_policy" in updates and updates["retention_policy"] is not None:
            update_metadata["retention_policy"] = updates["retention_policy"]
        canonical = self._memory_layer_service(project.settings_json)
        updated_record = await canonical.update_memory(
            entry.id,
            user_id=project.owner_id,
            content=updates.get("body"),
            metadata=update_metadata,
        )
        if updated_record is None:
            raise HTTPException(status_code=404, detail="Semantic entry not found")
        refreshed = await self.repo.get_semantic_memory_entry(project.owner_id, entry.id)
        if refreshed is None:
            raise HTTPException(status_code=404, detail="Semantic entry not found")
        await invalidate_project_knowledge_caches(project_id)
        return refreshed

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
        if (
            action_requires_approval(
                (project.settings_json or {}).get("execution"),
                "write_memory",
            )
            or ms.get("semantic_write_requires_approval")
        ) and not bypass_semantic_write_gate:
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
        canonical = self._memory_layer_service(project.settings_json)
        deleted = await canonical.delete_memory(entry.id, user_id=project.owner_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Semantic entry not found")
        await invalidate_project_knowledge_caches(project_id)
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
            raise HTTPException(
                status_code=400, detail="Working memory is empty; nothing to promote"
            )
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
        if entry is None or entry.deleted_at is not None:
            return
        if entry.expires_at is not None and entry.expires_at <= datetime.now(UTC):
            return
        text = f"{entry.title}\n\n{entry.body}"[:8000]
        vec = (await self.ai_providers.embed_texts([text]))[0]
        entry.embedding_vector = normalize_embedding_for_vector(vec)
        entry.embedding_model = getattr(settings, "RAG_EMBEDDING_MODEL", "") or None
        entry.embedding_version = entry.embedding_version or "v1"
        from backend.modules.ai.gateway.pricing import estimate_cost_micros, estimate_tokens

        embed_tokens = estimate_tokens(text)
        meta = dict(entry.metadata_json or {})
        meta["embedding_input_tokens"] = embed_tokens
        meta["embedding_cost_micros"] = estimate_cost_micros(
            None,
            embed_tokens,
            0,
            model_name=entry.embedding_model,
        )
        entry.metadata_json = meta
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

        cand = PromotionCandidate(
            entry_type="adr",
            title=(decision_row.title or "Decision")[:255],
            body=body,
            metadata={"rationale": (decision_row.rationale or "captured from project decision")},
            scope="project",
            source="project_decision",
            source_task_id=decision_row.task_id,
        )
        evaluation = evaluate_promotion(cand)
        if evaluation.verdict == "skip":
            increment_memory_metric("promotion_skipped")
            return

        bypass = ms.get("auto_ingest_bypasses_semantic_approval", True) and (
            evaluation.verdict == "auto"
        )
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project.id,
            {
                "entry_type": cand.entry_type,
                "title": cand.title,
                "body": cand.body,
                "metadata": cand.metadata,
                "scope": "project",
                "source_task_id": decision_row.task_id,
                "provenance": {
                    "source": "project_decision",
                    "confidence": max(0.75, evaluation.score),
                    "extras": {
                        "decision_id": decision_row.id,
                        "promotion_score": evaluation.score,
                        "matched_rules": evaluation.matched_rules,
                    },
                },
            },
            bypass_semantic_write_gate=bypass,
            promotion_evaluation=(None if evaluation.verdict == "auto" else evaluation),
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

        cand = PromotionCandidate(
            entry_type="preference",
            title=f"Memory: {memory.key}"[:255],
            body=memory.value_text or "",
            metadata={"preference_key": memory.key},
            scope="project",
            source="agent_memory",
            source_agent_id=memory.agent_id,
            source_run_id=memory.source_run_id,
        )
        evaluation = evaluate_promotion(cand)
        if evaluation.verdict == "skip":
            increment_memory_metric("promotion_skipped")
            return

        bypass = ms.get("auto_ingest_bypasses_semantic_approval", True) and (
            evaluation.verdict == "auto"
        )
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project.id,
            {
                "entry_type": cand.entry_type,
                "title": cand.title,
                "body": cand.body,
                "scope": "agent",
                "agent_id": memory.agent_id,
                "source_run_id": memory.source_run_id,
                "metadata": cand.metadata,
                "provenance": {
                    "source": "agent_memory",
                    "source_agent_id": memory.agent_id,
                    "source_run_id": memory.source_run_id,
                    "confidence": max(0.6, evaluation.score),
                    "extras": {
                        "agent_memory_id": memory.id,
                        "preference_key": memory.key,
                        "promotion_score": evaluation.score,
                        "matched_rules": evaluation.matched_rules,
                    },
                },
            },
            bypass_semantic_write_gate=bypass,
            promotion_evaluation=(None if evaluation.verdict == "auto" else evaluation),
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
        cand = PromotionCandidate(
            entry_type="note",
            title=f"Task close snapshot: {task.title or task.id[:8]}"[:255],
            body=body,
            scope="project",
            source="task_close",
            source_task_id=task.id,
            source_run_id=latest.id,
        )
        evaluation = evaluate_promotion(cand)
        if evaluation.verdict == "skip":
            increment_memory_metric("promotion_skipped")
            return
        bypass = ms.get("auto_ingest_bypasses_semantic_approval", True) and (
            evaluation.verdict == "auto"
        )
        out = await self.create_semantic_memory_entry_for_project(
            user,
            project.id,
            {
                "entry_type": cand.entry_type,
                "title": cand.title,
                "body": cand.body,
                "scope": "project",
                "source_task_id": task.id,
                "source_run_id": latest.id,
                "provenance": {
                    "source": "task_close",
                    "source_task_id": task.id,
                    "source_run_id": latest.id,
                    "confidence": max(0.55, evaluation.score),
                    "extras": {
                        "task_id": task.id,
                        "run_id": latest.id,
                        "promotion_score": evaluation.score,
                        "matched_rules": evaluation.matched_rules,
                    },
                },
            },
            bypass_semantic_write_gate=bypass,
            promotion_evaluation=(None if evaluation.verdict == "auto" else evaluation),
        )
        if isinstance(out, ApprovalRequest):
            return
        await self.db.refresh(task)
        meta = dict(task.metadata_json or {})
        meta["memory_task_close_promoted"] = True
        task.metadata_json = meta
        await self.db.commit()
        increment_memory_metric("task_close_auto_promotions")

    async def _run_task_close_memory_lifecycle(
        self,
        _user: User | None,
        project: OrchestratorProject,
        task: OrchestratorTask,
    ) -> None:
        if task.status not in {"completed", "archived", "synced_to_github"}:
            return
        meta = dict(task.metadata_json or {})
        if meta.get("memory_checkpoint_compacted"):
            return
        ms = merge_memory_settings(project.settings_json)
        want_default = bool(ms.get("compaction_on_task_close_enabled", True))
        low_value = False
        if ms.get("task_close_archive_unpromoted_memory", True) and not ms.get(
            "task_close_auto_promote_working_memory", False
        ):
            existing = await self.repo.find_semantic_by_task_close(
                project.owner_id, project.id, task.id
            )
            if existing is None:
                days = int(ms.get("task_close_low_value_archive_days") or 14)
                age_days = (datetime.now(UTC) - task.created_at).days
                if age_days >= days:
                    low_value = True
        if not want_default and not low_value:
            meta["memory_checkpoint_compacted"] = True
            meta["memory_compaction_skip_reason"] = "settings"
            task.metadata_json = meta
            orm_attributes.flag_modified(task, "metadata_json")
            await self.db.commit()
            return
        latest = await self.repo.get_latest_run_for_task(project.id, task.id)
        if not latest:
            meta["memory_checkpoint_compacted"] = True
            meta["memory_compaction_skip_reason"] = "no_run"
            task.metadata_json = meta
            orm_attributes.flag_modified(task, "metadata_json")
            await self.db.commit()
            return
        events = await self.repo.list_run_events_for_task(project.id, task.id, limit=400)
        ev_lines = [f"{ev.event_type}: {(ev.message or '')[:360]}" for ev in events[-160:]]
        wm = working_memory_from_checkpoint(latest.checkpoint_json)
        snap = build_task_close_snapshot_text(
            task_title=task.title or "",
            task_id=task.id,
            wm=wm,
            event_lines=ev_lines,
        )
        sid = snapshot_source_id(task.id, latest.id)
        if snap.strip():
            existing = await self.repo.get_episodic_index_row(
                project.id, TASK_CLOSE_SNAPSHOT_KIND, sid
            )
            if not existing:
                row = await self.repo.create_episodic_search_index_row(
                    owner_id=project.owner_id,
                    project_id=project.id,
                    source_kind=TASK_CLOSE_SNAPSHOT_KIND,
                    source_id=sid,
                    text_content=snap,
                    created_at=datetime.now(UTC),
                )
                await self.db.flush()
                try:
                    vec = (await self.ai_providers.embed_texts([snap[:8000]]))[0]
                    row.embedding_vector = normalize_embedding_for_vector(vec)
                except Exception as exc:
                    logger.warning(
                        "task_close_snapshot_embed_failed source_id=%s error=%s", sid, exc
                    )
        runs = await self.repo.list_task_runs_for_task(project.id, task.id, limit=80)
        for r in runs:
            r.checkpoint_json = prune_checkpoint_after_compaction(r.checkpoint_json or {})
            orm_attributes.flag_modified(r, "checkpoint_json")
        meta = dict(task.metadata_json or {})
        meta.pop("memory_compaction_skip_reason", None)
        meta["memory_checkpoint_compacted"] = True
        if low_value:
            meta["memory_low_value_archived"] = True
        task.metadata_json = meta
        orm_attributes.flag_modified(task, "metadata_json")
        await self.db.commit()
        increment_memory_metric("task_close_compactions")

    async def run_memory_compaction_backfill(self, *, limit: int = 40) -> int:
        """Periodic: terminal tasks missing compaction flag."""
        from sqlalchemy import select

        stmt = (
            select(OrchestratorTask)
            .where(
                OrchestratorTask.status.in_(("completed", "archived", "synced_to_github")),
            )
            .order_by(OrchestratorTask.updated_at.desc())
            .limit(max(limit * 4, 80))
        )
        tasks = list((await self.db.execute(stmt)).scalars().all())
        done = 0
        for t in tasks:
            if (t.metadata_json or {}).get("memory_checkpoint_compacted"):
                continue
            project = await self.db.get(OrchestratorProject, t.project_id)
            if project is None:
                continue
            await self._run_task_close_memory_lifecycle(None, project, t)
            done += 1
            if done >= limit:
                break
        increment_memory_metric("memory_compaction_backfill_runs")
        return done

    async def get_project_memory_settings(self, user: User, project_id: str) -> dict[str, Any]:
        cached = await get_cached_memory_settings(project_id)
        if cached is not None:
            await self.get_project(user, project_id)
            merged_cached = merge_memory_settings({"memory": cached})
            if merged_cached != cached:
                await set_cached_memory_settings(project_id, merged_cached)
            return merged_cached
        project = await self.get_project(user, project_id)
        merged = merge_memory_settings(project.settings_json)
        await set_cached_memory_settings(project_id, merged)
        return merged

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
        merged = merge_memory_settings(project.settings_json)
        await set_cached_memory_settings(project_id, merged)
        await invalidate_project_knowledge_caches(project_id)
        return merged

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
                    "kind": "title_duplicate",
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

        # Embedding-based conflict detection across same-type entries
        # (catches near-duplicates with different titles and contradictions).
        by_type: dict[str, list[SemanticMemoryEntry]] = {}
        for e in entries:
            by_type.setdefault(e.entry_type, []).append(e)
        seen_pairs: set[tuple[str, str]] = set()
        for et, bucket in by_type.items():
            for i, row in enumerate(bucket):
                report = detect_memory_conflicts(
                    row.embedding_vector,
                    row.title or "",
                    row.body or "",
                    et,
                    bucket[i + 1 :],
                    ignore_entry_id=row.id,
                )
                for hit in report.duplicates + report.contradictions:
                    pair = tuple(sorted((row.id, hit.entry_id)))
                    if pair in seen_pairs:
                        continue
                    seen_pairs.add(pair)
                    out.append(
                        {
                            "group_key": f"{et}:{hit.kind}:{hit.entry_id[:8]}",
                            "kind": hit.kind,
                            "similarity": hit.similarity,
                            "reason": hit.reason,
                            "entries": [
                                {
                                    "id": row.id,
                                    "title": row.title,
                                    "namespace": row.namespace,
                                    "updated_at": row.updated_at.isoformat(),
                                },
                                {
                                    "id": hit.entry_id,
                                    "title": hit.entry_title,
                                    "namespace": next(
                                        (x.namespace for x in bucket if x.id == hit.entry_id), ""
                                    ),
                                    "updated_at": next(
                                        (
                                            x.updated_at.isoformat()
                                            for x in bucket
                                            if x.id == hit.entry_id
                                        ),
                                        "",
                                    ),
                                },
                            ],
                        }
                    )
        title_groups = sum(1 for x in out if x.get("kind") == "title_duplicate")
        emb_groups = sum(1 for x in out if x.get("kind") != "title_duplicate")
        increment_memory_metric("semantic_conflict_scan_title_duplicate_groups", title_groups)
        increment_memory_metric("semantic_conflict_embedding_groups", emb_groups)
        increment_memory_metric("semantic_conflict_scan_total_groups", len(out))
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
        slug = (
            re.sub(r"[^a-z0-9]+", "-", str(payload.get("slug") or "").lower()).strip("-")[:128]
            or "playbook"
        )
        title = str(payload.get("title") or slug).strip()[:255]
        body = str(payload.get("body_md") or "").strip()
        if not body:
            raise HTTPException(status_code=422, detail="body_md is required")
        ns = (
            str(payload.get("namespace") or "").strip() or f"project/{project_id}/procedural/{slug}"
        )
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
        if (
            "shared" in payload
            and payload["shared"] is not None
            and self.action_requires_approval(project, "write_memory")
        ):
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

    async def merge_semantic_memory_entries_for_project(
        self,
        user: User,
        project_id: str,
        *,
        canonical_entry_id: str,
        merge_entry_ids: list[str],
        link_relation: str = "supersedes",
    ) -> SemanticMemoryEntry:
        await self.get_project(user, project_id)
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
        increment_memory_metric("semantic_conflict_resolved_merge")
        return canonical

    async def _ensure_knowledge_graph_edge(
        self,
        owner_id: str,
        project_id: str,
        source_kind: str,
        source_id: str,
        target_kind: str,
        target_id: str,
        relation_type: str,
        *,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeGraphEdge | None:
        if not source_id or not target_id:
            return None
        exists = await self.repo.get_knowledge_graph_edge_unique(
            project_id,
            source_kind[:64],
            source_id[:64],
            target_kind[:64],
            target_id[:64],
            relation_type[:64],
        )
        if exists:
            return None
        row = await self.repo.create_knowledge_graph_edge(
            owner_id=owner_id,
            project_id=project_id,
            source_kind=source_kind[:64],
            source_id=source_id[:64],
            target_kind=target_kind[:64],
            target_id=target_id[:64],
            relation_type=relation_type[:64],
            metadata_json=dict(metadata or {}),
        )
        increment_memory_metric("knowledge_graph_edges_created")
        return row

    async def _prune_stale_task_knowledge_graph_edges(
        self, project: OrchestratorProject, task: OrchestratorTask
    ) -> None:
        oid, pid = project.owner_id, project.id
        dep_ids = {
            d.depends_on_task_id for d in await self.repo.list_task_dependencies_for_task(task.id)
        }
        edges = await self.repo.list_knowledge_graph_edges_from_source(
            oid, pid, "task", task.id, limit=500
        )
        for e in edges:
            if e.relation_type == "depends_on" and e.target_kind == "task":
                if e.target_id not in dep_ids:
                    await self.repo.delete_knowledge_graph_edge(oid, pid, e.id)
            elif e.relation_type == "assigned_to" and e.target_kind == "agent_profile":
                if not task.assigned_agent_id or e.target_id != task.assigned_agent_id:
                    await self.repo.delete_knowledge_graph_edge(oid, pid, e.id)
            elif e.relation_type == "reviewed_by" and e.target_kind == "agent_profile":
                if not task.reviewer_agent_id or e.target_id != task.reviewer_agent_id:
                    await self.repo.delete_knowledge_graph_edge(oid, pid, e.id)
            elif (
                e.relation_type == "tracks_issue"
                and e.target_kind == "github_issue_link"
                and (not task.github_issue_link_id or e.target_id != task.github_issue_link_id)
            ):
                await self.repo.delete_knowledge_graph_edge(oid, pid, e.id)

    async def _sync_knowledge_graph_for_task(
        self, project: OrchestratorProject, task: OrchestratorTask
    ) -> None:
        oid, pid = project.owner_id, project.id
        await self._prune_stale_task_knowledge_graph_edges(project, task)
        if task.assigned_agent_id:
            await self._ensure_knowledge_graph_edge(
                oid, pid, "task", task.id, "agent_profile", task.assigned_agent_id, "assigned_to"
            )
        if task.reviewer_agent_id:
            await self._ensure_knowledge_graph_edge(
                oid, pid, "task", task.id, "agent_profile", task.reviewer_agent_id, "reviewed_by"
            )
        if task.github_issue_link_id:
            await self._ensure_knowledge_graph_edge(
                oid,
                pid,
                "task",
                task.id,
                "github_issue_link",
                task.github_issue_link_id,
                "tracks_issue",
            )
        for dep in await self.repo.list_task_dependencies_for_task(task.id):
            await self._ensure_knowledge_graph_edge(
                oid, pid, "task", task.id, "task", dep.depends_on_task_id, "depends_on"
            )

    async def _sync_knowledge_graph_for_decision(
        self, project: OrchestratorProject, decision: ProjectDecision
    ) -> None:
        oid, pid = project.owner_id, project.id
        edges = await self.repo.list_knowledge_graph_edges_from_source(
            oid, pid, "project_decision", decision.id, limit=100
        )
        for e in edges:
            if (
                e.relation_type == "about_task"
                and e.target_kind == "task"
                and (not decision.task_id or e.target_id != decision.task_id)
            ):
                await self.repo.delete_knowledge_graph_edge(oid, pid, e.id)
        if decision.task_id:
            await self._ensure_knowledge_graph_edge(
                project.owner_id,
                project.id,
                "project_decision",
                decision.id,
                "task",
                decision.task_id,
                "about_task",
            )

    async def _sync_knowledge_graph_for_project_repository(
        self, project: OrchestratorProject, link: ProjectRepositoryLink
    ) -> None:
        if link.github_repository_id:
            await self._ensure_knowledge_graph_edge(
                project.owner_id,
                project.id,
                "github_repository",
                link.github_repository_id,
                "orchestrator_project",
                project.id,
                "linked_to_project",
                metadata={"project_repository_link_id": link.id},
            )

    async def create_knowledge_graph_edge_for_project(
        self,
        user: User,
        project_id: str,
        *,
        source_kind: str,
        source_id: str,
        target_kind: str,
        target_id: str,
        relation_type: str,
        metadata: dict[str, Any] | None = None,
    ) -> KnowledgeGraphEdge:
        project = await self.get_project(user, project_id)
        row = await self._ensure_knowledge_graph_edge(
            project.owner_id,
            project_id,
            source_kind,
            source_id,
            target_kind,
            target_id,
            relation_type,
            metadata=metadata,
        )
        if row is not None:
            await self.db.commit()
            await self.db.refresh(row)
            return row
        existing = await self.repo.get_knowledge_graph_edge_unique(
            project_id,
            source_kind[:64],
            source_id[:64],
            target_kind[:64],
            target_id[:64],
            relation_type[:64],
        )
        if existing is None:
            raise HTTPException(status_code=400, detail="Could not create graph edge")
        return existing

    async def list_knowledge_graph_edges_for_project(
        self,
        user: User,
        project_id: str,
        *,
        source_kind: str | None = None,
        source_id: str | None = None,
        target_kind: str | None = None,
        target_id: str | None = None,
        limit: int = 200,
    ) -> list[KnowledgeGraphEdge]:
        project = await self.get_project(user, project_id)
        if source_kind and source_id:
            return await self.repo.list_knowledge_graph_edges_from_source(
                project.owner_id,
                project_id,
                source_kind,
                source_id,
                limit=limit,
            )
        if target_kind and target_id:
            return await self.repo.list_knowledge_graph_edges_to_target(
                project.owner_id,
                project_id,
                target_kind,
                target_id,
                limit=limit,
            )
        raise HTTPException(
            status_code=422,
            detail="Provide source_kind+source_id or target_kind+target_id query pair.",
        )

    async def delete_knowledge_graph_edge_for_project(
        self, user: User, project_id: str, edge_id: str
    ) -> None:
        project = await self.get_project(user, project_id)
        ok = await self.repo.delete_knowledge_graph_edge(project.owner_id, project_id, edge_id)
        if not ok:
            raise HTTPException(status_code=404, detail="Graph edge not found")
        await self.db.commit()

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

    async def _enqueue_classifier_job_for_task(
        self, project: OrchestratorProject, task: OrchestratorTask
    ) -> None:
        ms = merge_memory_settings(project.settings_json)
        if not ms.get("classifier_worker_enabled", True):
            return
        latest = await self.repo.get_latest_run_for_task(project.id, task.id)
        if latest is None:
            return
        await self.repo.create_memory_ingest_job(
            owner_id=project.owner_id,
            project_id=project.id,
            job_type="classify",
            payload_json={
                "project_id": project.id,
                "run_id": latest.id,
                "task_id": task.id,
            },
            status="pending",
        )
        await self.db.commit()

    async def _run_classifier_ingest_job(self, job: Any, payload: dict[str, Any]) -> dict[str, Any]:
        project_id = str(payload.get("project_id") or "")
        run_id = str(payload.get("run_id") or "")
        if not project_id or not run_id:
            raise RuntimeError("classify job missing project_id / run_id")
        project = await self.db.get(OrchestratorProject, project_id)
        if project is None:
            raise RuntimeError("classify job target project missing")
        ms = merge_memory_settings(project.settings_json)
        if not ms.get("classifier_worker_enabled", True):
            return {"skipped": True}
        owner_id = str(project.owner_id)
        owner = await self.db.get(User, owner_id)
        if owner is None:
            raise RuntimeError("classify job target owner missing")
        events = await self.repo.list_run_events_tail(
            run_id, limit=settings.RUN_EVENTS_CLASSIFIER_MAX
        )
        event_dicts: list[dict[str, Any]] = []
        for ev in events:
            event_dicts.append(
                {
                    "id": ev.id,
                    "event_type": ev.event_type,
                    "message": ev.message,
                    "payload_json": ev.payload_json,
                }
            )
        candidates = classify_run_events(event_dicts)
        created = 0
        approvals = 0
        skipped = 0
        for cand in candidates:
            if cand.layer != "semantic":
                # Procedural/working layers are out of scope for the
                # semantic write path; record a metric and move on.
                increment_memory_metric(f"classifier_candidate_{cand.layer}")
                continue
            promotion_cand = PromotionCandidate(
                entry_type=cand.entry_type,
                title=cand.title,
                body=cand.body,
                metadata={
                    k: v
                    for k, v in (cand.metadata or {}).items()
                    if k in ("rationale", "scope_label", "term", "preference_key")
                },
                scope="project",
                source="classifier",
                source_run_id=run_id,
            )
            evaluation = evaluate_promotion(promotion_cand)
            if evaluation.verdict == "skip":
                skipped += 1
                continue
            bypass = ms.get("auto_ingest_bypasses_semantic_approval", True) and (
                evaluation.verdict == "auto"
            )
            out = await self.create_semantic_memory_entry_for_project(
                owner,
                project_id,
                {
                    "entry_type": cand.entry_type,
                    "title": cand.title,
                    "body": cand.body,
                    "scope": "project",
                    "source_run_id": run_id,
                    "metadata": promotion_cand.metadata,
                    "provenance": {
                        "source": "classifier",
                        "source_run_id": run_id,
                        "confidence": max(cand.confidence, evaluation.score),
                        "extras": {
                            "classifier_rationale": cand.rationale,
                            "promotion_score": evaluation.score,
                            "matched_rules": evaluation.matched_rules,
                            "source_event_ids": cand.source_event_ids,
                        },
                    },
                },
                bypass_semantic_write_gate=bypass,
                promotion_evaluation=(None if evaluation.verdict == "auto" else evaluation),
            )
            if isinstance(out, ApprovalRequest):
                approvals += 1
            else:
                created += 1
        increment_memory_metric("classifier_jobs_completed")
        return {
            "candidates": len(candidates),
            "created": created,
            "approvals": approvals,
            "skipped": skipped,
        }

    async def _execute_memory_ingest_job_body(self, job: MemoryIngestJob) -> None:
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
        elif jt == "ai_document_ingest":
            from backend.modules.ai.service import AiService

            await AiService(self.db).process_ai_document_ingest_job(
                user_id=str(payload.get("user_id") or job.owner_id),
                document_id=str(payload.get("document_id") or ""),
            )
        elif jt == "repo_index":
            await self._run_repository_index_job(
                owner_id=str(job.owner_id),
                project_id=str(payload.get("project_id") or ""),
                repository_link_id=str(payload.get("repository_link_id") or ""),
                requested_by_user_id=str(payload.get("requested_by_user_id") or "") or None,
                payload=payload,
            )
        elif jt == "classify":
            await self._run_classifier_ingest_job(job, payload)
        else:
            raise RuntimeError(f"Unsupported memory ingest job type: {jt}")

    async def _process_memory_ingest_job(self, job: MemoryIngestJob) -> bool:
        await self.repo.update_memory_ingest_job(
            job.id, status="running", started_at=datetime.now(UTC)
        )
        await self.db.commit()
        try:
            await self._execute_memory_ingest_job_body(job)
            await self.repo.update_memory_ingest_job(
                job.id, status="completed", finished_at=datetime.now(UTC)
            )
            await self.db.commit()
            return True
        except Exception as exc:
            logger.error(
                "memory_ingest_job failed job_id=%s job_type=%s error=%s",
                job.id,
                job.job_type,
                exc,
            )
            increment_memory_metric("memory_ingest_jobs_failed")
            await self.repo.update_memory_ingest_job(
                job.id,
                status="failed",
                error_text=str(exc)[:2000],
                finished_at=datetime.now(UTC),
            )
            await self.db.commit()
            return False

    async def process_memory_ingest_job_by_id(self, job_id: str) -> bool:
        job = await self.repo.get_memory_ingest_job(job_id)
        if job is None or job.status != "pending":
            return False
        return await self._process_memory_ingest_job(job)

    async def process_memory_ingest_jobs_worker(self, *, limit: int = 15) -> dict[str, Any]:
        jobs = await self.repo.list_pending_memory_ingest_jobs(limit=limit)
        if not jobs:
            return {"processed": 0, "batch_size": 0}

        concurrency = max(1, settings.MEMORY_INGEST_JOB_CONCURRENCY)
        if concurrency <= 1 or len(jobs) == 1:
            processed = sum(1 for job in jobs if await self._process_memory_ingest_job(job))
        else:
            from backend.db.session import SessionLocal
            from backend.modules.orchestration.services.service import OrchestrationService

            semaphore = asyncio.Semaphore(concurrency)

            async def run_job(job_id: str) -> bool:
                async with semaphore, SessionLocal() as session:
                    service = OrchestrationService(session)
                    return await service.process_memory_ingest_job_by_id(job_id)

            results = await asyncio.gather(
                *[run_job(job.id) for job in jobs],
                return_exceptions=True,
            )
            processed = sum(1 for result in results if result is True)

        increment_memory_metric("memory_ingest_jobs_processed")
        return {"processed": processed, "batch_size": len(jobs)}

    async def _snapshot_expiring_project_document(self, doc: ProjectDocument) -> None:
        if not doc.project_id:
            return
        project = await self.db.get(OrchestratorProject, doc.project_id)
        if project is None:
            return
        existing = await self.repo.get_episodic_index_row(
            doc.project_id, PROJECT_DOCUMENT_TTL_SNAPSHOT_KIND, doc.id
        )
        if existing:
            return
        body = (
            f"[document_ttl] id={doc.id} filename={doc.filename}\n"
            f"{(doc.summary_text or doc.source_text or '')[:6000]}"
        ).strip()
        if not body:
            return
        row = await self.repo.create_episodic_search_index_row(
            owner_id=project.owner_id,
            project_id=doc.project_id,
            source_kind=PROJECT_DOCUMENT_TTL_SNAPSHOT_KIND,
            source_id=doc.id,
            text_content=body[:8000],
            created_at=datetime.now(UTC),
        )
        await self.db.flush()
        try:
            vec = (await self.ai_providers.embed_texts([body[:8000]]))[0]
            row.embedding_vector = normalize_embedding_for_vector(vec)
        except Exception as exc:
            logger.warning(
                "document_ttl_snapshot_embed_failed document_id=%s error=%s", doc.id, exc
            )
        increment_memory_metric("memory_ttl_document_snapshots")

    async def _snapshot_expiring_agent_memory(self, mem: AgentMemoryEntry) -> None:
        if not mem.project_id:
            return
        project = await self.db.get(OrchestratorProject, mem.project_id)
        if project is None:
            return
        existing = await self.repo.get_episodic_index_row(
            mem.project_id, AGENT_MEMORY_TTL_SNAPSHOT_KIND, mem.id
        )
        if existing:
            return
        body = (
            f"[agent_memory_ttl] id={mem.id} key={mem.key}\n{(mem.value_text or '')[:6000]}"
        ).strip()
        if not body:
            return
        row = await self.repo.create_episodic_search_index_row(
            owner_id=project.owner_id,
            project_id=mem.project_id,
            source_kind=AGENT_MEMORY_TTL_SNAPSHOT_KIND,
            source_id=mem.id,
            text_content=body[:8000],
            created_at=datetime.now(UTC),
        )
        await self.db.flush()
        try:
            vec = (await self.ai_providers.embed_texts([body[:8000]]))[0]
            row.embedding_vector = normalize_embedding_for_vector(vec)
        except Exception as exc:
            logger.warning(
                "agent_memory_ttl_snapshot_embed_failed memory_id=%s error=%s", mem.id, exc
            )
        increment_memory_metric("memory_ttl_agent_memory_snapshots")

    async def sweep_expired_memory_globally(self) -> dict[str, int]:
        """TTL soft-delete; episodic snapshot row first (retrieval), then mark deleted."""
        now = datetime.now(UTC)
        from sqlalchemy import select

        batch_size = max(1, settings.MEMORY_RETENTION_SWEEP_BATCH_SIZE)
        docs = list(
            (
                await self.db.execute(
                    select(ProjectDocument)
                    .where(
                        ProjectDocument.expires_at.isnot(None),
                        ProjectDocument.expires_at <= now,
                        ProjectDocument.deleted_at.is_(None),
                    )
                    .limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        for doc in docs:
            await self._snapshot_expiring_project_document(doc)
        mems = list(
            (
                await self.db.execute(
                    select(AgentMemoryEntry)
                    .where(
                        AgentMemoryEntry.expires_at.isnot(None),
                        AgentMemoryEntry.expires_at <= now,
                        AgentMemoryEntry.deleted_at.is_(None),
                    )
                    .limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        for mem in mems:
            await self._snapshot_expiring_agent_memory(mem)
        await self.db.flush()
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
        semantic_rows = list(
            (
                await self.db.execute(
                    select(SemanticMemoryEntry)
                    .where(
                        SemanticMemoryEntry.expires_at.is_not(None),
                        SemanticMemoryEntry.expires_at <= now,
                        SemanticMemoryEntry.deleted_at.is_(None),
                    )
                    .limit(batch_size)
                )
            )
            .scalars()
            .all()
        )
        for entry in semantic_rows:
            entry.deleted_at = now
            entry.embedding_vector = None
        await self.db.flush()
        await self.db.commit()
        increment_memory_metric("memory_expiration_sweeps")
        return {
            "expired_documents": doc_result.rowcount or 0,
            "expired_memory_entries": mem_result.rowcount or 0,
            "expired_semantic_entries": len(semantic_rows),
        }

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
                asset_class=StorageAssetClass.PRIVATE,
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
        return await self.repo.list_documents(project_id, task_id)

    async def delete_document(self, user: User, project_id: str, document_id: str) -> None:
        await self.get_project(user, project_id)
        item = await self.repo.get_document(project_id, document_id)
        if not item:
            raise HTTPException(status_code=404, detail="Document not found")
        item.deleted_at = datetime.now(UTC)
        item.updated_at = datetime.now(UTC)
        await self.db.commit()
        await invalidate_project_knowledge_caches(project_id)

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
            owner_id=user.id,
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
        owner_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Semantic / RAG retrieval only.

        Results may enrich prompts but must never determine run lifecycle, task status
        transitions, or approval outcomes. Authoritative execution state is relational;
        see ``execution_state`` and the task/run execution-snapshot read APIs.
        """
        if resolve_rag_config().enabled:
            matches = await RetrieverService(self.db).retrieve(
                query,
                filters=RagSearchFilters(
                    user_id=owner_id,
                    project_id=project_id,
                    task_id=task_id,
                    source_kind=source_kind,
                    include_decisions=include_decisions,
                ),
                limit=top_k,
            )
            return [
                {
                    "hit_kind": item.hit_kind,
                    "document_id": item.document_id,
                    "chunk_id": item.chunk_id,
                    "filename": item.title,
                    "chunk_index": item.chunk_index,
                    "score": round(float(item.score), 4),
                    "content": item.content,
                    "metadata": item.metadata,
                    "decision_id": item.chunk_id if item.hit_kind == "decision" else None,
                }
                for item in matches
            ]

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
            if settings.vector_python_fallback_enabled:
                chunks = await self.repo.list_document_chunks(
                    project_id,
                    task_id=task_id,
                    source_kind=source_kind,
                    limit=settings.RAG_CHUNK_FALLBACK_MAX,
                )
            else:
                chunks = []
            if not chunks and not include_decisions:
                return []
            documents = {
                item.id: item
                for item in await self.repo.list_documents(project_id, task_id, limit=0)
            }
            for chunk in chunks:
                if not chunk.embedding_json:
                    continue
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
                        "score": round(
                            _cosine_similarity(query_embedding, chunk.embedding_json), 4
                        ),
                        "content": chunk.content,
                        "metadata": chunk.metadata_json or {},
                        "decision_id": None,
                    }
                )
            merged.sort(key=lambda item: item["score"], reverse=True)
            merged = merged[:cap]

        if include_decisions:
            decisions = await self.repo.list_project_decisions(project_id, query=query)
            dec_hits: list[dict[str, Any]] = []
            for d in decisions:
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
            merged = sorted(
                [*merged, *dec_hits[:cap]], key=lambda item: item["score"], reverse=True
            )[:cap]

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
        return await self.repo.list_agent_memory(
            user.id,
            project_id=project_id,
            agent_id=agent_id,
            status=status,
        )

    async def create_project_agent_memory(
        self,
        user: User,
        project_id: str,
        *,
        agent_id: str,
        key: str,
        value_text: str,
        scope: str = "project-only",
        ttl_days: int | None = None,
    ) -> AgentMemoryEntry | ApprovalRequest:
        """Create explicit agent memory while gating durable writes for review."""
        project = await self.get_project(user, project_id)
        agent = await self.repo.get_agent(user.id, agent_id)
        if agent is None or (agent.project_id is not None and agent.project_id != project_id):
            raise HTTPException(status_code=404, detail="Agent not found in this project")
        normalized_key = key.strip()
        normalized_value = value_text.strip()
        if not normalized_key or not normalized_value:
            raise HTTPException(status_code=422, detail="key and value_text are required")
        if scope not in {"project-only", "long-term"}:
            raise HTTPException(status_code=422, detail="scope must be project-only or long-term")
        effective_ttl = ttl_days if ttl_days is not None else (180 if scope == "long-term" else 30)
        status = "pending" if scope == "long-term" else "approved"
        memory = await self.repo.create_agent_memory(
            owner_id=project.owner_id,
            agent_id=agent.id,
            project_id=project_id,
            key=normalized_key,
            value_text=normalized_value,
            scope=scope,
            status=status,
            ttl_days=effective_ttl,
            expires_at=datetime.now(UTC) + timedelta(days=effective_ttl),
            metadata_json={"source": "manual_memory_write"},
        )
        if status == "pending":
            approval = await self.repo.create_approval(
                project_id=project_id,
                task_id=None,
                run_id=None,
                requested_by_user_id=user.id,
                approval_type="agent_memory_write",
                status="pending",
                payload_json={
                    "memory_entry_id": memory.id,
                    "key": normalized_key,
                    "value_text": normalized_value,
                    "source": "manual_memory_write",
                },
            )
            await self.db.commit()
            await self.db.refresh(approval)
            return approval
        await self.db.commit()
        await self.db.refresh(memory)
        await self._maybe_promote_agent_memory_to_semantic(user, project, memory)
        return memory

    async def delete_memory_entry(self, user: User, project_id: str, memory_id: str) -> None:
        await self.get_project(user, project_id)
        entry = await self.repo.get_agent_memory(user.id, memory_id)
        if entry is None or entry.project_id != project_id:
            raise HTTPException(status_code=404, detail="Memory entry not found")
        entry.deleted_at = datetime.now(UTC)
        entry.status = "deleted"
        await self.db.commit()

    def _decision_text_relevance_score(self, query: str, title: str, body: str) -> float:
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", (query or "").lower())}
        if not q_tokens:
            return 0.0
        blob = f"{title} {body}".lower()
        t_tokens = set(re.findall(r"[a-z0-9]{3,}", blob))
        if not t_tokens:
            return 0.0
        return len(q_tokens & t_tokens) / max(len(q_tokens), 1)

    async def _index_project_document(self, document: ProjectDocument) -> None:
        if resolve_rag_config().enabled:
            await DocumentIngestionService(self.db).index_project_document(document)
            return
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
        await invalidate_project_knowledge_caches(document.project_id)

    async def _build_company_brief_section(self, project: OrchestratorProject) -> str:
        company_id = await self._ensure_company_id_for_project(project)
        if not company_id:
            return ""
        from backend.modules.companies.models import Company

        company = await self.db.get(Company, company_id)
        if company is None:
            return ""
        brief = (company.brief_markdown or "").strip()
        return brief[:500]

    async def _build_agent_preferences_section(self, agent: AgentProfile) -> str:
        from backend.modules.memory.models import SemanticMemoryEntry as _Sem

        prefix = f"agent/{agent.id}/preferences"
        res = await self.db.execute(
            select(_Sem)
            .where(
                _Sem.owner_id == agent.owner_id,
                _Sem.namespace.startswith(prefix),
            )
            .order_by(_Sem.updated_at.desc())
            .limit(8)
        )
        rows = list(res.scalars().all())
        if not rows:
            return ""
        return "\n".join(f"- {r.title}: {(r.body or '')[:200]}" for r in rows)

    async def _build_agent_memory_context(self, agent: AgentProfile | None, project_id: str) -> str:
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
            owner_id=run.triggered_by_user_id,
        )
        if resolve_rag_config().enabled:
            rag_matches = [
                RagChunkMatch(
                    chunk_id=str(item["chunk_id"]),
                    document_id=str(item["document_id"]),
                    title=str(item["filename"]),
                    content=str(item["content"]),
                    chunk_index=int(item["chunk_index"]),
                    score=float(item["score"]),
                    metadata=dict(item.get("metadata") or {}),
                    hit_kind=str(item.get("hit_kind") or "chunk"),
                )
                for item in matches
            ]
            return RagPromptBuilder().build_context_block(rag_matches)
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
        events = await self.repo.list_run_events_tail(run.id, limit=8)
        summary = "\n".join(f"{item.event_type}: {item.message[:180]}" for item in events)
        run.checkpoint_json = {
            **(run.checkpoint_json or {}),
            "scratchpad_summary": summary[:2000],
            "last_event_count": await self.repo.count_run_events(run.id),
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
                    payload_json={
                        "memory_entry_id": memory.id,
                        "key": key,
                        "value_text": value_text,
                    },
                )

    async def _build_episodic_recall_sections(
        self,
        run: TaskRun,
        task: OrchestratorTask,
        project: OrchestratorProject,
        agent: AgentProfile | None,
        wm_block: str,
    ) -> tuple[str, str]:
        episodic_recall_block = ""
        deep_recall_block = ""
        ms = merge_memory_settings(project.settings_json)
        depth = int(ms.get("episodic_retrieval_depth") or 8)
        cand = int(ms.get("deep_recall_episodic_candidates") or 24)
        q_title = (task.title or "")[:200]
        if ms.get("deep_recall_mode"):
            try:
                q_text = "\n".join(
                    [
                        task.title or "",
                        (task.description or "")[:500],
                        wm_block[:1200] if wm_block else "",
                    ]
                ).strip()[:6000]
                qv = (await self.ai_providers.embed_texts([q_text or q_title]))[0]
                min_hits = max(1, int(ms.get("retrieval_stage_min_hits") or 3))
                rel_cap = max(1, int(ms.get("retrieval_cross_project_limit") or 6))
                company_id_ctx = await self._ensure_company_id_for_project(project)
                run_agent_id = (
                    run.worker_agent_id
                    or run.orchestrator_agent_id
                    or (task.assigned_agent_id if task else None)
                )
                per_sem = max(3, min(8, cand // 3))
                (sem_vec, _smeta), (epi_vec, _emeta) = await asyncio.gather(
                    staged_semantic_vector_retrieval(
                        self.repo,
                        owner_id=project.owner_id,
                        project_id=project.id,
                        task_id=task.id,
                        company_id=company_id_ctx,
                        agent_id=run_agent_id,
                        query_vec=qv,
                        min_hits=min_hits,
                        per_stage_limit=per_sem,
                        related_project_limit=rel_cap,
                    ),
                    staged_episodic_vector_retrieval(
                        self.repo,
                        owner_id=project.owner_id,
                        project_id=project.id,
                        company_id=company_id_ctx,
                        agent_id=run_agent_id,
                        query_vec=qv,
                        min_hits=min_hits,
                        per_stage_limit=min(cand, 40),
                        related_project_limit=rel_cap,
                    ),
                )
                lines_e = [f"- [episodic] {(r.text_content or '')[:320]}" for r in epi_vec[:cand]]
                lines_s = [
                    f"- [semantic:{e.entry_type}] {e.title}: {(e.body or '')[:240]}"
                    for e in sem_vec[: max(8, per_sem)]
                ]
                if len(lines_e) + len(lines_s) < min_hits:
                    manifests = await self.repo.list_episodic_archive_manifests(
                        project.owner_id, project.id, limit=5
                    )
                    for m in manifests:
                        rc = int(getattr(m, "record_count", 0) or 0)
                        ps = m.period_start.isoformat() if m.period_start else "?"
                        pe = m.period_end.isoformat() if m.period_end else "?"
                        lines_e.append(f"- [archive] {ps}..{pe} records={rc}")
                deep_recall_block = "\n".join(lines_e + lines_s)
            except Exception as exc:
                logger.warning("deep_recall_mode assembly failed: %s", exc)
        elif ms.get("second_stage_rag"):
            min_h = max(1, int(ms.get("retrieval_stage_min_hits") or 3))
            hits = await self.repo.search_episodic_for_project(
                project.id,
                query=q_title or None,
                limit=min(depth, 24),
                task_id=task.id,
            )
            increment_memory_metric(
                "retrieval_kw_episodic_task_hit" if hits else "retrieval_kw_episodic_task_miss"
            )
            increment_memory_metric("retrieval_scope_episodic_task_kw")
            if len(hits) < min_h:
                hits_proj = await self.repo.search_episodic_for_project(
                    project.id,
                    query=q_title or None,
                    limit=min(depth, 24),
                    task_id=None,
                )
                by_key = {(h["kind"], h["id"]): h for h in hits}
                for h in hits_proj:
                    by_key.setdefault((h["kind"], h["id"]), h)
                hits = sorted(by_key.values(), key=lambda x: x["created_at"], reverse=True)[
                    : min(depth, 24)
                ]
                increment_memory_metric(
                    "retrieval_kw_episodic_project_hit"
                    if hits_proj
                    else "retrieval_kw_episodic_project_miss"
                )
                increment_memory_metric("retrieval_scope_episodic_project_kw")
            if hits:
                lines = [f"- [{h['kind']}] {h['snippet'][:280]}" for h in hits[:depth]]
                episodic_recall_block = "\n".join(lines)
        return episodic_recall_block, deep_recall_block

    async def _assemble_user_context_packet(
        self,
        run: TaskRun,
        agent: AgentProfile | None,
        *,
        prefix: str | None = None,
    ) -> ContextPacket:
        fingerprint = "|".join(
            [
                str(run.id),
                str(getattr(agent, "id", "") or ""),
                str(prefix or ""),
                str(((run.checkpoint_json or {}).get("workflow") or {}).get("resume_count") or 0),
                str(run.status or ""),
            ]
        )
        if run.project_id:
            cached_sections = await get_cached_memory_context(run.project_id, fingerprint)
            if cached_sections:
                return ContextPacket(sections=cached_sections)

        async def _none() -> None:
            return None

        task, project = await asyncio.gather(
            self.db.get(OrchestratorTask, run.task_id) if run.task_id else _none(),
            self.db.get(OrchestratorProject, run.project_id) if run.project_id else _none(),
        )
        if task and project is None and task.project_id:
            project = await self.db.get(OrchestratorProject, task.project_id)

        wm_block = format_working_memory_for_prompt(
            working_memory_from_checkpoint(run.checkpoint_json)
        )
        replay = (
            (run.input_payload_json or {}).get("orchestration_replay")
            if run.input_payload_json
            else None
        )
        replay_block = ""
        if isinstance(replay, dict) and replay.get("prior_transcript"):
            replay_block = (
                "Replay context (carry forward from a previous run; continue without repeating completed steps):\n"
                f"{replay.get('prior_transcript')}"
            )

        load_keys: list[str] = ["scratchpad"]
        load_coros: list[Any] = [self._build_run_scratchpad_context(run)]
        if agent:
            load_keys.extend(["agent_memory", "agent_prefs"])
            load_coros.extend(
                [
                    self._build_agent_memory_context(agent, run.project_id),
                    self._build_agent_preferences_section(agent),
                ]
            )
        if task:
            load_keys.extend(["context_docs", "comments", "artifacts"])
            load_coros.extend(
                [
                    self._build_project_knowledge_context(run, task),
                    self.repo.list_task_comments(task.id),
                    self.repo.list_task_artifacts(task.id),
                ]
            )
            if project:
                load_keys.extend(
                    ["company_brief", "semantic", "memory_layer", "playbook", "episodic"]
                )
                load_coros.extend(
                    [
                        self._build_company_brief_section(project),
                        self._semantic_context_snippets_for_prompt(task, project),
                        self._build_memory_layer_context_for_run(run, task, project),
                        self._procedural_playbook_excerpt(project, task),
                        self._build_episodic_recall_sections(run, task, project, agent, wm_block),
                    ]
                )

        loaded = dict(zip(load_keys, await asyncio.gather(*load_coros), strict=True))

        scratchpad_summary, previous_run_diff = loaded["scratchpad"]
        agent_memory = loaded.get("agent_memory", "")
        agent_prefs = loaded.get("agent_prefs", "")
        context_docs = loaded.get("context_docs", "")
        recent_comments = ""
        recent_artifacts = ""
        if task:
            comments = loaded.get("comments", [])
            recent_comments = "\n".join(comment.body[:300] for comment in comments[-3:])
            artifacts = loaded.get("artifacts", [])
            recent_artifacts = "\n".join(
                f"{artifact.title}: {(artifact.content or '')[:300]}" for artifact in artifacts[:3]
            )
        company_brief = loaded.get("company_brief", "")
        semantic_block = loaded.get("semantic", "")
        memory_layer_block = loaded.get("memory_layer", "")
        playbook_ex = loaded.get("playbook", "")
        episodic_recall_block, deep_recall_block = loaded.get("episodic", ("", ""))
        project_name = project.name if project else ""
        project_goals = project.goals_markdown if project else ""
        proc_block = build_procedural_snippets(agent, task, project_playbooks_excerpt=playbook_ex)
        shared_bb, priv_bb = "", ""
        if task:
            aid = agent.id if agent else None
            shared_bb, priv_bb = extract_blackboard_sections(task.metadata_json, agent_id=aid)

        sections: dict[str, str] = {}
        if prefix:
            sections["prefix"] = prefix
        if company_brief:
            sections["company_brief"] = f"Company brief:\n{company_brief}"
        if agent:
            sections["agent_label"] = f"Agent: {agent.name}"
            if agent_prefs:
                sections["agent_preferences"] = f"Agent preferences:\n{agent_prefs}"
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
        if memory_layer_block:
            sections["relevant_memory_context"] = memory_layer_block
        if episodic_recall_block:
            sections["episodic_recall"] = (
                f"Episodic recall (second stage):\n{episodic_recall_block}"
            )
        if deep_recall_block:
            sections["deep_recall"] = (
                f"Deep recall (vector episodic + semantic):\n{deep_recall_block}"
            )
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
            sections["input_payload"] = (
                f"Run input payload:\n{json.dumps(run.input_payload_json, indent=2)}"
            )

        sections = dedupe_context_sections(sections)
        packet = ContextPacket(sections=sections)
        log_context_packet_telemetry(packet, run_id=run.id)
        if run.project_id:
            await set_cached_memory_context(run.project_id, fingerprint, dict(packet.sections))
        return packet

    async def _build_task_prompt(
        self,
        run: TaskRun,
        agent: AgentProfile | None,
        *,
        prefix: str | None = None,
    ) -> str:
        project = await self.db.get(OrchestratorProject, run.project_id) if run.project_id else None
        ms = (
            merge_memory_settings(project.settings_json) if project else merge_memory_settings(None)
        )
        grounding_prefix = ""
        if run.run_mode == "review" or ms.get("require_grounded_context"):
            grounding_prefix = (
                "Grounding requirement: Use only information from the context sections below. "
                "If context is insufficient to complete the task, respond with INSUFFICIENT_CONTEXT "
                "and do not invent facts or sources."
            )
        combined_prefix = (
            "\n\n".join(part for part in (grounding_prefix, prefix) if part and part.strip())
            or None
        )
        packet = await self._assemble_user_context_packet(run, agent, prefix=combined_prefix)
        max_chars = int(ms.get("context_packet_max_chars") or 48000)
        max_tok = int(ms.get("context_packet_max_tokens") or 0)
        raw_budgets = ms.get("context_packet_section_token_budgets")
        section_token_budgets: dict[str, int] | None = None
        if isinstance(raw_budgets, dict) and raw_budgets:
            section_token_budgets = {}
            for k, v in raw_budgets.items():
                if isinstance(k, str) and isinstance(v, (int, float)):
                    section_token_budgets[k] = max(0, int(v))
        raw_scores = ms.get("context_packet_section_priority_scores")
        section_priority_scores: dict[str, float] | None = None
        if isinstance(raw_scores, dict) and raw_scores:
            section_priority_scores = {}
            for k, v in raw_scores.items():
                if isinstance(k, str) and isinstance(v, (int, float)):
                    section_priority_scores[k] = max(0.0, min(1.0, float(v)))
        if max_tok > 0:
            return packet.combined_user_prompt(
                max_chars=max_chars,
                max_tokens=max_tok,
                section_token_budgets=section_token_budgets,
                section_priority_scores=section_priority_scores,
            )
        return packet.combined_user_prompt(max_chars=max_chars)
