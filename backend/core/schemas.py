from datetime import datetime
from typing import Generic, TypeVar

from pydantic import BaseModel, ConfigDict

T = TypeVar("T")


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CursorTokenResponse(BaseModel):
    created_at: datetime
    id: str
    position: int | None = None


class CursorPageResponse(BaseModel, Generic[T]):
    items: list[T]
    next_cursor: CursorTokenResponse | None = None
