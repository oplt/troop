#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.modules.rag.evaluation import (
    RetrievalEvalCase,
    evaluate_answer,
    evaluate_retrieval_case,
)
from backend.modules.rag.schemas import RagAnswer, RagChunkMatch, RagCitation


def _match(payload: dict[str, Any]) -> RagChunkMatch:
    return RagChunkMatch(
        chunk_id=str(payload["chunk_id"]),
        document_id=str(payload.get("document_id") or payload.get("project_document_id") or ""),
        title=str(payload.get("title") or payload.get("filename") or "document"),
        content=str(payload.get("content") or ""),
        chunk_index=int(payload.get("chunk_index") or 0),
        score=float(payload.get("score") or 0),
        hit_kind=str(payload.get("hit_kind") or "chunk"),
        metadata=dict(payload.get("metadata") or payload.get("metadata_json") or {}),
    )


def _answer(payload: dict[str, Any]) -> RagAnswer:
    return RagAnswer(
        query=str(payload.get("query") or ""),
        answer=str(payload.get("answer") or ""),
        grounded=bool(payload.get("grounded")),
        context_found=bool(payload.get("context_found")),
        citations=[
            RagCitation(
                source_index=int(item.get("source_index") or index + 1),
                chunk_id=str(item["chunk_id"]),
                document_id=str(item.get("document_id") or ""),
                title=str(item.get("title") or "document"),
                chunk_index=int(item.get("chunk_index") or 0),
                score=float(item.get("score") or 0),
                excerpt=str(item.get("excerpt") or ""),
            )
            for index, item in enumerate(payload.get("citations") or [])
        ],
        model=str(payload.get("model") or ""),
        provider=str(payload.get("provider") or ""),
    )


def run_gate(path: Path, *, min_pass_rate: float) -> int:
    data = json.loads(path.read_text(encoding="utf-8"))
    cases = data.get("cases") or []
    if not cases:
        print("rag_eval_gate: no cases found", file=sys.stderr)
        return 2

    passed = 0
    failures: list[str] = []
    category_counts: dict[str, int] = {}
    metric_totals = {
        "recall_at_k": 0.0,
        "mrr": 0.0,
        "ndcg": 0.0,
        "citation_precision": 0.0,
        "citation_coverage": 0.0,
        "answer_faithfulness": 0.0,
        "no_context_correctness": 0.0,
        "cross_project_leakage": 0.0,
        "acl_leakage": 0.0,
        "latency_ms": 0.0,
        "embedding_cost_usd": 0.0,
        "answer_cost_usd": 0.0,
    }
    for raw in cases:
        case = RetrievalEvalCase(
            query=str(raw["query"]),
            expected_chunk_ids=tuple(str(item) for item in raw.get("expected_chunk_ids") or ()),
            negative_chunk_ids=tuple(str(item) for item in raw.get("negative_chunk_ids") or ()),
            min_recall=float(raw.get("min_recall", 1.0)),
            category=str(raw.get("category") or "easy"),
            forbidden_project_ids=tuple(
                str(item) for item in raw.get("forbidden_project_ids") or ()
            ),
            acl_denied_chunk_ids=tuple(str(item) for item in raw.get("acl_denied_chunk_ids") or ()),
            expected_no_context=bool(raw.get("expected_no_context", False)),
        )
        result = evaluate_retrieval_case(case, [_match(item) for item in raw.get("matches") or []])
        answer_payload = raw.get("answer")
        answer_result = evaluate_answer(case, _answer(answer_payload) if answer_payload else None)
        grounded_ok = answer_result.faithful
        ok = result.passed and answer_result.passed
        passed += 1 if ok else 0
        category_counts[case.category] = category_counts.get(case.category, 0) + 1
        metric_totals["recall_at_k"] += result.recall
        metric_totals["mrr"] += result.reciprocal_rank
        metric_totals["ndcg"] += result.ndcg
        metric_totals["citation_precision"] += answer_result.citation_precision
        metric_totals["citation_coverage"] += answer_result.citation_coverage
        metric_totals["answer_faithfulness"] += float(answer_result.faithful)
        metric_totals["no_context_correctness"] += float(answer_result.no_context_correct)
        metric_totals["cross_project_leakage"] += float(result.cross_project_leakage)
        metric_totals["acl_leakage"] += float(result.acl_leakage)
        metric_totals["latency_ms"] += float(raw.get("latency_ms") or 0.0)
        metric_totals["embedding_cost_usd"] += float(raw.get("embedding_cost_usd") or 0.0)
        metric_totals["answer_cost_usd"] += float(raw.get("answer_cost_usd") or 0.0)
        if not ok:
            failures.append(
                f"{case.query}: recall={result.recall:.3f} missing={list(result.missing_chunk_ids)} "
                f"unexpected={list(result.unexpected_chunk_ids)} grounded={grounded_ok}"
            )

    pass_rate = passed / len(cases)
    print(f"rag_eval_gate: passed={passed}/{len(cases)} pass_rate={pass_rate:.3f}")
    averages = {
        key: round(value / len(cases), 6)
        for key, value in metric_totals.items()
        if key not in {"embedding_cost_usd", "answer_cost_usd"}
    }
    averages["embedding_cost_usd"] = round(metric_totals["embedding_cost_usd"], 6)
    averages["answer_cost_usd"] = round(metric_totals["answer_cost_usd"], 6)
    print(f"rag_eval_gate: categories={json.dumps(category_counts, sort_keys=True)}")
    print(f"rag_eval_gate: metrics={json.dumps(averages, sort_keys=True)}")
    required_categories = {
        "easy",
        "lexical",
        "semantic",
        "cross_scope",
        "security",
    }
    minimum_per_category = int(data.get("minimum_cases_per_category") or 0)
    if minimum_per_category:
        for category in sorted(required_categories):
            count = category_counts.get(category, 0)
            if count < minimum_per_category:
                failures.append(
                    f"category {category}: {count} cases; expected >= {minimum_per_category}"
                )
    for failure in failures:
        print(f"FAIL {failure}")
    return 0 if pass_rate >= min_pass_rate and not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Fail CI on golden RAG retrieval/grounding regressions."
    )
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(run_gate(args.dataset, min_pass_rate=args.min_pass_rate))


if __name__ == "__main__":
    main()
