from __future__ import annotations

import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict
from time import perf_counter
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import (
    cache_singleflight,
    get_cached_rag_retrieval,
    invalidate_project_rag_retrieval_cache,
    rag_retrieval_cache_key,
    set_cached_rag_retrieval,
)
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.memory.models import ProjectDocument
from backend.modules.observability.metrics import (
    record_context_tokens,
    record_memory_retrieval,
    record_rag_degraded,
    record_rag_retrieval_duration,
)
from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.rag.chunking import ChunkingService
from backend.modules.rag.citations import SourceCitationService
from backend.modules.rag.config import RagConfig
from backend.modules.rag.embedding import EmbeddingService
from backend.modules.rag.fusion import reciprocal_rank_fusion
from backend.modules.rag.observability import RagTimer, log_rag_event
from backend.modules.rag.parsing import DocumentParser, detect_source_type
from backend.modules.rag.prompt_builder import RagPromptBuilder
from backend.modules.rag.reranker import RerankerService
from backend.modules.rag.schemas import RagAnswer, RagChunkMatch, RagSearchFilters
from backend.modules.rag.selection import select_context_matches
from backend.modules.rag.vector_store import PgVectorStoreRepository
from backend.modules.workforce.integrations.drive_acl import actor_can_read_acl

_DRIVE_SOURCE_KINDS = frozenset({"google_drive", "microsoft_drive"})

logger = get_logger(__name__)


class RetrieverService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        config: RagConfig | None = None,
        vector_store: PgVectorStoreRepository | None = None,
        embedder: EmbeddingService | None = None,
        reranker: RerankerService | None = None,
        repo: OrchestrationRepository | None = None,
    ):
        self._db = db
        self._config = config or RagConfig.from_settings()
        self._vector_store = vector_store or PgVectorStoreRepository(db)
        self._embedder = embedder or EmbeddingService(self._config)
        self._reranker = reranker or RerankerService(
            self._config.rerank_enabled,
            mode=self._config.rerank_mode,
        )
        self._repo = repo or OrchestrationRepository(db)
        self._prompt_builder = RagPromptBuilder()
        self._citations = SourceCitationService()

    async def retrieve(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> list[RagChunkMatch]:
        if not self._config.enabled or not filters.project_id:
            return []

        timer = RagTimer()
        cap = limit or self._config.top_k
        cache_key = rag_retrieval_cache_key(
            filters.project_id,
            query,
            task_id=filters.task_id,
            source_kind=filters.source_kind,
            include_decisions=filters.include_decisions,
            limit=cap,
            actor_email=filters.actor_email,
        )
        cached_payload = await get_cached_rag_retrieval(cache_key)
        if cached_payload is not None:
            record_memory_retrieval(
                "rag",
                "cache_hit",
                timer.elapsed_ms / 1000.0,
            )
            log_rag_event(
                "retrieve_cache_hit",
                project_id=filters.project_id,
                user_id=filters.user_id,
                count=len(cached_payload),
                duration_ms=timer.elapsed_ms,
            )
            return [RagChunkMatch(**item) for item in cached_payload]

        async def fill() -> list[RagChunkMatch]:
            # Re-check after acquiring the single-flight lock so waiters do not
            # repeat the vector search when the first caller has filled Redis.
            cached_after_wait = await get_cached_rag_retrieval(cache_key)
            if cached_after_wait is not None:
                return [RagChunkMatch(**item) for item in cached_after_wait]

            query_vec = (await self._embedder.embed_texts([query.strip() or "context"]))[0]
            candidate_cap = max(cap, self._config.candidate_top_k)
            rankings: list[list[RagChunkMatch]] = []
            vector_failed = False
            vector_started = perf_counter()
            try:
                vector_hits = await self._vector_store.search(
                    filters.project_id,
                    query_vec,
                    filters=filters,
                    limit=candidate_cap,
                )
            except Exception as exc:
                vector_failed = True
                record_rag_retrieval_duration(
                    stage="vector_search",
                    outcome="error",
                    duration_seconds=perf_counter() - vector_started,
                )
                record_rag_degraded(
                    reason=type(exc).__name__,
                    fallback=("python" if self._config.python_fallback_enabled else "lexical_only"),
                )
                log_rag_event(
                    "retrieve_vector_degraded",
                    project_id=filters.project_id,
                    user_id=filters.user_id,
                    level="warning",
                )
                vector_hits = []
            else:
                record_rag_retrieval_duration(
                    stage="vector_search",
                    outcome="success",
                    duration_seconds=perf_counter() - vector_started,
                )

            threshold = self._config.effective_score_threshold()
            vector_matches = [
                item for item in self._hits_from_vector_rows(vector_hits) if item.score >= threshold
            ]
            vector_matches = self._filter_drive_acl_matches(
                vector_matches,
                actor_email=filters.actor_email,
            )
            if vector_matches:
                rankings.append(vector_matches)

            if self._config.hybrid_search_enabled:
                lexical_started = perf_counter()
                try:
                    lexical_hits = await self._vector_store.text_search(
                        filters.project_id,
                        query,
                        filters=filters,
                        limit=candidate_cap,
                    )
                except Exception:
                    record_rag_retrieval_duration(
                        stage="lexical_search",
                        outcome="error",
                        duration_seconds=perf_counter() - lexical_started,
                    )
                else:
                    record_rag_retrieval_duration(
                        stage="lexical_search",
                        outcome="success",
                        duration_seconds=perf_counter() - lexical_started,
                    )
                    lexical_matches = self._filter_drive_acl_matches(
                        self._hits_from_vector_rows(lexical_hits),
                        actor_email=filters.actor_email,
                    )
                    if lexical_matches:
                        rankings.append(lexical_matches)

            if (vector_failed or not vector_matches) and self._config.python_fallback_enabled:
                record_rag_degraded(
                    reason="vector_unavailable" if vector_failed else "no_vector_matches",
                    fallback="python",
                )
                log_rag_event(
                    "retrieve_python_fallback",
                    project_id=filters.project_id,
                    user_id=filters.user_id,
                    level="warning",
                )
                fallback_matches = await self._fallback_search(
                    filters.project_id,
                    query_vec,
                    filters,
                    candidate_cap,
                )
                if fallback_matches:
                    rankings.append(fallback_matches)

            if filters.include_decisions:
                decision_matches = await self._decision_matches(
                    filters.project_id,
                    query,
                    candidate_cap,
                )
                if decision_matches:
                    rankings.append(decision_matches)
                if filters.user_id:
                    semantic_matches = await self._semantic_memory_matches(
                        filters.user_id,
                        filters.project_id,
                        query_vec,
                        candidate_cap,
                    )
                    if semantic_matches:
                        rankings.append(semantic_matches)

            matches = reciprocal_rank_fusion(
                rankings,
                limit=candidate_cap,
                rank_constant=self._config.rrf_k,
            )
            matches = self._filter_drive_acl_matches(matches, actor_email=filters.actor_email)
            rerank_cap = min(len(matches), max(1, self._config.rerank_top_n))
            matches = self._reranker.rerank(query, matches[:rerank_cap])
            matches = select_context_matches(
                matches,
                limit=cap,
                max_context_tokens=self._config.max_context_tokens,
                max_chunks_per_document=self._config.max_chunks_per_document,
                max_chunks_per_source=self._config.max_chunks_per_source,
                dedup_similarity_threshold=self._config.dedup_similarity_threshold,
                estimate_tokens=PgVectorStoreRepository.estimate_tokens,
            )
            await set_cached_rag_retrieval(cache_key, matches)
            return matches

        matches = await cache_singleflight(f"rag-retrieve:{cache_key}", fill)

        log_rag_event(
            "retrieve",
            project_id=filters.project_id,
            user_id=filters.user_id,
            count=len(matches),
            duration_ms=timer.elapsed_ms,
        )
        record_memory_retrieval("rag", "success", timer.elapsed_ms / 1000.0)
        return matches

    async def build_context(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> str:
        matches = await self.retrieve(query, filters=filters, limit=limit)
        record_context_tokens(
            pipeline="rag",
            tokens=sum(PgVectorStoreRepository.estimate_tokens(item.content) for item in matches),
        )
        return self._prompt_builder.build_context_block(matches)

    def _hits_from_vector_rows(self, rows: list[dict[str, Any]]) -> list[RagChunkMatch]:
        out: list[RagChunkMatch] = []
        for row in rows:
            out.append(
                RagChunkMatch(
                    chunk_id=str(row["chunk_id"]),
                    document_id=str(row["project_document_id"]),
                    title=str(row.get("filename") or "document"),
                    content=str(row.get("content") or ""),
                    chunk_index=int(row.get("chunk_index") or 0),
                    score=float(row.get("score") or 0.0),
                    metadata=dict(row.get("metadata_json") or {}),
                )
            )
        return out

    @staticmethod
    def _filter_drive_acl_matches(
        matches: list[RagChunkMatch],
        *,
        actor_email: str | None,
    ) -> list[RagChunkMatch]:
        filtered: list[RagChunkMatch] = []
        for match in matches:
            source_kind = str(match.metadata.get("source_kind") or "")
            if source_kind not in _DRIVE_SOURCE_KINDS:
                filtered.append(match)
                continue
            if not actor_email:
                continue
            acl_snapshot = match.metadata.get("acl_snapshot")
            if actor_can_read_acl(acl_snapshot, actor_email=actor_email):
                filtered.append(match)
        return filtered

    async def _fallback_search(
        self,
        project_id: str,
        query_vec: list[float],
        filters: RagSearchFilters,
        cap: int,
    ) -> list[RagChunkMatch]:
        chunks = await self._vector_store.list_chunks_fallback(project_id, filters=filters)
        if not chunks:
            return []
        cap = min(cap, self._config.chunk_fallback_max)
        documents = {
            d.id: d for d in await self._repo.list_documents(project_id, filters.task_id, limit=0)
        }
        matches: list[RagChunkMatch] = []
        for chunk in chunks:
            if not chunk.embedding_json:
                continue
            doc = documents.get(chunk.project_document_id)
            if doc is None:
                continue
            score = PgVectorStoreRepository.cosine_similarity(query_vec, chunk.embedding_json)
            matches.append(
                RagChunkMatch(
                    chunk_id=chunk.id,
                    document_id=doc.id,
                    title=doc.filename,
                    content=chunk.content,
                    chunk_index=chunk.chunk_index,
                    score=score,
                    metadata=dict(chunk.metadata_json or {}),
                )
            )
        matches.sort(key=lambda item: item.score, reverse=True)
        return self._filter_drive_acl_matches(matches[:cap], actor_email=filters.actor_email)

    async def _decision_matches(
        self,
        project_id: str,
        query: str,
        cap: int,
    ) -> list[RagChunkMatch]:
        decisions = await self._repo.list_project_decisions(
            project_id,
            query=query,
            limit=cap,
        )
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
        extra: list[RagChunkMatch] = []
        for decision in decisions:
            title = decision.title or ""
            body = decision.decision or ""
            blob = f"{title} {body}".lower()
            t_tokens = set(re.findall(r"[a-z0-9]{3,}", blob))
            score = len(q_tokens & t_tokens) / max(len(q_tokens), 1) if q_tokens else 0.0
            if score <= 0 and query.strip():
                continue
            extra.append(
                RagChunkMatch(
                    chunk_id=decision.id,
                    document_id=decision.id,
                    title=title or "decision",
                    content="\n".join(x for x in [title, body, decision.rationale or ""] if x),
                    chunk_index=0,
                    score=score,
                    hit_kind="decision",
                )
            )
        return sorted(extra, key=lambda item: item.score, reverse=True)[:cap]

    async def _semantic_memory_matches(
        self,
        owner_id: str,
        project_id: str,
        query_vec: list[float],
        cap: int,
    ) -> list[RagChunkMatch]:
        entries = await self._repo.search_semantic_memory_by_vector(
            owner_id,
            project_id,
            query_vec,
            limit=cap,
        )
        return [
            RagChunkMatch(
                chunk_id=entry.id,
                document_id=str(entry.source_chunk_id or entry.id),
                title=entry.title or "memory",
                content=entry.body or "",
                chunk_index=0,
                score=1.0 / rank,
                hit_kind="semantic_memory",
                metadata={
                    **dict(entry.metadata_json or {}),
                    "source_id": entry.source_chunk_id or entry.id,
                    "source_task_id": entry.source_task_id,
                    "source_run_id": entry.source_run_id,
                    "provenance": dict(entry.provenance_json or {}),
                },
            )
            for rank, entry in enumerate(entries, start=1)
        ]


class DocumentIngestionService:
    def __init__(
        self,
        db: AsyncSession,
        *,
        config: RagConfig | None = None,
        parser: DocumentParser | None = None,
        chunker: ChunkingService | None = None,
        embedder: EmbeddingService | None = None,
        vector_store: PgVectorStoreRepository | None = None,
        repo: OrchestrationRepository | None = None,
    ):
        self._db = db
        self._config = config or RagConfig.from_settings()
        self._parser = parser or DocumentParser()
        self._chunker = chunker or ChunkingService(self._config)
        self._embedder = embedder or EmbeddingService(self._config)
        self._vector_store = vector_store or PgVectorStoreRepository(db)
        self._repo = repo or OrchestrationRepository(db)

    async def index_project_document(self, document: ProjectDocument) -> int:
        timer = RagTimer()
        from backend.modules.memory.layer.redaction import sanitize_for_storage

        safe_source, redaction_hits = sanitize_for_storage(document.source_text or "")
        if safe_source is None:
            document.ingestion_status = "failed"
            document.metadata_json = {
                **(document.metadata_json or {}),
                "ingest_error": "blocked_by_redaction",
                "redaction_applied": redaction_hits,
            }
            await self._db.flush()
            log_rag_event(
                "index_redaction_blocked",
                project_id=document.project_id,
                document_id=document.id,
                level="warning",
            )
            return 0

        source_type = detect_source_type(document.content_type, document.filename)
        normalized = self._parser.normalize_document(
            document_id=document.id,
            source_id=document.id,
            source_type=source_type,
            title=document.filename,
            content=safe_source,
            owner_user_id=document.uploaded_by_user_id,
            project_id=document.project_id,
            metadata=dict(document.metadata_json or {}),
        )
        rag_chunks = self._chunker.build_chunks(
            document_id=normalized.document_id,
            source_id=normalized.source_id,
            source_type=normalized.source_type,
            title=normalized.title,
            content=normalized.content,
            owner_user_id=normalized.owner_user_id,
            project_id=normalized.project_id,
            metadata=normalized.metadata,
        )

        existing = await self._vector_store.list_document_chunks_for_document(document.id)
        existing_vectors: dict[str, list[list[float]]] = {}
        for item in existing:
            content_hash = str((item.metadata_json or {}).get("content_hash") or "")
            stored_vector = item.embedding_vector
            if stored_vector is None or len(stored_vector) == 0:
                stored_vector = item.embedding_json
            if content_hash and stored_vector is not None and len(stored_vector) > 0:
                existing_vectors.setdefault(content_hash, []).append(
                    [float(value) for value in stored_vector]
                )

        embeddings: list[list[float] | None] = []
        changed_indexes: list[int] = []
        changed_texts: list[str] = []
        for index, chunk in enumerate(rag_chunks):
            reusable = existing_vectors.get(chunk.content_hash, [])
            if reusable:
                embeddings.append(reusable.pop(0))
            else:
                embeddings.append(None)
                changed_indexes.append(index)
                changed_texts.append(chunk.content)

        if changed_texts:
            changed_embeddings = await self._embedder.embed_texts(changed_texts)
            for index, embedding in zip(changed_indexes, changed_embeddings, strict=True):
                embeddings[index] = embedding
        rows = [
            (
                chunk.chunk_index,
                chunk.content,
                PgVectorStoreRepository.estimate_tokens(chunk.content),
                embeddings[index] or [],
                {
                    **chunk.metadata,
                    "content_hash": chunk.content_hash,
                    "rag_chunk_id": chunk.chunk_id,
                },
            )
            for index, chunk in enumerate(rag_chunks)
        ]
        await self._vector_store.upsert_document_chunks(document, rows)
        document.ingestion_status = "completed"
        document.chunk_count = len(rag_chunks)
        document.summary_text = (document.summary_text or normalized.content[:500])[:1000]
        document.metadata_json = {
            **(document.metadata_json or {}),
            "checksum": normalized.checksum,
            "source_type": normalized.source_type,
        }
        if redaction_hits:
            document.metadata_json["redaction_applied"] = redaction_hits
        await self._db.flush()
        await invalidate_project_rag_retrieval_cache(document.project_id)
        log_rag_event(
            "index_complete",
            project_id=document.project_id,
            document_id=document.id,
            count=len(rag_chunks),
            duration_ms=timer.elapsed_ms,
        )
        return len(rag_chunks)


class RagAnswerService:
    def __init__(
        self,
        retriever: RetrieverService,
        *,
        config: RagConfig | None = None,
        providers: AiProviderRegistry | None = None,
        generation_config_resolver: Callable[
            [RagSearchFilters], Awaitable[tuple[ProviderConfig | None, str, str]]
        ]
        | None = None,
    ):
        self._retriever = retriever
        self._config = config or RagConfig.from_settings()
        self._providers = providers or AiProviderRegistry()
        self._prompt_builder = RagPromptBuilder()
        self._citations = SourceCitationService()
        self._generation_config_resolver = generation_config_resolver

    async def _resolve_generation_config(
        self,
        filters: RagSearchFilters,
    ) -> tuple[ProviderConfig | None, str, str]:
        if self._generation_config_resolver is None:
            return None, settings.OPENAI_DEFAULT_MODEL, settings.AI_DEFAULT_PROVIDER
        return await self._generation_config_resolver(filters)

    async def answer(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> RagAnswer:
        timer = RagTimer()
        matches = await self._retriever.retrieve(query, filters=filters, limit=limit)
        citations = self._citations.to_citations(matches)

        if not matches:
            log_rag_event(
                "answer_no_context",
                project_id=filters.project_id,
                user_id=filters.user_id,
                duration_ms=timer.elapsed_ms,
                level="warning",
            )
            return RagAnswer(
                query=query,
                answer=self._prompt_builder.no_context_answer(),
                citations=[],
                grounded=True,
                context_found=False,
            )

        system_prompt, user_prompt = self._prompt_builder.build_answer_prompt(query, matches)
        provider_config, model, provider_key = await self._resolve_generation_config(filters)
        if provider_config is not None:
            provider_result = await execute_prompt(
                provider_config,
                model_name=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format="text",
            )
            output_text = provider_result.output_text
            result_model = provider_result.model_name
            result_provider = provider_config.provider_type
        else:
            result = await self._providers.generate(
                ProviderGenerateRequest(
                    model=model,
                    system_prompt=system_prompt,
                    user_prompt=user_prompt,
                    response_format="text",
                    temperature=0.0,
                ),
                provider_key=provider_key,
            )
            output_text = result.output_text
            result_model = result.model
            result_provider = result.provider_key
        log_rag_event(
            "answer_complete",
            project_id=filters.project_id,
            user_id=filters.user_id,
            count=len(matches),
            duration_ms=timer.elapsed_ms,
        )
        return RagAnswer(
            query=query,
            answer=(output_text or "").strip(),
            citations=citations,
            grounded=True,
            context_found=True,
            model=result_model,
            provider=result_provider,
        )

    async def answer_stream(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> AsyncIterator[dict[str, Any]]:
        timer = RagTimer()
        matches = await self._retriever.retrieve(query, filters=filters, limit=limit)
        citations = self._citations.to_citations(matches)
        citation_payload = [asdict(c) for c in citations]

        yield {
            "type": "meta",
            "query": query,
            "context_found": bool(matches),
            "citations": citation_payload,
        }

        if not matches:
            answer = self._prompt_builder.no_context_answer()
            yield {"type": "token", "text": answer}
            log_rag_event(
                "answer_no_context",
                project_id=filters.project_id,
                user_id=filters.user_id,
                duration_ms=timer.elapsed_ms,
                level="warning",
            )
            yield {
                "type": "done",
                "answer": answer,
                "grounded": True,
                "context_found": False,
                "model": "",
                "provider": "",
            }
            return

        system_prompt, user_prompt = self._prompt_builder.build_answer_prompt(query, matches)
        provider_config, model, provider_key = await self._resolve_generation_config(filters)
        request = ProviderGenerateRequest(
            model=model,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            response_format="text",
            temperature=0.0,
        )
        parts: list[str] = []
        result_model = model
        result_provider = provider_key
        if provider_config is not None:
            provider_result = await execute_prompt(
                provider_config,
                model_name=model,
                system_prompt=system_prompt,
                user_prompt=user_prompt,
                response_format="text",
            )
            token = (provider_result.output_text or "").strip()
            parts.append(token)
            result_model = provider_result.model_name
            result_provider = provider_config.provider_type
            yield {"type": "token", "text": token}
        else:
            async for token in self._providers.stream_generate(request, provider_key=provider_key):
                parts.append(token)
                yield {"type": "token", "text": token}

        answer = "".join(parts).strip()
        log_rag_event(
            "answer_complete",
            project_id=filters.project_id,
            user_id=filters.user_id,
            count=len(matches),
            duration_ms=timer.elapsed_ms,
        )
        yield {
            "type": "done",
            "answer": answer,
            "grounded": True,
            "context_found": True,
            "model": result_model,
            "provider": result_provider,
        }
