from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from backend.core.schemas import RequestModel


class CompanyResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    owner_id: str
    name: str
    slug: str
    brief_markdown: str
    settings_json: dict[str, Any]
    created_at: datetime
    updated_at: datetime


class CompanyCreate(RequestModel):
    name: str = Field(min_length=1, max_length=255)
    slug: str = Field(min_length=1, max_length=255, pattern=r"^[a-z0-9][a-z0-9\-]*$")
    brief_markdown: str = ""
    settings_json: dict[str, Any] = Field(default_factory=dict)


class CompanyUpdate(RequestModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    brief_markdown: str | None = None
    settings_json: dict[str, Any] | None = None
