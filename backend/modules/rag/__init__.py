"""Retrieval-Augmented Generation layer (LangChain-inspired facade over project documents)."""

from backend.modules.rag.config import RagConfig, resolve_rag_config
from backend.modules.rag.schemas import RagAnswer, RagChunkMatch, RagDocument, RagSearchFilters
from backend.modules.rag.service import RagService

__all__ = [
    "RagAnswer",
    "RagChunkMatch",
    "RagConfig",
    "RagDocument",
    "RagSearchFilters",
    "RagService",
    "resolve_rag_config",
]
