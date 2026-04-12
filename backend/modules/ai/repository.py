from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.ai.models import (
    AiDocument,
    AiDocumentChunk,
    AiEvaluationCase,
    AiEvaluationDataset,
    AiEvaluationRun,
    AiEvaluationRunItem,
    AiFeedback,
    AiPromptTemplate,
    AiPromptVersion,
    AiReviewItem,
    AiRun,
)


class AiRepository:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def list_prompt_templates_for_user(self, user_id: str) -> list[AiPromptTemplate]:
        result = await self.db.execute(
            select(AiPromptTemplate)
            .where(AiPromptTemplate.user_id == user_id)
            .order_by(AiPromptTemplate.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_prompt_template_for_user(
        self, user_id: str, template_id: str
    ) -> AiPromptTemplate | None:
        result = await self.db.execute(
            select(AiPromptTemplate).where(
                AiPromptTemplate.user_id == user_id,
                AiPromptTemplate.id == template_id,
            )
        )
        return result.scalar_one_or_none()

    async def get_prompt_template_by_key_for_user(
        self, user_id: str, key: str
    ) -> AiPromptTemplate | None:
        result = await self.db.execute(
            select(AiPromptTemplate).where(
                AiPromptTemplate.user_id == user_id,
                AiPromptTemplate.key == key,
            )
        )
        return result.scalar_one_or_none()

    async def create_prompt_template(self, **kwargs) -> AiPromptTemplate:
        template = AiPromptTemplate(**kwargs)
        self.db.add(template)
        await self.db.flush()
        return template

    async def list_prompt_versions(self, template_id: str) -> list[AiPromptVersion]:
        result = await self.db.execute(
            select(AiPromptVersion)
            .where(AiPromptVersion.prompt_template_id == template_id)
            .order_by(AiPromptVersion.version_number.desc())
        )
        return list(result.scalars().all())

    async def get_prompt_version(self, version_id: str) -> AiPromptVersion | None:
        result = await self.db.execute(
            select(AiPromptVersion).where(AiPromptVersion.id == version_id)
        )
        return result.scalar_one_or_none()

    async def create_prompt_version(self, **kwargs) -> AiPromptVersion:
        version = AiPromptVersion(**kwargs)
        self.db.add(version)
        await self.db.flush()
        return version

    async def list_documents_for_user(self, user_id: str) -> list[AiDocument]:
        result = await self.db.execute(
            select(AiDocument)
            .where(AiDocument.user_id == user_id)
            .order_by(AiDocument.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_document_for_user(self, user_id: str, document_id: str) -> AiDocument | None:
        result = await self.db.execute(
            select(AiDocument).where(
                AiDocument.user_id == user_id,
                AiDocument.id == document_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_document(self, **kwargs) -> AiDocument:
        document = AiDocument(**kwargs)
        self.db.add(document)
        await self.db.flush()
        return document

    async def replace_document_chunks(
        self,
        document: AiDocument,
        chunks: list[tuple[int, str, int, list[float]]],
    ) -> None:
        result = await self.db.execute(
            select(AiDocumentChunk).where(AiDocumentChunk.document_id == document.id)
        )
        for chunk in result.scalars().all():
            await self.db.delete(chunk)
        await self.db.flush()
        for chunk_index, content, token_count, embedding in chunks:
            self.db.add(
                AiDocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=token_count,
                    embedding_json=embedding,
                )
            )
        await self.db.flush()

    async def list_document_chunks(
        self,
        document_ids: list[str],
    ) -> list[AiDocumentChunk]:
        if not document_ids:
            return []
        result = await self.db.execute(
            select(AiDocumentChunk)
            .where(AiDocumentChunk.document_id.in_(document_ids))
            .order_by(AiDocumentChunk.document_id.asc(), AiDocumentChunk.chunk_index.asc())
        )
        return list(result.scalars().all())

    async def create_run(self, **kwargs) -> AiRun:
        run = AiRun(**kwargs)
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_run_for_user(self, user_id: str, run_id: str) -> AiRun | None:
        result = await self.db.execute(
            select(AiRun).where(AiRun.user_id == user_id, AiRun.id == run_id)
        )
        return result.scalar_one_or_none()

    async def list_runs_for_user(self, user_id: str, limit: int = 50) -> list[AiRun]:
        result = await self.db.execute(
            select(AiRun)
            .where(AiRun.user_id == user_id)
            .order_by(AiRun.created_at.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def list_reviews_for_user(self, user_id: str) -> list[AiReviewItem]:
        result = await self.db.execute(
            select(AiReviewItem)
            .where(
                (AiReviewItem.requested_by_user_id == user_id)
                | (AiReviewItem.assigned_to_user_id == user_id)
                | (AiReviewItem.reviewed_by_user_id == user_id)
            )
            .order_by(AiReviewItem.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_review(self, review_id: str) -> AiReviewItem | None:
        result = await self.db.execute(select(AiReviewItem).where(AiReviewItem.id == review_id))
        return result.scalar_one_or_none()

    async def create_review(self, **kwargs) -> AiReviewItem:
        review = AiReviewItem(**kwargs)
        self.db.add(review)
        await self.db.flush()
        return review

    async def list_feedback_for_run(self, run_id: str) -> list[AiFeedback]:
        result = await self.db.execute(
            select(AiFeedback)
            .where(AiFeedback.run_id == run_id)
            .order_by(AiFeedback.created_at.desc())
        )
        return list(result.scalars().all())

    async def create_feedback(self, **kwargs) -> AiFeedback:
        feedback = AiFeedback(**kwargs)
        self.db.add(feedback)
        await self.db.flush()
        return feedback

    async def list_datasets_for_user(self, user_id: str) -> list[AiEvaluationDataset]:
        result = await self.db.execute(
            select(AiEvaluationDataset)
            .where(AiEvaluationDataset.user_id == user_id)
            .order_by(AiEvaluationDataset.updated_at.desc())
        )
        return list(result.scalars().all())

    async def get_dataset_for_user(
        self, user_id: str, dataset_id: str
    ) -> AiEvaluationDataset | None:
        result = await self.db.execute(
            select(AiEvaluationDataset).where(
                AiEvaluationDataset.user_id == user_id,
                AiEvaluationDataset.id == dataset_id,
            )
        )
        return result.scalar_one_or_none()

    async def create_dataset(self, **kwargs) -> AiEvaluationDataset:
        dataset = AiEvaluationDataset(**kwargs)
        self.db.add(dataset)
        await self.db.flush()
        return dataset

    async def list_dataset_cases(self, dataset_id: str) -> list[AiEvaluationCase]:
        result = await self.db.execute(
            select(AiEvaluationCase)
            .where(AiEvaluationCase.dataset_id == dataset_id)
            .order_by(AiEvaluationCase.created_at.asc())
        )
        return list(result.scalars().all())

    async def get_dataset_case(self, case_id: str) -> AiEvaluationCase | None:
        result = await self.db.execute(
            select(AiEvaluationCase).where(AiEvaluationCase.id == case_id)
        )
        return result.scalar_one_or_none()

    async def create_dataset_case(self, **kwargs) -> AiEvaluationCase:
        case = AiEvaluationCase(**kwargs)
        self.db.add(case)
        await self.db.flush()
        return case

    async def create_evaluation_run(self, **kwargs) -> AiEvaluationRun:
        evaluation_run = AiEvaluationRun(**kwargs)
        self.db.add(evaluation_run)
        await self.db.flush()
        return evaluation_run

    async def create_evaluation_run_item(self, **kwargs) -> AiEvaluationRunItem:
        item = AiEvaluationRunItem(**kwargs)
        self.db.add(item)
        await self.db.flush()
        return item

    async def list_evaluation_runs_for_user(self, user_id: str) -> list[AiEvaluationRun]:
        result = await self.db.execute(
            select(AiEvaluationRun)
            .where(AiEvaluationRun.user_id == user_id)
            .order_by(AiEvaluationRun.created_at.desc())
        )
        return list(result.scalars().all())
