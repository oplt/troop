#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from backend.modules.rag.evaluation import (
    RetrievalEvalCase,
    answer_is_grounded,
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
    for raw in cases:
        case = RetrievalEvalCase(
            query=str(raw["query"]),
            expected_chunk_ids=tuple(str(item) for item in raw.get("expected_chunk_ids") or ()),
            negative_chunk_ids=tuple(str(item) for item in raw.get("negative_chunk_ids") or ()),
            min_recall=float(raw.get("min_recall", 1.0)),
        )
        result = evaluate_retrieval_case(case, [_match(item) for item in raw.get("matches") or []])
        answer_payload = raw.get("answer")
        grounded_ok = True if answer_payload is None else answer_is_grounded(_answer(answer_payload))
        ok = result.passed and grounded_ok
        passed += 1 if ok else 0
        if not ok:
            failures.append(
                f"{case.query}: recall={result.recall:.3f} missing={list(result.missing_chunk_ids)} "
                f"unexpected={list(result.unexpected_chunk_ids)} grounded={grounded_ok}"
            )

    pass_rate = passed / len(cases)
    print(f"rag_eval_gate: passed={passed}/{len(cases)} pass_rate={pass_rate:.3f}")
    for failure in failures:
        print(f"FAIL {failure}")
    return 0 if pass_rate >= min_pass_rate and not failures else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="Fail CI on golden RAG retrieval/grounding regressions.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("--min-pass-rate", type=float, default=1.0)
    args = parser.parse_args()
    raise SystemExit(run_gate(args.dataset, min_pass_rate=args.min_pass_rate))


if __name__ == "__main__":
    main()
