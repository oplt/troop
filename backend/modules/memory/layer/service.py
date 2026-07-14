from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.memory.layer.config import MemoryConfig, resolve_memory_config
from backend.modules.memory.layer.dedup import content_hash, is_duplicate
from backend.modules.memory.layer.extractor import (
    _SYSTEM_PROMPT,
    ExtractedMemory,
    build_llm_extraction_prompt,
    extract_with_rules,
    parse_llm_extraction,
)
from backend.modules.memory.layer.observability import MemoryTimer, log_memory_event
from backend.modules.memory.layer.provider import MemoryProvider, SemanticMemoryProvider
from backend.modules.memory.layer.redaction import sanitize_for_storage
from backend.modules.memory.layer.repository import SqlMemoryRepository
from backend.modules.memory.layer.schemas import MemoryFilters, MemoryRecord, MemoryScope
from backend.modules.memory.lifecycle import (
    MemoryContextLifecycle,
    SemanticMemoryLifecycle,
    resolve_retention,
)
from backend.modules.memory.metrics import increment_memory_metric

logger = get_logger(__name__)


class MemoryService:
    """High-level memory API — mem0-inspired facade over semantic memory storage."""

    def __init__(
        self,
        db: AsyncSession,
        *,
        config: MemoryConfig | None = None,
        provider: MemoryProvider | None = None,
        embedder: AiProviderRegistry | None = None,
    ):
        self._db = db
        self._config = config or resolve_memory_config()
        self._provider = provider or SemanticMemoryProvider(SqlMemoryRepository(db))
        self._semantic = SemanticMemoryLifecycle(self._provider)
        self._context = MemoryContextLifecycle()
        self._embedder = embedder or AiProviderRegistry()
        self._log_content = (
            bool(getattr(settings, "MEMORY_LOG_CONTENT_IN_DEV", False))
            and not settings.is_production
        )

    @property
    def enabled(self) -> bool:
        return self._config.enabled

    async def add_memory(
        self,
        user_id: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        scope: MemoryScope = "project",
        project_id: str | None = None,
        ttl_days: int | None = None,
        retention_policy: str = "default",
    ) -> MemoryRecord | None:
        if not self._config.enabled:
            return None

        timer = MemoryTimer()
        meta = dict(metadata or {})
        meta.setdefault("source", "memory_service")
        meta.setdefault("created_by_user_id", user_id)
        requested_ttl = ttl_days if ttl_days is not None else meta.get("ttl_days")
        try:
            requested_ttl = int(requested_ttl) if requested_ttl is not None else None
        except (TypeError, ValueError):
            requested_ttl = None
        retention = resolve_retention(
            requested_ttl,
            default_ttl_days=self._config.default_ttl_days,
            max_ttl_days=self._config.max_ttl_days,
            policy=retention_policy,
        )
        meta["ttl_days"] = retention.ttl_days
        meta["expires_at"] = retention.expires_at.isoformat() if retention.expires_at else None
        meta["retention_policy"] = retention.policy
        meta.setdefault("memory_version", 1)
        meta.setdefault("embedding_model", getattr(settings, "RAG_EMBEDDING_MODEL", "") or None)
        meta.setdefault("embedding_version", "v1")

        safe_content, redaction_hits = sanitize_for_storage(content)
        if not safe_content:
            log_memory_event(
                "add_blocked",
                user_id=user_id,
                duration_ms=timer.elapsed_ms,
                error="redaction",
            )
            increment_memory_metric("memory_layer_add_blocked")
            return None
        if redaction_hits:
            meta["redaction_applied"] = redaction_hits

        digest = content_hash(safe_content)
        meta["content_hash"] = digest

        filters = MemoryFilters(
            user_id=user_id,
            company_id=meta.get("company_id"),
            project_id=project_id or meta.get("project_id"),
            agent_id=meta.get("agent_id"),
            task_id=meta.get("task_id") or meta.get("source_task_id"),
            session_id=meta.get("session_id"),
            scope=scope,
            namespace_prefix=meta.get("namespace"),
        )
        if self._config.dedup_enabled:
            duplicate = await self._semantic.find_duplicate(user_id, digest, filters)
            if duplicate is not None:
                log_memory_event(
                    "add_dedup_skip",
                    user_id=user_id,
                    memory_id=duplicate.id,
                    duration_ms=timer.elapsed_ms,
                )
                increment_memory_metric("memory_layer_dedup_skip")
                return duplicate

        record = await self._semantic.add(
            owner_id=user_id,
            content=safe_content,
            scope=scope,
            project_id=project_id or meta.get("project_id"),
            metadata=meta,
        )
        await self._db.commit()
        log_memory_event(
            "add",
            user_id=user_id,
            memory_id=record.id,
            duration_ms=timer.elapsed_ms,
            content_preview=safe_content,
            log_content=self._log_content,
        )
        increment_memory_metric("memory_layer_add")
        return record

    async def search_memories(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        filters: MemoryFilters | None = None,
    ) -> list[MemoryRecord]:
        if not self._config.enabled:
            return []

        timer = MemoryTimer()
        effective_limit = limit or self._config.default_search_limit
        effective_filters = filters or MemoryFilters(user_id=user_id)
        effective_filters.user_id = user_id

        query_vec: list[float] | None = None
        if effective_filters.project_id:
            try:
                query_vec = (await self._embedder.embed_texts([query.strip() or "context"]))[0]
            except Exception as exc:
                logger.debug("memory search embedding unavailable: %s", exc)

        records = await self._semantic.search(
            user_id,
            query,
            query_vec=query_vec,
            filters=effective_filters,
            limit=effective_limit,
        )
        log_memory_event(
            "search",
            user_id=user_id,
            count=len(records),
            duration_ms=timer.elapsed_ms,
        )
        increment_memory_metric("memory_layer_search")
        return records

    async def update_memory(
        self,
        memory_id: str,
        *,
        user_id: str,
        content: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> MemoryRecord | None:
        if not self._config.enabled:
            return None

        timer = MemoryTimer()
        safe_content: str | None = None
        meta = dict(metadata or {})
        if content is not None:
            safe_content, redaction_hits = sanitize_for_storage(content)
            if not safe_content:
                log_memory_event(
                    "update_blocked",
                    user_id=user_id,
                    memory_id=memory_id,
                    duration_ms=timer.elapsed_ms,
                    error="redaction",
                )
                return None
            if redaction_hits:
                meta["redaction_applied"] = redaction_hits
            meta["content_hash"] = content_hash(safe_content)
        if "ttl_days" in meta:
            try:
                update_ttl = int(meta["ttl_days"])
            except (TypeError, ValueError) as exc:
                raise ValueError("Memory TTL must be an integer") from exc
            if update_ttl < 0 or update_ttl > self._config.max_ttl_days:
                raise ValueError(
                    f"Memory TTL must be between 0 and {self._config.max_ttl_days} days"
                )
            retention = resolve_retention(
                update_ttl,
                default_ttl_days=0,
                max_ttl_days=self._config.max_ttl_days,
                policy=str(meta.get("retention_policy") or "default"),
            )
            meta["expires_at"] = retention.expires_at.isoformat() if retention.expires_at else None

        record = await self._semantic.update(
            user_id,
            memory_id,
            content=safe_content,
            metadata=meta or None,
        )
        if record is None:
            log_memory_event(
                "update_miss",
                user_id=user_id,
                memory_id=memory_id,
                duration_ms=timer.elapsed_ms,
            )
            return None

        await self._db.commit()
        log_memory_event(
            "update",
            user_id=user_id,
            memory_id=memory_id,
            duration_ms=timer.elapsed_ms,
            content_preview=safe_content or "",
            log_content=self._log_content and bool(safe_content),
        )
        increment_memory_metric("memory_layer_update")
        return record

    async def delete_memory(self, memory_id: str, *, user_id: str) -> bool:
        if not self._config.enabled:
            return False

        timer = MemoryTimer()
        ok = await self._semantic.delete(user_id, memory_id)
        if ok:
            await self._db.commit()
        log_memory_event(
            "delete",
            user_id=user_id,
            memory_id=memory_id,
            duration_ms=timer.elapsed_ms,
            error=None if ok else "not_found",
        )
        increment_memory_metric("memory_layer_delete" if ok else "memory_layer_delete_miss")
        return ok

    async def delete_memories_for_user(self, user_id: str) -> int:
        if not self._config.enabled:
            return 0

        timer = MemoryTimer()
        count = await self._semantic.delete_for_user(user_id)
        await self._db.commit()
        log_memory_event(
            "delete_user",
            user_id=user_id,
            count=count,
            duration_ms=timer.elapsed_ms,
        )
        increment_memory_metric("memory_layer_delete_user")
        return count

    async def build_memory_context(
        self,
        user_id: str,
        query: str,
        *,
        limit: int | None = None,
        filters: MemoryFilters | None = None,
        header: str | None = None,
        max_tokens: int | None = None,
    ) -> str:
        if not self._config.enabled:
            return ""
        records = await self.search_memories(
            user_id,
            query,
            limit=limit,
            filters=filters,
        )
        return self._context.build(
            records,
            header=header,
            query=query,
            max_tokens=max_tokens or self._config.context_max_tokens,
        )

    async def extract_and_store_from_interaction(
        self,
        *,
        user_id: str,
        messages: list[dict[str, str]],
        project_id: str | None = None,
        session_id: str | None = None,
        agent_id: str | None = None,
        scope: MemoryScope = "project",
    ) -> list[MemoryRecord]:
        """Extract durable facts from a conversation and store them."""
        if not self._config.enabled or not self._config.extraction_enabled:
            return []

        timer = MemoryTimer()
        extracted = await self._extract_memories(messages)
        stored: list[MemoryRecord] = []
        seen_hashes: set[str] = set()

        for item in extracted:
            if item.confidence < self._config.min_extraction_confidence:
                continue
            digest = content_hash(item.text)
            if is_duplicate(seen_hashes, item.text):
                continue
            seen_hashes.add(digest)

            record = await self.add_memory(
                user_id,
                item.text,
                metadata={
                    "memory_type": item.memory_type,
                    "confidence": item.confidence,
                    "source": item.source,
                    "project_id": project_id,
                    "session_id": session_id,
                    "agent_id": agent_id,
                    "title": item.text[:80],
                },
                scope=scope,
                project_id=project_id,
            )
            if record is not None:
                stored.append(record)

        log_memory_event(
            "extract_store",
            user_id=user_id,
            count=len(stored),
            duration_ms=timer.elapsed_ms,
        )
        increment_memory_metric("memory_layer_extract_store")
        return stored

    async def _extract_memories(self, messages: list[dict[str, str]]) -> list[ExtractedMemory]:
        rule_based = extract_with_rules(
            messages, min_confidence=self._config.min_extraction_confidence
        )
        if not self._config.llm_extraction_enabled:
            return rule_based

        try:
            prompt = build_llm_extraction_prompt(messages)
            result = await self._embedder.generate(
                ProviderGenerateRequest(
                    model=settings.OPENAI_DEFAULT_MODEL,
                    system_prompt=_SYSTEM_PROMPT,
                    user_prompt=prompt,
                    response_format="json",
                    temperature=0.0,
                )
            )
            llm_items = parse_llm_extraction(result.output_text or "")
            if not llm_items:
                return rule_based
            by_hash = {content_hash(item.text): item for item in rule_based}
            for item in llm_items:
                by_hash.setdefault(content_hash(item.text), item)
            return list(by_hash.values())
        except Exception as exc:
            logger.debug("LLM memory extraction failed, using rules only: %s", exc)
            return rule_based
