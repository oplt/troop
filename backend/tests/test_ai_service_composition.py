from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.ai.prompts.service import PromptService
from backend.modules.ai.service import AiService


def test_ai_service_composes_prompt_domain_explicitly() -> None:
    service = AiService(MagicMock())

    assert isinstance(service.prompts, PromptService)
    assert PromptService not in type(service).__mro__[1:]


@pytest.mark.asyncio
async def test_flat_prompt_api_delegates_during_compatibility_window() -> None:
    service = AiService(MagicMock())
    service.prompts.list_prompt_templates = AsyncMock(return_value=["prompt"])

    result = await service.list_prompt_templates(MagicMock())

    assert result == ["prompt"]
    service.prompts.list_prompt_templates.assert_awaited_once()
