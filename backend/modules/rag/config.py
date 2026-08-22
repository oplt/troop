from __future__ import annotations

from dataclasses import dataclass

from backend.core.config import settings


@dataclass(frozen=True, slots=True)
class RagConfig:
    enabled: bool = True
    provider: str = "native"
    vector_store: str = "pgvector"
    embedding_provider: str = "local"
    embedding_model: str = ""
    chunk_size: int = 1200
    chunk_overlap: int = 150
    top_k: int = 5
    candidate_top_k: int = 30
    score_threshold: float = 0.2
    score_threshold_local: float = 0.05
    rerank_enabled: bool = False
    rerank_mode: str = "lexical"
    rerank_top_n: int = 15
    hybrid_search_enabled: bool = True
    rrf_k: int = 60
    max_chunks_per_document: int = 2
    max_chunks_per_source: int = 4
    dedup_similarity_threshold: float = 0.9
    max_context_tokens: int = 4000
    indexing_batch_size: int = 64
    log_content_in_dev: bool = False
    chunk_fallback_max: int = 200
    python_fallback_enabled: bool = False

    @classmethod
    def from_settings(cls) -> RagConfig:
        return cls(
            enabled=bool(getattr(settings, "RAG_ENABLED", True)),
            provider=str(getattr(settings, "RAG_PROVIDER", "native")),
            vector_store=str(getattr(settings, "RAG_VECTOR_STORE", "pgvector")),
            embedding_provider=str(
                getattr(settings, "RAG_EMBEDDING_PROVIDER", settings.AI_EMBEDDING_PROVIDER)
            ),
            embedding_model=str(
                getattr(settings, "RAG_EMBEDDING_MODEL", settings.OPENAI_EMBEDDING_MODEL)
            ),
            chunk_size=int(getattr(settings, "RAG_CHUNK_SIZE", 0))
            or settings.AI_DOCUMENT_CHUNK_SIZE,
            chunk_overlap=int(getattr(settings, "RAG_CHUNK_OVERLAP", 0))
            or settings.AI_DOCUMENT_CHUNK_OVERLAP,
            top_k=int(getattr(settings, "RAG_TOP_K", 5)),
            candidate_top_k=int(getattr(settings, "RAG_CANDIDATE_TOP_K", 30)),
            score_threshold=float(getattr(settings, "RAG_SCORE_THRESHOLD", 0.2)),
            score_threshold_local=float(getattr(settings, "RAG_SCORE_THRESHOLD_LOCAL", 0.05)),
            rerank_enabled=bool(getattr(settings, "RAG_RERANK_ENABLED", False)),
            rerank_mode=str(getattr(settings, "RAG_RERANK_MODE", "lexical")),
            rerank_top_n=int(getattr(settings, "RAG_RERANK_TOP_N", 15)),
            hybrid_search_enabled=bool(getattr(settings, "RAG_HYBRID_SEARCH_ENABLED", True)),
            rrf_k=int(getattr(settings, "RAG_RRF_K", 60)),
            max_chunks_per_document=int(getattr(settings, "RAG_MAX_CHUNKS_PER_DOCUMENT", 2)),
            max_chunks_per_source=int(getattr(settings, "RAG_MAX_CHUNKS_PER_SOURCE", 4)),
            dedup_similarity_threshold=float(
                getattr(settings, "RAG_DEDUP_SIMILARITY_THRESHOLD", 0.9)
            ),
            max_context_tokens=int(getattr(settings, "RAG_MAX_CONTEXT_TOKENS", 4000)),
            indexing_batch_size=int(getattr(settings, "RAG_INDEXING_BATCH_SIZE", 64)),
            log_content_in_dev=bool(getattr(settings, "RAG_LOG_CONTENT_IN_DEV", False)),
            chunk_fallback_max=int(getattr(settings, "RAG_CHUNK_FALLBACK_MAX", 200)),
            python_fallback_enabled=bool(settings.vector_python_fallback_enabled),
        )

    def effective_score_threshold(self) -> float:
        provider = (
            (
                self.embedding_provider
                or getattr(settings, "AI_EMBEDDING_PROVIDER", "local")
                or "local"
            )
            .strip()
            .lower()
        )
        if provider == "local":
            return self.score_threshold_local
        return self.score_threshold


def resolve_rag_config() -> RagConfig:
    return RagConfig.from_settings()
