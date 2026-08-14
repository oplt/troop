from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class SkillPackResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    slug: str
    name: str
    description: str | None
    capabilities: list[str]
    allowed_tools: list[str]
    rules_markdown: str
    tags: list[str]


class SkillPackCreate(RequestModel):
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=2, max_length=255)
    description: str | None = None
    capabilities: list[str] = Field(default_factory=list)
    allowed_tools: list[str] = Field(default_factory=list)
    rules_markdown: str = ""
    tags: list[str] = Field(default_factory=list)


class SkillPackUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    capabilities: list[str] | None = None
    allowed_tools: list[str] | None = None
    rules_markdown: str | None = None
    tags: list[str] | None = None
