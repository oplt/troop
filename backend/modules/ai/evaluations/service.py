"""Evaluation datasets and batch scoring runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.core.config import settings
from backend.modules.ai.evaluations.execution import execute_evaluation_cases
from backend.modules.ai.evaluations.metrics import aggregate_metrics
from backend.modules.ai.evaluations.scorecard import build_scorecard
from backend.modules.ai.evaluations.trace_case import (
    apply_correction,
    build_input_snapshot,
    build_input_variables,
    build_provenance,
)
from backend.modules.ai.models import AiEvaluationRun
from backend.modules.identity_access.models import User
from backend.modules.orchestration.execution.run_trace import RunTraceService
from backend.modules.orchestration.repository import OrchestrationRepository


class AiEvaluationsMixin:
    """Evaluation behavior. Requires ``self.db`` and ``self.repo``.

    Evaluation execution creates an isolated session per case and calls the
    composed run service through a fresh ``AiService`` instance.
    """

    async def list_datasets(self, user: User):
        return await self.repo.list_datasets_for_user(user.id)

    async def create_dataset(self, user: User, name: str, description: str | None):
        dataset = await self.repo.create_dataset(
            user_id=user.id, name=name, description=description
        )
        await self.db.commit()
        await self.db.refresh(dataset)
        return dataset

    async def update_dataset(self, user: User, dataset_id: str, updates: dict[str, Any]):
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        for field, value in updates.items():
            setattr(dataset, field, value)
        await self.db.commit()
        await self.db.refresh(dataset)
        return dataset

    async def list_dataset_cases(self, user: User, dataset_id: str):
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        return await self.repo.list_dataset_cases(dataset.id)

    async def create_dataset_case(self, user: User, dataset_id: str, payload: dict[str, Any]):
        from backend.modules.ai.evaluations.assertions import (
            derive_assertions_from_expected,
            normalize_assertions,
        )

        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        expected_assertions = normalize_assertions(payload.get("expected_assertions"))
        expected_output_json = payload.get("expected_output_json")
        if expected_assertions is None and expected_output_json is not None:
            expected_assertions = derive_assertions_from_expected(expected_output_json)
        case = await self.repo.create_dataset_case(
            dataset_id=dataset.id,
            input_variables_json=payload["input_variables"],
            expected_output_text=payload["expected_output_text"],
            expected_output_json=expected_output_json,
            expected_assertions_json=expected_assertions,
            notes=payload["notes"],
        )
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def create_case_from_trace(
        self,
        user: User,
        dataset_id: str,
        payload: dict[str, Any],
    ):
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")

        run_id = str(payload["run_id"])
        orch_repo = OrchestrationRepository(self.db)
        run = await orch_repo.get_run(user.id, run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Run not found")

        trace_service = RunTraceService(self.db)
        trace_page = await trace_service.list_run_trace_spans(run, limit=200)
        spans = list(trace_page.items)
        source_trace_span_id = payload.get("source_trace_span_id")
        if source_trace_span_id and not any(span.id == source_trace_span_id for span in spans):
            raise HTTPException(status_code=422, detail="Trace span not found on run")

        events = await orch_repo.list_run_events(run.id, limit=200)
        provenance = build_provenance(
            run,
            events=events,
            source_trace_span_id=source_trace_span_id,
        )
        snapshot = build_input_snapshot(
            run,
            spans=spans,
            source_trace_span_id=source_trace_span_id,
        )
        correction_payload = dict(payload.get("correction") or {})
        if payload.get("expected_assertions") is not None:
            correction_payload["expected_assertions"] = payload["expected_assertions"]
        if payload.get("notes") is not None:
            correction_payload.setdefault("notes", payload["notes"])
        resolved = apply_correction(correction_payload or None)

        case = await self.repo.create_dataset_case(
            dataset_id=dataset.id,
            input_variables_json=build_input_variables(snapshot),
            expected_output_text=resolved.get("expected_output_text"),
            expected_output_json=resolved.get("expected_output_json"),
            expected_assertions_json=resolved.get("expected_assertions_json"),
            notes=resolved.get("notes") or payload.get("notes"),
            source_run_id=run.id,
            source_trace_span_id=source_trace_span_id,
            provenance_json=provenance,
            input_snapshot_json=snapshot,
            correction_json=resolved.get("correction_json"),
        )
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def run_evaluation(
        self, user: User, dataset_id: str, payload: dict[str, Any]
    ) -> AiEvaluationRun:
        prompt_version_id = str(payload["prompt_version_id"])
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        version = await self.repo.get_prompt_version(prompt_version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        template = await self.repo.get_prompt_template_for_user(user.id, version.prompt_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")

        baseline_run = None
        baseline_run_id = payload.get("baseline_run_id")
        if baseline_run_id:
            baseline_run = await self.repo.get_evaluation_run_for_user(
                user.id, str(baseline_run_id)
            )
            if baseline_run is None:
                raise HTTPException(status_code=404, detail="Baseline evaluation run not found")
            if baseline_run.dataset_id != dataset.id:
                raise HTTPException(
                    status_code=422,
                    detail="Baseline evaluation run must belong to the same dataset",
                )

        candidate_config = {
            "prompt_version_id": version.id,
            "prompt_template_id": template.id,
            "prompt_template_key": template.key,
            "workflow_version_id": payload.get("workflow_version_id"),
            "model_name": payload.get("model_name") or version.model_name,
            "provider_key": version.provider_key,
        }
        qualitative_rubric = payload.get("qualitative_rubric")
        regression_threshold = float(payload.get("regression_threshold") or 0.05)

        cases = await self.repo.list_dataset_cases(dataset.id)
        evaluation_run = await self.repo.create_evaluation_run(
            dataset_id=dataset.id,
            prompt_version_id=version.id,
            user_id=user.id,
            status="running",
            total_cases=len(cases),
            passed_cases=0,
            average_score=0,
            baseline_run_id=baseline_run.id if baseline_run else None,
            candidate_config_json=candidate_config,
        )
        await self.db.commit()
        await self.db.refresh(evaluation_run)
        judge_mode = "model_judge" if qualitative_rubric else "deterministic"

        try:
            results = await execute_evaluation_cases(
                user=user,
                case_ids=[case.id for case in cases],
                evaluation_run_id=evaluation_run.id,
                dataset_id=dataset.id,
                template_key=template.key,
                prompt_version_id=version.id,
                response_format=version.response_format,
                model_name=payload.get("model_name"),
                qualitative_rubric=(
                    qualitative_rubric if isinstance(qualitative_rubric, dict) else None
                ),
                concurrency=settings.AI_EVAL_CONCURRENCY,
            )
        except Exception:
            evaluation_run.status = "failed"
            evaluation_run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise

        passed_cases = sum(1 for result in results if result.passed)
        scores = [result.score for result in results]
        item_metrics = [result.metrics for result in results]
        judge_version_id = next(
            (result.judge_version_id for result in results if result.judge_version_id),
            None,
        )

        aggregate = aggregate_metrics(item_metrics)
        baseline_metrics = dict(baseline_run.metrics_json or {}) if baseline_run else None
        scorecard = build_scorecard(
            candidate_config=candidate_config,
            metrics=aggregate,
            baseline_metrics=baseline_metrics,
            regression_threshold=regression_threshold,
            judge_version_id=judge_version_id,
            judge_mode=judge_mode,
        )

        evaluation_run.status = "completed"
        evaluation_run.passed_cases = passed_cases
        evaluation_run.average_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        evaluation_run.metrics_json = aggregate
        evaluation_run.scorecard_json = scorecard
        evaluation_run.judge_version_id = judge_version_id
        evaluation_run.completed_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(evaluation_run)
        return evaluation_run

    async def get_evaluation_run(self, user: User, evaluation_run_id: str) -> AiEvaluationRun:
        run = await self.repo.get_evaluation_run_for_user(user.id, evaluation_run_id)
        if run is None:
            raise HTTPException(status_code=404, detail="Evaluation run not found")
        return run

    async def get_evaluation_scorecard(self, user: User, evaluation_run_id: str) -> dict[str, Any]:
        run = await self.get_evaluation_run(user, evaluation_run_id)
        scorecard = dict(run.scorecard_json or {})
        if not scorecard:
            scorecard = build_scorecard(
                candidate_config=dict(run.candidate_config_json or {}),
                metrics=dict(run.metrics_json or {}),
                baseline_metrics=None,
                regression_threshold=0.05,
                judge_version_id=run.judge_version_id,
                judge_mode="deterministic",
            )
        return scorecard

    async def list_evaluation_runs(self, user: User, **page):
        return await self.repo.list_evaluation_runs_for_user(user.id, **page)
