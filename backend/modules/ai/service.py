from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.modules.ai.documents.service import AiDocumentsMixin
from backend.modules.ai.evaluations.service import AiEvaluationsMixin
from backend.modules.ai.prompts.renderer import render_template
from backend.modules.ai.prompts.service import PromptService
from backend.modules.ai.providers import AiProviderRegistry
from backend.modules.ai.repository import AiRepository
from backend.modules.ai.retrieval.service import AiRetrievalMixin
from backend.modules.ai.reviews.service import AiReviewsMixin
from backend.modules.ai.runs.service import AiRunsMixin
from backend.modules.ai.schemas import AiProviderDescriptor
from backend.modules.identity_access.models import User

# Backward-compatible alias used by tests patching backend.modules.ai.service.settings
__all__ = ["AiService", "render_template", "settings"]


class AiService(
    AiDocumentsMixin,
    AiRetrievalMixin,
    AiRunsMixin,
    AiReviewsMixin,
    AiEvaluationsMixin,
):
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = AiRepository(db)
        self.providers = AiProviderRegistry()
        self.prompts = PromptService(db, self.repo)

    def __getattr__(self, name: str):
        """Compatibility bridge while callers migrate to ``service.prompts``."""
        prompt_api = {
            "list_prompt_templates",
            "create_prompt_template",
            "update_prompt_template",
            "create_prompt_version",
            "update_prompt_version",
            "list_prompt_versions",
        }
        if name in prompt_api:
            return getattr(self.prompts, name)
        raise AttributeError(f"{type(self).__name__!r} object has no attribute {name!r}")

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

    async def get_overview(self, user: User):
        counts = await self.repo.get_overview_counts_for_user(user.id)
        recent_runs = await self.repo.list_runs_for_user(user.id, limit=5)
        return {
            "providers": self.list_provider_descriptors(),
            "recent_runs": recent_runs,
            **counts,
        }
