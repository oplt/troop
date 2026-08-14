from __future__ import annotations

import math
import re

from backend.modules.memory.namespaces import build_namespace as _build_memory_namespace

OPENAI_FAMILY_PROVIDER_TYPES = frozenset({"openai", "openai_compatible", "qwen"})


def _default_semantic_namespace(
    project_id: str | None,
    entry_type: str,
    title: str,
    *,
    scope: str = "project",
    company_id: str | None = None,
    agent_id: str | None = None,
) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", (title or "").lower()).strip("-")[:80] or "entry"
    if scope == "company" and company_id:
        return _build_memory_namespace("company", company_id, entry_type, slug)
    if scope == "agent" and agent_id:
        sub = "preferences" if entry_type == "preference" else "memory"
        return _build_memory_namespace("agent", agent_id, sub, entry_type, slug)
    if project_id:
        return _build_memory_namespace("project", project_id, entry_type, slug)
    return _build_memory_namespace("global", None, entry_type, slug)


def _normalize_task_priority(value: str | None) -> str:
    if not value:
        return "normal"
    v = str(value).strip().lower()
    if v == "medium":
        return "normal"
    return v


def _provider_type_aliases(provider_type: str | None) -> set[str]:
    if not provider_type:
        return set()
    if provider_type in OPENAI_FAMILY_PROVIDER_TYPES:
        return set(OPENAI_FAMILY_PROVIDER_TYPES)
    return {provider_type}


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


def resolve_query_limit(
    limit: int | None,
    *,
    default: int,
    maximum: int,
) -> int:
    """Return a SQL LIMIT clamped to ``maximum``.

    ``limit=0`` historically meant "uncapped"; that is no longer allowed on hot
    list paths — treat it as the configured maximum instead.
    """
    if limit is None:
        effective = default
    elif limit == 0:
        effective = maximum
    else:
        effective = limit
    return max(1, min(effective, maximum))


async def run_orchestration_job(run_id: str) -> None:
    from backend.db.session import SessionLocal
    from backend.modules.orchestration.services.service import OrchestrationService

    async with SessionLocal() as db:
        service = OrchestrationService(db)
        await service.execute_run(run_id)
