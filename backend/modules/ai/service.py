from __future__ import annotations

import json
import math
import re
from datetime import UTC, datetime
from time import perf_counter
from typing import Any

from fastapi import HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.ai.models import (
    AiEvaluationRun,
    AiPromptTemplate,
    AiPromptVersion,
)
from backend.modules.ai.providers import AiProviderRegistry, ProviderGenerateRequest
from backend.modules.ai.repository import AiRepository
from backend.modules.ai.schemas import AiProviderDescriptor
from backend.modules.identity_access.models import User

PLACEHOLDER_PATTERN = re.compile(r"{{\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*}}")


def _estimate_tokens(text: str) -> int:
    return max(1, math.ceil(len(text) / 4))


def _render_template(template: str, variables: dict[str, Any]) -> str:
    def replace(match: re.Match[str]) -> str:
        key = match.group(1)
        value = variables.get(key)
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, ensure_ascii=True)
        return str(value)

    return PLACEHOLDER_PATTERN.sub(replace, template)


def _chunk_text(text: str, chunk_size: int = 1200, overlap: int = 150) -> list[str]:
    normalized = text.strip()
    if not normalized:
        return []
    chunks: list[str] = []
    start = 0
    while start < len(normalized):
        end = min(len(normalized), start + chunk_size)
        chunk = normalized[start:end].strip()
        if chunk:
            chunks.append(chunk)
        if end >= len(normalized):
            break
        start = max(end - overlap, start + 1)
    return chunks


def _cosine_similarity(left: list[float], right: list[float]) -> float:
    if not left or not right or len(left) != len(right):
        return 0.0
    numerator = sum(a * b for a, b in zip(left, right, strict=True))
    left_norm = math.sqrt(sum(a * a for a in left))
    right_norm = math.sqrt(sum(b * b for b in right))
    if left_norm == 0 or right_norm == 0:
        return 0.0
    return numerator / (left_norm * right_norm)


class AiService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AiRepository(db)
        self.providers = AiProviderRegistry()

    @staticmethod
    def list_provider_descriptors() -> list[AiProviderDescriptor]:
        return [
            AiProviderDescriptor(
                key="local",
                label="Local heuristic",
                supports_generation=True,
                supports_embeddings=True,
            ),
            AiProviderDescriptor(
                key="openai",
                label="OpenAI",
                supports_generation=True,
                supports_embeddings=True,
            ),
            AiProviderDescriptor(
                key="anthropic",
                label="Anthropic",
                supports_generation=True,
                supports_embeddings=settings.AI_EMBEDDING_PROVIDER == "anthropic",
            ),
        ]

    async def list_prompt_templates(self, user: User):
        return await self.repo.list_prompt_templates_for_user(user.id)

    async def create_prompt_template(
        self, user: User, key: str, name: str, description: str | None
    ):
        existing = await self.repo.get_prompt_template_by_key_for_user(user.id, key)
        if existing:
            raise HTTPException(
                status_code=409,
                detail="A prompt template with this key already exists",
            )
        template = await self.repo.create_prompt_template(
            user_id=user.id,
            key=key,
            name=name,
            description=description,
        )
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def update_prompt_template(
        self, user: User, template_id: str, updates: dict[str, Any]
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        if "active_version_id" in updates and updates["active_version_id"]:
            version = await self.repo.get_prompt_version(updates["active_version_id"])
            if not version or version.prompt_template_id != template.id:
                raise HTTPException(
                    status_code=404,
                    detail="Prompt version not found for this template",
                )
            if not version.is_published:
                raise HTTPException(
                    status_code=422,
                    detail="Only published versions can be activated",
                )
        for field, value in updates.items():
            setattr(template, field, value)
        await self.db.commit()
        await self.db.refresh(template)
        return template

    async def create_prompt_version(self, user: User, template_id: str, payload: dict[str, Any]):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        versions = await self.repo.list_prompt_versions(template.id)
        next_version_number = (versions[0].version_number + 1) if versions else 1
        version = await self.repo.create_prompt_version(
            prompt_template_id=template.id,
            version_number=next_version_number,
            provider_key=payload["provider_key"],
            model_name=payload["model_name"],
            system_prompt=payload["system_prompt"],
            user_prompt_template=payload["user_prompt_template"],
            variable_definitions_json=[
                item.model_dump() for item in payload["variable_definitions"]
            ],
            response_format=payload["response_format"],
            temperature=payload["temperature"],
            rollout_percentage=payload["rollout_percentage"],
            is_published=payload["is_published"],
            input_cost_per_million=payload["input_cost_per_million"],
            output_cost_per_million=payload["output_cost_per_million"],
            created_by_user_id=user.id,
        )
        if template.active_version_id is None and version.is_published:
            template.active_version_id = version.id
        await self.db.commit()
        await self.db.refresh(version)
        await self.db.refresh(template)
        return version

    async def update_prompt_version(
        self, user: User, template_id: str, version_id: str, updates: dict[str, Any]
    ):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        version = await self.repo.get_prompt_version(version_id)
        if not version or version.prompt_template_id != template.id:
            raise HTTPException(status_code=404, detail="Prompt version not found")
        for field, value in updates.items():
            if field == "variable_definitions":
                version.variable_definitions_json = [item.model_dump() for item in value]
            else:
                setattr(version, field, value)
        await self.db.commit()
        await self.db.refresh(version)
        return version

    async def list_prompt_versions(self, user: User, template_id: str):
        template = await self.repo.get_prompt_template_for_user(user.id, template_id)
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        return await self.repo.list_prompt_versions(template.id)

    async def list_documents(self, user: User):
        return await self.repo.list_documents_for_user(user.id)

    async def create_document_from_text(
        self,
        user: User,
        *,
        title: str,
        description: str | None,
        content: str,
        content_type: str,
        filename: str | None = None,
        metadata: dict[str, Any] | None = None,
    ):
        if not content.strip():
            raise HTTPException(status_code=422, detail="Document content must not be empty")
        if len(content.encode("utf-8")) > settings.AI_DOCUMENT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Document exceeds the maximum size of"
                    f" {settings.AI_DOCUMENT_MAX_BYTES} bytes"
                ),
            )
        chunks = _chunk_text(
            content, settings.AI_DOCUMENT_CHUNK_SIZE, settings.AI_DOCUMENT_CHUNK_OVERLAP
        )
        embeddings = await self.providers.embed_texts(chunks) if chunks else []
        document = await self.repo.create_document(
            user_id=user.id,
            title=title,
            description=description,
            filename=filename,
            content_type=content_type,
            size_bytes=len(content.encode("utf-8")),
            ingestion_status="completed",
            source_text=content,
            metadata_json=metadata or {},
            chunk_count=len(chunks),
        )
        await self.repo.replace_document_chunks(
            document,
            [
                (index, chunk, _estimate_tokens(chunk), embeddings[index])
                for index, chunk in enumerate(chunks)
            ],
        )
        await self.db.commit()
        await self.db.refresh(document)
        return document

    async def create_document_from_upload(
        self, user: User, file: UploadFile, description: str | None
    ):
        content_type = file.content_type or "text/plain"
        if not (
            content_type.startswith("text/")
            or content_type in {"application/json", "application/x-ndjson", "text/markdown"}
        ):
            raise HTTPException(
                status_code=400,
                detail="Document ingestion currently supports text, markdown, and json files only",
            )
        payload = await file.read()
        if not payload:
            raise HTTPException(status_code=400, detail="Uploaded document file is empty")
        if len(payload) > settings.AI_DOCUMENT_MAX_BYTES:
            raise HTTPException(
                status_code=413,
                detail=(
                    f"Document exceeds the maximum size of"
                    f" {settings.AI_DOCUMENT_MAX_BYTES} bytes"
                ),
            )
        try:
            content = payload.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise HTTPException(
                status_code=400, detail="Uploaded document must be valid UTF-8 text"
            ) from exc
        title = file.filename or "Untitled document"
        return await self.create_document_from_text(
            user,
            title=title,
            description=description,
            content=content,
            content_type=content_type,
            filename=file.filename,
        )

    async def retrieve_chunks(
        self,
        user: User,
        *,
        query: str,
        document_ids: list[str],
        top_k: int,
    ) -> list[dict[str, Any]]:
        allowed_docs = await self.repo.list_documents_for_user(user.id)
        allowed_doc_map = {document.id: document for document in allowed_docs}
        candidate_ids = document_ids or list(allowed_doc_map)
        invalid_ids = [
            document_id for document_id in candidate_ids if document_id not in allowed_doc_map
        ]
        if invalid_ids:
            raise HTTPException(status_code=404, detail="One or more documents were not found")
        chunks = await self.repo.list_document_chunks(candidate_ids)
        if not chunks:
            return []
        query_embedding = (await self.providers.embed_texts([query]))[0]
        matches = []
        for chunk in chunks:
            score = _cosine_similarity(query_embedding, chunk.embedding_json)
            document = allowed_doc_map[chunk.document_id]
            matches.append(
                {
                    "document_id": chunk.document_id,
                    "chunk_id": chunk.id,
                    "document_title": document.title,
                    "chunk_index": chunk.chunk_index,
                    "score": round(score, 4),
                    "content": chunk.content,
                }
            )
        matches.sort(key=lambda item: item["score"], reverse=True)
        return matches[:top_k]

    async def _resolve_prompt_version(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
    ) -> tuple[AiPromptTemplate | None, AiPromptVersion]:
        if prompt_version_id:
            version = await self.repo.get_prompt_version(prompt_version_id)
            if not version:
                raise HTTPException(status_code=404, detail="Prompt version not found")
            template = await self.repo.get_prompt_template_for_user(
                user.id, version.prompt_template_id
            )
            if not template:
                raise HTTPException(status_code=404, detail="Prompt template not found")
            return template, version
        if not prompt_template_key:
            raise HTTPException(
                status_code=422,
                detail="prompt_template_key or prompt_version_id is required",
            )
        template = await self.repo.get_prompt_template_by_key_for_user(
            user.id, prompt_template_key
        )
        if not template:
            raise HTTPException(status_code=404, detail="Prompt template not found")
        versions = await self.repo.list_prompt_versions(template.id)
        version = None
        if template.active_version_id:
            version = next(
                (item for item in versions if item.id == template.active_version_id), None
            )
        if version is None:
            version = next((item for item in versions if item.is_published), None)
        if version is None and versions:
            version = versions[0]
        if version is None:
            raise HTTPException(status_code=422, detail="This prompt template has no versions yet")
        return template, version

    async def run_prompt(
        self,
        user: User,
        *,
        prompt_template_key: str | None,
        prompt_version_id: str | None,
        variables: dict[str, Any],
        retrieval_query: str | None,
        document_ids: list[str],
        top_k: int,
        review_required: bool,
        evaluation_dataset_id: str | None = None,
        evaluation_case_id: str | None = None,
    ):
        template, version = await self._resolve_prompt_version(
            user,
            prompt_template_key=prompt_template_key,
            prompt_version_id=prompt_version_id,
        )
        provider = self.providers.get(version.provider_key)
        matches: list[dict[str, Any]] = []
        if retrieval_query:
            matches = await self.retrieve_chunks(
                user,
                query=retrieval_query,
                document_ids=document_ids,
                top_k=top_k,
            )
            variables = {
                **variables,
                "retrieval_context": "\n\n".join(
                    f"[{item['document_title']} #{item['chunk_index']}]\n{item['content']}"
                    for item in matches
                ),
            }

        rendered_system_prompt = _render_template(version.system_prompt, variables)
        rendered_user_prompt = _render_template(version.user_prompt_template, variables)
        run = await self.repo.create_run(
            user_id=user.id,
            prompt_template_id=template.id if template else None,
            prompt_version_id=version.id,
            evaluation_dataset_id=evaluation_dataset_id,
            evaluation_case_id=evaluation_case_id,
            provider_key=version.provider_key,
            model_name=version.model_name,
            status="running",
            response_format=version.response_format,
            variables_json=variables,
            retrieval_query=retrieval_query,
            retrieved_chunk_ids_json=[item["chunk_id"] for item in matches],
            input_messages_json=[
                {"role": "system", "content": rendered_system_prompt},
                {"role": "user", "content": rendered_user_prompt},
            ],
            review_status="pending" if review_required else "not_requested",
        )
        await self.db.flush()

        started = perf_counter()
        try:
            result = await provider.generate(
                ProviderGenerateRequest(
                    model=version.model_name,
                    system_prompt=rendered_system_prompt,
                    user_prompt=rendered_user_prompt,
                    response_format=version.response_format,
                    temperature=version.temperature,
                )
            )
            latency_ms = int((perf_counter() - started) * 1000)
            run.status = "completed"
            run.output_text = result.output_text
            run.output_json = result.output_json
            run.latency_ms = latency_ms
            run.input_tokens = result.input_tokens
            run.output_tokens = result.output_tokens
            run.total_tokens = result.total_tokens
            run.estimated_cost_micros = (
                (result.input_tokens * version.input_cost_per_million)
                + (result.output_tokens * version.output_cost_per_million)
            )
            run.completed_at = datetime.now(UTC)
        except HTTPException as exc:
            run.status = "failed"
            run.error_message = exc.detail if isinstance(exc.detail, str) else str(exc.detail)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise
        except Exception as exc:
            run.status = "failed"
            run.error_message = str(exc)
            run.completed_at = datetime.now(UTC)
            await self.db.commit()
            raise HTTPException(status_code=502, detail="AI provider execution failed") from exc

        if review_required:
            await self.repo.create_review(
                run_id=run.id,
                requested_by_user_id=user.id,
                status="pending",
            )

        await self.db.commit()
        await self.db.refresh(run)
        return run

    async def list_runs(self, user: User):
        return await self.repo.list_runs_for_user(user.id)

    async def create_review(self, user: User, run_id: str, assigned_to_user_id: str | None):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        review = await self.repo.create_review(
            run_id=run.id,
            requested_by_user_id=user.id,
            assigned_to_user_id=assigned_to_user_id,
            status="pending",
        )
        run.review_status = "pending"
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def list_reviews(self, user: User):
        return await self.repo.list_reviews_for_user(user.id)

    async def decide_review(self, user: User, review_id: str, payload: dict[str, Any]):
        review = await self.repo.get_review(review_id)
        if not review:
            raise HTTPException(status_code=404, detail="Review item not found")
        if not user.is_admin and user.id not in {
            review.requested_by_user_id,
            review.assigned_to_user_id,
        }:
            raise HTTPException(status_code=403, detail="You are not allowed to decide this review")
        run = await self.repo.get_run_for_user(review.requested_by_user_id, review.run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        review.status = payload["status"]
        review.reviewed_by_user_id = user.id
        review.reviewer_notes = payload.get("reviewer_notes")
        review.corrected_output = payload.get("corrected_output")
        run.review_status = payload["status"]
        if payload.get("corrected_output"):
            run.output_text = payload["corrected_output"]
        await self.db.commit()
        await self.db.refresh(review)
        return review

    async def add_feedback(
        self, user: User, run_id: str, rating: int,
        comment: str | None, corrected_output: str | None,
    ):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        feedback = await self.repo.create_feedback(
            run_id=run.id,
            user_id=user.id,
            rating=rating,
            comment=comment,
            corrected_output=corrected_output,
        )
        await self.db.commit()
        await self.db.refresh(feedback)
        return feedback

    async def list_feedback(self, user: User, run_id: str):
        run = await self.repo.get_run_for_user(user.id, run_id)
        if not run:
            raise HTTPException(status_code=404, detail="AI run not found")
        return await self.repo.list_feedback_for_run(run.id)

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
            score, passed, notes = self._score_evaluation_case(
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

    def _score_evaluation_case(
        self, output_text: str | None, output_json: dict | None, case
    ) -> tuple[float, bool, str]:
        if case.expected_output_json is not None:
            passed = output_json == case.expected_output_json
            return (1.0 if passed else 0.0, passed, "JSON exact match")
        expected_text = (case.expected_output_text or "").strip()
        actual_text = (output_text or "").strip()
        if expected_text:
            passed = expected_text.lower() == actual_text.lower()
            if passed:
                return 1.0, True, "Exact text match"
            partial = 1.0 if expected_text.lower() in actual_text.lower() else 0.0
            return partial, partial >= 1.0, "Substring text comparison"
        return 0.0, False, "No expected output defined"

    async def list_evaluation_runs(self, user: User):
        return await self.repo.list_evaluation_runs_for_user(user.id)

    async def get_overview(self, user: User):
        prompt_templates = await self.repo.list_prompt_templates_for_user(user.id)
        recent_runs = await self.repo.list_runs_for_user(user.id, limit=10)
        documents = await self.repo.list_documents_for_user(user.id)
        datasets = await self.repo.list_datasets_for_user(user.id)
        return {
            "providers": self.list_provider_descriptors(),
            "prompt_templates": prompt_templates,
            "recent_runs": recent_runs,
            "documents": documents,
            "datasets": datasets,
        }
