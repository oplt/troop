from __future__ import annotations

from backend.modules.rag.schemas import RagChunkMatch

_GROUNDED_SYSTEM = """You are a helpful assistant that answers questions using ONLY
the retrieved context.
Rules:
- Answer based on the retrieved context below.
- Do not invent facts not supported by the context.
- Cite sources using [Source N] notation when possible.
- If the context is insufficient, say you do not have enough information."""


class RagPromptBuilder:
    def build_context_block(self, matches: list[RagChunkMatch]) -> str:
        if not matches:
            return ""
        lines = ["Relevant retrieved context:"]
        for index, match in enumerate(matches, start=1):
            lines.extend(
                [
                    f"[Source {index}]",
                    f"Title: {match.title}",
                    f"Document ID: {match.document_id}",
                    f"Chunk ID: {match.chunk_id}",
                    f"Content: {match.content.strip()}",
                    "",
                ]
            )
        return "\n".join(lines).strip()

    def build_answer_prompt(self, query: str, matches: list[RagChunkMatch]) -> tuple[str, str]:
        context = self.build_context_block(matches)
        user_prompt = (
            f"{context}\n\n"
            f"User question:\n{query.strip()}\n\n"
            "Answer using only the retrieved context. Cite sources as [Source N]. "
            "If the context does not contain enough information, say so explicitly."
        )
        return _GROUNDED_SYSTEM, user_prompt

    def no_context_answer(self) -> str:
        return (
            "I do not have enough information in the indexed project knowledge "
            "to answer that question."
        )
