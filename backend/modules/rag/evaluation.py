from __future__ import annotations

import re
from dataclasses import dataclass

from backend.modules.rag.schemas import RagAnswer, RagChunkMatch


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    query: str
    expected_chunk_ids: tuple[str, ...]
    negative_chunk_ids: tuple[str, ...] = ()
    min_recall: float = 1.0


@dataclass(frozen=True, slots=True)
class RetrievalEvalResult:
    query: str
    expected_chunk_ids: tuple[str, ...]
    returned_chunk_ids: tuple[str, ...]
    missing_chunk_ids: tuple[str, ...]
    unexpected_chunk_ids: tuple[str, ...]
    recall: float
    min_recall: float

    @property
    def passed(self) -> bool:
        return self.recall >= self.min_recall and not self.unexpected_chunk_ids


def evaluate_retrieval_case(
    case: RetrievalEvalCase, matches: list[RagChunkMatch]
) -> RetrievalEvalResult:
    returned = tuple(match.chunk_id for match in matches)
    returned_set = set(returned)
    expected_set = set(case.expected_chunk_ids)
    missing = tuple(
        chunk_id for chunk_id in case.expected_chunk_ids if chunk_id not in returned_set
    )
    unexpected = tuple(chunk_id for chunk_id in case.negative_chunk_ids if chunk_id in returned_set)
    recall = len(expected_set & returned_set) / max(len(expected_set), 1)
    return RetrievalEvalResult(
        query=case.query,
        expected_chunk_ids=case.expected_chunk_ids,
        returned_chunk_ids=returned,
        missing_chunk_ids=missing,
        unexpected_chunk_ids=unexpected,
        recall=recall,
        min_recall=case.min_recall,
    )


def answer_is_grounded(answer: RagAnswer) -> bool:
    if not answer.context_found or not answer.grounded or not answer.citations:
        return False
    cited_ids = {citation.chunk_id for citation in answer.citations}
    if not cited_ids:
        return False
    citation_markers = set(
        re.findall(r"\[(?:source|citation):([^\]]+)\]", answer.answer, flags=re.IGNORECASE)
    )
    return not citation_markers or citation_markers.issubset(cited_ids)
