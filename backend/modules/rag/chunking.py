from __future__ import annotations

import hashlib
from dataclasses import dataclass

from backend.modules.rag.config import RagConfig
from backend.modules.rag.schemas import RagChunk, SourceType


@dataclass(frozen=True, slots=True)
class ChunkingOptions:
    chunk_size: int = 1200
    chunk_overlap: int = 150


class ChunkingService:
    """Split documents into ordered, hash-addressable chunks."""

    def __init__(self, config: RagConfig | None = None):
        cfg = config or RagConfig.from_settings()
        self._default = ChunkingOptions(chunk_size=cfg.chunk_size, chunk_overlap=cfg.chunk_overlap)

    def split_text(self, text: str, *, options: ChunkingOptions | None = None) -> list[str]:
        opts = options or self._default
        normalized = (text or "").strip()
        if not normalized:
            return []
        chunks: list[str] = []
        start = 0
        while start < len(normalized):
            end = min(len(normalized), start + opts.chunk_size)
            chunk = normalized[start:end].strip()
            if chunk:
                chunks.append(chunk)
            if end >= len(normalized):
                break
            start = max(end - opts.chunk_overlap, start + 1)
        return chunks

    def build_chunks(
        self,
        *,
        document_id: str,
        source_id: str,
        source_type: SourceType,
        title: str,
        content: str,
        owner_user_id: str,
        project_id: str,
        workspace_id: str | None = None,
        metadata: dict | None = None,
        options: ChunkingOptions | None = None,
    ) -> list[RagChunk]:
        meta = dict(metadata or {})
        parts = self.split_text(content, options=options)
        out: list[RagChunk] = []
        for index, part in enumerate(parts):
            digest = hashlib.sha256(part.encode("utf-8")).hexdigest()
            out.append(
                RagChunk(
                    chunk_id=f"{document_id}:{index}:{digest[:12]}",
                    document_id=document_id,
                    source_id=source_id,
                    source_type=source_type,
                    title=title,
                    content=part,
                    chunk_index=index,
                    content_hash=digest,
                    owner_user_id=owner_user_id,
                    project_id=project_id,
                    workspace_id=workspace_id,
                    section=meta.get("section"),
                    page_number=meta.get("page_number"),
                    metadata={**meta, "content_hash": digest},
                )
            )
        return out
