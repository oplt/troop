from __future__ import annotations

import re
from dataclasses import dataclass
from math import log2

from backend.modules.rag.schemas import RagAnswer, RagChunkMatch


@dataclass(frozen=True, slots=True)
class RetrievalEvalCase:
    query: str
    expected_chunk_ids: tuple[str, ...]
    negative_chunk_ids: tuple[str, ...] = ()
    min_recall: float = 1.0
    category: str = "easy"
    forbidden_project_ids: tuple[str, ...] = ()
    acl_denied_chunk_ids: tuple[str, ...] = ()
    expected_no_context: bool = False


@dataclass(frozen=True, slots=True)
class RetrievalEvalResult:
    query: str
    expected_chunk_ids: tuple[str, ...]
    returned_chunk_ids: tuple[str, ...]
    missing_chunk_ids: tuple[str, ...]
    unexpected_chunk_ids: tuple[str, ...]
    recall: float
    reciprocal_rank: float
    ndcg: float
    cross_project_leakage: bool
    acl_leakage: bool
    min_recall: float

    @property
    def passed(self) -> bool:
        return (
            self.recall >= self.min_recall
            and not self.unexpected_chunk_ids
            and not self.cross_project_leakage
            and not self.acl_leakage
        )


@dataclass(frozen=True, slots=True)
class AnswerEvalResult:
    citation_precision: float
    citation_coverage: float
    faithful: bool
    no_context_correct: bool

    @property
    def passed(self) -> bool:
        return self.faithful and self.no_context_correct


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
    recall = (
        1.0
        if not expected_set and not returned_set
        else len(expected_set & returned_set) / max(len(expected_set), 1)
    )
    first_relevant_rank = next(
        (rank for rank, chunk_id in enumerate(returned, start=1) if chunk_id in expected_set),
        None,
    )
    reciprocal_rank = (
        1.0
        if not expected_set and not returned_set
        else (0.0 if first_relevant_rank is None else 1.0 / first_relevant_rank)
    )
    dcg = sum(
        1.0 / log2(rank + 1)
        for rank, chunk_id in enumerate(returned, start=1)
        if chunk_id in expected_set
    )
    ideal_count = min(len(expected_set), len(returned))
    ideal_dcg = sum(1.0 / log2(rank + 1) for rank in range(1, ideal_count + 1))
    forbidden_projects = set(case.forbidden_project_ids)
    cross_project_leakage = any(
        str(match.metadata.get("project_id") or "") in forbidden_projects for match in matches
    )
    acl_leakage = bool(set(case.acl_denied_chunk_ids) & returned_set)
    return RetrievalEvalResult(
        query=case.query,
        expected_chunk_ids=case.expected_chunk_ids,
        returned_chunk_ids=returned,
        missing_chunk_ids=missing,
        unexpected_chunk_ids=unexpected,
        recall=recall,
        reciprocal_rank=reciprocal_rank,
        ndcg=dcg / ideal_dcg if ideal_dcg else 1.0,
        cross_project_leakage=cross_project_leakage,
        acl_leakage=acl_leakage,
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


def evaluate_answer(case: RetrievalEvalCase, answer: RagAnswer | None) -> AnswerEvalResult:
    if answer is None:
        return AnswerEvalResult(1.0, 1.0, True, not case.expected_no_context)
    cited_ids = {citation.chunk_id for citation in answer.citations}
    expected_ids = set(case.expected_chunk_ids)
    if case.expected_no_context and not cited_ids:
        citation_precision = 1.0
        citation_coverage = 1.0
    else:
        citation_precision = len(cited_ids & expected_ids) / max(len(cited_ids), 1)
        citation_coverage = len(cited_ids & expected_ids) / max(len(expected_ids), 1)
    no_context_correct = (
        not answer.context_found and not answer.citations
        if case.expected_no_context
        else answer.context_found
    )
    faithful = (
        no_context_correct
        if case.expected_no_context
        else answer_is_grounded(answer) and citation_precision == 1.0
    )
    return AnswerEvalResult(
        citation_precision=citation_precision,
        citation_coverage=citation_coverage,
        faithful=faithful,
        no_context_correct=no_context_correct,
    )
