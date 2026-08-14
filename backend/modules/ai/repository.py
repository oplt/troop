from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
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
from backend.modules.orchestration.model_utils import normalize_embedding_for_vector


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

    async def update_document(self, document: AiDocument, **values) -> AiDocument:
        for field, value in values.items():
            setattr(document, field, value)
        await self.db.flush()
        return document

    async def replace_document_chunks(
        self,
        document: AiDocument,
        chunks: list[tuple[int, str, int, list[float]]],
    ) -> None:
        await self.db.execute(
            delete(AiDocumentChunk).where(AiDocumentChunk.document_id == document.id)
        )
        await self.db.flush()
        for chunk_index, content, token_count, embedding in chunks:
            self.db.add(
                AiDocumentChunk(
                    document_id=document.id,
                    chunk_index=chunk_index,
                    content=content,
                    token_count=token_count,
                    embedding_json=embedding if settings.VECTOR_WRITE_EMBEDDING_JSON else [],
                    embedding_vector=normalize_embedding_for_vector(embedding),
                )
            )
        await self.db.flush()

    async def search_document_chunks_by_vector(
        self,
        user_id: str,
        document_ids: list[str],
        query_vec: list[float],
        *,
        top_k: int,
    ) -> list[dict]:
        if not document_ids:
            return []
        qv = normalize_embedding_for_vector(query_vec)
        literal = "[" + ",".join(str(float(x)) for x in qv) + "]"
        cap = max(1, min(int(top_k), 20))
        sql = text(
            """
            SELECT c.id AS chunk_id,
                   c.document_id,
                   c.chunk_index,
                   c.content,
                   d.title AS document_title,
                   1 - (c.embedding_vector <=> CAST(:qv AS vector)) AS score
            FROM ai_document_chunks c
            INNER JOIN ai_documents d ON d.id = c.document_id
            WHERE d.user_id = :uid
              AND c.document_id = ANY(:doc_ids)
              AND c.embedding_vector IS NOT NULL
            ORDER BY c.embedding_vector <=> CAST(:qv AS vector)
            LIMIT :lim
            """
        )
        result = await self.db.execute(
            sql,
            {"uid": user_id, "doc_ids": document_ids, "qv": literal, "lim": cap},
        )
        return [dict(row) for row in result.mappings().all()]

    async def list_document_chunks(
        self,
        document_ids: list[str],
        *,
        limit: int | None = None,
    ) -> list[AiDocumentChunk]:
        if not document_ids:
            return []
        cap = settings.AI_RETRIEVE_CHUNK_SCAN_MAX if limit is None else limit
        cap = min(max(int(cap), 1), settings.AI_RETRIEVE_CHUNK_SCAN_MAX)
        result = await self.db.execute(
            select(AiDocumentChunk)
            .where(AiDocumentChunk.document_id.in_(document_ids))
            .order_by(AiDocumentChunk.document_id.asc(), AiDocumentChunk.chunk_index.asc())
            .limit(cap)
        )
        return list(result.scalars().all())

    async def create_run(self, **kwargs) -> AiRun:
        run = AiRun(**kwargs)
        self.db.add(run)
        await self.db.flush()
        return run

    async def get_run_by_id(self, run_id: str) -> AiRun | None:
        result = await self.db.execute(select(AiRun).where(AiRun.id == run_id))
        return result.scalar_one_or_none()

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

    async def get_evaluation_run_for_user(
        self, user_id: str, evaluation_run_id: str
    ) -> AiEvaluationRun | None:
        result = await self.db.execute(
            select(AiEvaluationRun).where(
                AiEvaluationRun.id == evaluation_run_id,
                AiEvaluationRun.user_id == user_id,
            )
        )
        return result.scalar_one_or_none()

    async def list_evaluation_run_items(
        self, evaluation_run_id: str
    ) -> list[AiEvaluationRunItem]:
        result = await self.db.execute(
            select(AiEvaluationRunItem)
            .where(AiEvaluationRunItem.evaluation_run_id == evaluation_run_id)
            .order_by(AiEvaluationRunItem.id.asc())
        )
        return list(result.scalars().all())
