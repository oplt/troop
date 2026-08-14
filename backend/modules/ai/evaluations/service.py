"""Evaluation datasets and batch scoring runs."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException

from backend.modules.ai.evaluations.scoring import score_evaluation_case
from backend.modules.ai.models import AiEvaluationRun
from backend.modules.identity_access.models import User


class AiEvaluationsMixin:
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
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        case = await self.repo.create_dataset_case(
            dataset_id=dataset.id,
            input_variables_json=payload["input_variables"],
            expected_output_text=payload["expected_output_text"],
            expected_output_json=payload["expected_output_json"],
            notes=payload["notes"],
        )
        await self.db.commit()
        await self.db.refresh(case)
        return case

    async def run_evaluation(
        self, user: User, dataset_id: str, prompt_version_id: str
    ) -> AiEvaluationRun:
        dataset = await self.repo.get_dataset_for_user(user.id, dataset_id)
        if not dataset:
            raise HTTPException(status_code=404, detail="Evaluation dataset not found")
        version = await self.repo.get_prompt_version(prompt_version_id)
        if not version:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        template = await self.repo.get_prompt_template_for_user(user.id, version.prompt_template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        cases = await self.repo.list_dataset_cases(dataset.id)
        evaluation_run = await self.repo.create_evaluation_run(
            dataset_id=dataset.id,
            prompt_version_id=version.id,
            user_id=user.id,
            status="running",
            total_cases=len(cases),
            passed_cases=0,
            average_score=0,
        )
        passed_cases = 0
        scores: list[float] = []
        for case in cases:
            ai_run = await self.run_prompt(
                user,
                prompt_template_key=template.key,
                prompt_version_id=version.id,
                variables=case.input_variables_json,
                retrieval_query=None,
                document_ids=[],
                top_k=0,
                review_required=False,
                evaluation_dataset_id=dataset.id,
                evaluation_case_id=case.id,
            )
            score, passed, notes = score_evaluation_case(
                ai_run.output_text, ai_run.output_json, case
            )
            scores.append(score)
            if passed:
                passed_cases += 1
            await self.repo.create_evaluation_run_item(
                evaluation_run_id=evaluation_run.id,
                evaluation_case_id=case.id,
                ai_run_id=ai_run.id,
                score=score,
                passed=passed,
                notes=notes,
            )
        evaluation_run.status = "completed"
        evaluation_run.passed_cases = passed_cases
        evaluation_run.average_score = round(sum(scores) / len(scores), 4) if scores else 0.0
        evaluation_run.completed_at = datetime.now(UTC)
        await self.db.commit()
        await self.db.refresh(evaluation_run)
        return evaluation_run
    async def list_evaluation_runs(self, user: User):
        return await self.repo.list_evaluation_runs_for_user(user.id)
