from __future__ import annotations

from backend.modules.rag.schemas import RagChunkMatch, RagCitation


class SourceCitationService:
    def to_citations(
        self, matches: list[RagChunkMatch], *, excerpt_len: int = 240
    ) -> list[RagCitation]:
        out: list[RagCitation] = []
        for index, match in enumerate(matches, start=1):
            out.append(
                RagCitation(
                    source_index=index,
                    chunk_id=match.chunk_id,
                    document_id=match.document_id,
                    title=match.title,
                    chunk_index=match.chunk_index,
                    score=match.score,
                    excerpt=match.content[:excerpt_len],
                )
            )
        return out

    def format_inline_references(self, citations: list[RagCitation]) -> str:
        if not citations:
            return ""
        lines = ["Sources:"]
        for cite in citations:
            lines.append(
                f"[{cite.source_index}] {cite.title} (chunk {cite.chunk_index}, "
                f"doc {cite.document_id}, score={cite.score:.3f})"
            )
        return "\n".join(lines)
