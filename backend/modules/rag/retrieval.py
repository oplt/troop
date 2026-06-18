from __future__ import annotations

import logging
import re
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import asdict
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.cache import (
    get_cached_rag_retrieval,
    invalidate_project_rag_retrieval_cache,
    rag_retrieval_cache_key,
    set_cached_rag_retrieval,
)
from backend.core.config import settings
from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.memory.models import ProjectDocument
from backend.modules.orchestration.models import ProviderConfig
from backend.modules.orchestration.providers import execute_prompt
from backend.modules.orchestration.repository import OrchestrationRepository
from backend.modules.rag.chunking import ChunkingService
from backend.modules.rag.citations import SourceCitationService
from backend.modules.rag.config import RagConfig
from backend.modules.rag.embedding import EmbeddingService
from backend.modules.rag.observability import RagTimer, log_rag_event
from backend.modules.rag.parsing import DocumentParser, detect_source_type
from backend.modules.rag.prompt_builder import RagPromptBuilder
from backend.modules.rag.reranker import RerankerService
from backend.modules.rag.schemas import RagAnswer, RagChunkMatch, RagSearchFilters
from backend.modules.rag.vector_store import PgVectorStoreRepository

logger = logging.getLogger(__name__)


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
        self._reranker = reranker or RerankerService(self._config.rerank_enabled)
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
        )
        cached_payload = await get_cached_rag_retrieval(cache_key)
        if cached_payload is not None:
            log_rag_event(
                "retrieve_cache_hit",
                project_id=filters.project_id,
                user_id=filters.user_id,
                count=len(cached_payload),
                duration_ms=timer.elapsed_ms,
            )
            return [RagChunkMatch(**item) for item in cached_payload]

        query_vec = (await self._embedder.embed_texts([query.strip() or "context"]))[0]

        vector_hits = await self._vector_store.search(
            filters.project_id,
            query_vec,
            filters=filters,
            limit=cap,
        )
        matches = self._hits_from_vector_rows(vector_hits)

        if not matches and self._config.python_fallback_enabled:
            log_rag_event(
                "retrieve_python_fallback",
                project_id=filters.project_id,
                user_id=filters.user_id,
                level="warning",
            )
            matches = await self._fallback_search(filters.project_id, query_vec, filters, cap)

        if filters.include_decisions:
            matches = await self._merge_decisions(filters.project_id, query, matches, cap)

        threshold = self._config.effective_score_threshold()
        matches = [m for m in matches if m.score >= threshold]
        matches = self._reranker.rerank(query, matches)[:cap]

        await set_cached_rag_retrieval(cache_key, matches)

        log_rag_event(
            "retrieve",
            project_id=filters.project_id,
            user_id=filters.user_id,
            count=len(matches),
            duration_ms=timer.elapsed_ms,
        )
        return matches

    async def build_context(
        self,
        query: str,
        *,
        filters: RagSearchFilters,
        limit: int | None = None,
    ) -> str:
        matches = await self.retrieve(query, filters=filters, limit=limit)
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
        documents = {d.id: d for d in await self._repo.list_documents(project_id, filters.task_id, limit=0)}
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
        return matches[:cap]

    async def _merge_decisions(
        self,
        project_id: str,
        query: str,
        matches: list[RagChunkMatch],
        cap: int,
    ) -> list[RagChunkMatch]:
        decisions = await self._repo.list_project_decisions(project_id)
        q_tokens = {t for t in re.findall(r"[a-z0-9]{3,}", query.lower())}
        extra: list[RagChunkMatch] = []
        for decision in decisions[:300]:
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
        merged = sorted([*matches, *extra], key=lambda item: item.score, reverse=True)
        return merged[:cap]


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
        texts = [chunk.content for chunk in rag_chunks]
        embeddings = await self._embedder.embed_texts(texts) if texts else []
        rows = [
            (
                chunk.chunk_index,
                chunk.content,
                PgVectorStoreRepository.estimate_tokens(chunk.content),
                embeddings[index],
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
