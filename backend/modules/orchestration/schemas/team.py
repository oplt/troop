from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel
from backend.modules.orchestration.schemas.common import *  # noqa: F403


class TeamTemplateResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    slug: str
    name: str
    description: str
    outcome: str
    roles: list[str]
    tools: list[str]
    autonomy: str
    visibility: str
    agent_template_slugs: list[str]
    canvas_layout: dict[str, Any] = Field(default_factory=dict)


class TeamTemplateCreate(RequestModel):
    slug: str = Field(min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    name: str = Field(min_length=2, max_length=255)
    description: str = ""
    outcome: str = ""
    roles: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    autonomy: str = "medium"
    visibility: str = "private"
    agent_template_slugs: list[str] = Field(default_factory=list)
    canvas_layout: dict[str, Any] = Field(default_factory=dict)


class TeamTemplateUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=2, max_length=255)
    description: str | None = None
    outcome: str | None = None
    roles: list[str] | None = None
    tools: list[str] | None = None
    autonomy: str | None = None
    visibility: str | None = None
    agent_template_slugs: list[str] | None = None
    canvas_layout: dict[str, Any] | None = None


class TeamProfileResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str | None = None
    source_team_template_slug: str
    slug: str
    name: str
    description: str
    outcome: str
    roles: list[str]
    tools: list[str]
    autonomy: str
    visibility: str
    agent_template_slugs: list[str]
    canvas_layout: dict[str, Any] = Field(default_factory=dict)


class TeamProfileCreateFromTemplate(RequestModel):
    template_id: str
    slug: str | None = Field(
        default=None, min_length=2, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$"
    )
    name: str | None = Field(default=None, min_length=2, max_length=255)
