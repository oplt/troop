"""Tier-3 staged retrieval: task → project → company → related projects → archive hints."""

from __future__ import annotations

from typing import Any, Protocol

from backend.modules.memory.models import EpisodicSearchIndex, SemanticMemoryEntry
from backend.modules.orchestration.memory_metrics import increment_memory_metric


class MemoryRetrievalRepo(Protocol):
    async def search_semantic_memory_by_vector_scoped(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        *,
        namespace_prefix: str | None,
        source_task_id: str | None,
        limit: int,
    ) -> list[SemanticMemoryEntry]: ...

    async def search_semantic_memory_by_vector(
        self, owner_id: str, project_id: str, query_vec: list[float], *, limit: int
    ) -> list[SemanticMemoryEntry]: ...

    async def search_semantic_memory_by_vector_company(
        self, owner_id: str, company_id: str, query_vec: list[float], *, limit: int
    ) -> list[SemanticMemoryEntry]: ...

    async def search_semantic_memory_by_vector_for_projects(
        self, owner_id: str, project_ids: list[str], query_vec: list[float], *, limit: int
    ) -> list[SemanticMemoryEntry]: ...

    async def search_episodic_index_by_vector(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        *,
        limit: int,
        require_not_archived: bool,
    ) -> list[EpisodicSearchIndex]: ...

    async def search_episodic_index_by_vector_for_projects(
        self,
        owner_id: str,
        project_ids: list[str],
        query_vec: list[float],
        *,
        limit: int,
        require_not_archived: bool,
    ) -> list[EpisodicSearchIndex]: ...

    async def list_related_project_ids_for_retrieval(
        self, owner_id: str, project_id: str, *, agent_id: str | None, limit: int
    ) -> list[str]: ...

    async def list_episodic_archive_manifests(
        self, owner_id: str, project_id: str, *, limit: int
    ) -> list[Any]: ...


def _merge_unique_rows(
    rows: list[SemanticMemoryEntry], seen: set[str], out: list[SemanticMemoryEntry]
) -> int:
    added = 0
    for r in rows:
        if r.id in seen:
            continue
        seen.add(r.id)
        out.append(r)
        added += 1
    return added


async def staged_semantic_vector_retrieval(
    repo: MemoryRetrievalRepo,
    *,
    owner_id: str,
    project_id: str,
    task_id: str,
    company_id: str | None,
    agent_id: str | None,
    query_vec: list[float],
    min_hits: int,
    per_stage_limit: int,
    related_project_limit: int,
) -> tuple[list[SemanticMemoryEntry], dict[str, Any]]:
    out: list[SemanticMemoryEntry] = []
    seen: set[str] = set()
    meta: dict[str, Any] = {"stages": []}
    task_prefix = f"task/{task_id}/"

    rows = await repo.search_semantic_memory_by_vector_scoped(
        owner_id,
        project_id,
        query_vec,
        namespace_prefix=task_prefix,
        source_task_id=task_id,
        limit=per_stage_limit,
    )
    n = _merge_unique_rows(rows, seen, out)
    meta["stages"].append({"scope": "task", "added": n, "total": len(out)})
    increment_memory_metric("retrieval_scope_semantic_task")
    increment_memory_metric("retrieval_vec_semantic_task_hit" if n else "retrieval_vec_semantic_task_miss")
    if len(out) >= min_hits:
        increment_memory_metric("retrieval_scope_early_exit_semantic")
        return out, meta

    rows = await repo.search_semantic_memory_by_vector(
        owner_id, project_id, query_vec, limit=per_stage_limit
    )
    n = _merge_unique_rows(rows, seen, out)
    meta["stages"].append({"scope": "project", "added": n, "total": len(out)})
    increment_memory_metric("retrieval_scope_semantic_project")
    increment_memory_metric("retrieval_vec_semantic_project_hit" if n else "retrieval_vec_semantic_project_miss")
    if len(out) >= min_hits:
        increment_memory_metric("retrieval_scope_early_exit_semantic")
        return out, meta

    if company_id:
        rows = await repo.search_semantic_memory_by_vector_company(
            owner_id, company_id, query_vec, limit=per_stage_limit
        )
        n = _merge_unique_rows(rows, seen, out)
        meta["stages"].append({"scope": "company", "added": n, "total": len(out)})
        increment_memory_metric("retrieval_scope_semantic_company")
        increment_memory_metric("retrieval_vec_semantic_company_hit" if n else "retrieval_vec_semantic_company_miss")
        if len(out) >= min_hits:
            increment_memory_metric("retrieval_scope_early_exit_semantic")
            return out, meta

    related = await repo.list_related_project_ids_for_retrieval(
        owner_id, project_id, agent_id=agent_id, limit=related_project_limit
    )
    if related:
        rows = await repo.search_semantic_memory_by_vector_for_projects(
            owner_id, related, query_vec, limit=per_stage_limit * 2
        )
        n = _merge_unique_rows(rows, seen, out)
        meta["stages"].append(
            {"scope": "cross_project", "added": n, "total": len(out), "project_ids": related}
        )
        increment_memory_metric("retrieval_scope_semantic_cross_project")
        increment_memory_metric(
            "retrieval_vec_semantic_cross_project_hit" if n else "retrieval_vec_semantic_cross_project_miss"
        )
        if len(out) >= min_hits:
            increment_memory_metric("retrieval_scope_early_exit_semantic")
            return out, meta

    return out, meta


async def staged_episodic_vector_retrieval(
    repo: MemoryRetrievalRepo,
    *,
    owner_id: str,
    project_id: str,
    company_id: str | None,
    agent_id: str | None,
    query_vec: list[float],
    min_hits: int,
    per_stage_limit: int,
    related_project_limit: int,
) -> tuple[list[EpisodicSearchIndex], dict[str, Any]]:
    out: list[EpisodicSearchIndex] = []
    seen: set[str] = set()
    meta: dict[str, Any] = {"stages": []}

    def merge_epi(rows: list[EpisodicSearchIndex]) -> int:
        added = 0
        for r in rows:
            if r.id in seen:
                continue
            seen.add(r.id)
            out.append(r)
            added += 1
        return added

    rows = await repo.search_episodic_index_by_vector(
        owner_id,
        project_id,
        query_vec,
        limit=per_stage_limit,
        require_not_archived=True,
    )
    n = merge_epi(rows)
    meta["stages"].append({"scope": "project", "added": n, "total": len(out)})
    increment_memory_metric("retrieval_scope_episodic_project")
    increment_memory_metric("retrieval_vec_episodic_project_hit" if n else "retrieval_vec_episodic_project_miss")
    if len(out) >= min_hits:
        increment_memory_metric("retrieval_scope_early_exit_episodic")
        return out, meta

    related = await repo.list_related_project_ids_for_retrieval(
        owner_id, project_id, agent_id=agent_id, limit=related_project_limit
    )
    if related:
        rows = await repo.search_episodic_index_by_vector_for_projects(
            owner_id,
            related,
            query_vec,
            limit=per_stage_limit * 2,
            require_not_archived=True,
        )
        n = merge_epi(rows)
        meta["stages"].append(
            {"scope": "cross_project", "added": n, "total": len(out), "project_ids": related}
        )
        increment_memory_metric("retrieval_scope_episodic_cross_project")
        increment_memory_metric(
            "retrieval_vec_episodic_cross_project_hit" if n else "retrieval_vec_episodic_cross_project_miss"
        )

    if company_id and len(out) < min_hits:
        meta["stages"].append(
            {
                "scope": "company_note",
                "detail": "episodic index is project-scoped; company layer uses semantic + brief",
            }
        )

    if len(out) < min_hits:
        manifests = await repo.list_episodic_archive_manifests(
            owner_id, project_id, limit=min(6, per_stage_limit)
        )
        meta["archive_manifest_count"] = len(manifests)
        increment_memory_metric("retrieval_scope_episodic_archive_hint")

    return out, meta
