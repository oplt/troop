"""Bounded evaluation case execution with one database session per case."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from typing import Any

from backend.modules.ai.evaluations.judge import run_qualitative_judge
from backend.modules.ai.evaluations.metrics import build_case_metrics
from backend.modules.ai.evaluations.scoring import score_evaluation_case
from backend.modules.identity_access.models import User


@dataclass(frozen=True, slots=True)
class EvaluationCaseResult:
    score: float
    passed: bool
    metrics: dict[str, Any]
    judge_version_id: str | None


async def execute_evaluation_cases(
    *,
    user: User,
    case_ids: list[str],
    evaluation_run_id: str,
    dataset_id: str,
    template_key: str,
    prompt_version_id: str,
    response_format: str,
    model_name: str | None,
    qualitative_rubric: dict[str, Any] | None,
    concurrency: int,
) -> list[EvaluationCaseResult]:
    """Run cases concurrently without ever sharing an AsyncSession."""
    from backend.db.session import SessionLocal
    from backend.modules.ai.service import AiService

    semaphore = asyncio.Semaphore(max(1, concurrency))

    async def run_case(case_id: str) -> EvaluationCaseResult:
        async with semaphore, SessionLocal() as session:
            service = AiService(session)
            case = await service.repo.get_dataset_case(case_id)
            if case is None:
                raise LookupError(f"Evaluation case {case_id} no longer exists")
            ai_run = await service.run_prompt(
                user,
                prompt_template_key=template_key,
                prompt_version_id=prompt_version_id,
                variables=dict(case.input_variables_json or {}),
                retrieval_query=None,
                document_ids=[],
                top_k=0,
                review_required=False,
                evaluation_dataset_id=dataset_id,
                evaluation_case_id=case.id,
                model_name=model_name,
            )
            score, passed, notes = score_evaluation_case(
                ai_run.output_text,
                ai_run.output_json,
                case,
            )
            qualitative_score, judge_notes, judge_version_id = run_qualitative_judge(
                output_text=ai_run.output_text,
                output_json=ai_run.output_json,
                rubric=qualitative_rubric,
            )
            if judge_notes:
                notes = f"{notes}; {judge_notes}" if notes else judge_notes
            metrics = build_case_metrics(
                case=case,
                ai_run=ai_run,
                passed=passed,
                response_format=response_format,
                qualitative_score=qualitative_score,
            )
            await service.repo.create_evaluation_run_item(
                evaluation_run_id=evaluation_run_id,
                evaluation_case_id=case.id,
                ai_run_id=ai_run.id,
                score=score,
                passed=passed,
                notes=notes,
                metrics_json=metrics,
            )
            await session.commit()
            return EvaluationCaseResult(
                score=score,
                passed=passed,
                metrics=metrics,
                judge_version_id=judge_version_id,
            )

    return await asyncio.gather(*(run_case(case_id) for case_id in case_ids))
