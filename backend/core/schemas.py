from datetime import datetime

from pydantic import BaseModel, ConfigDict


class RequestModel(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)


class CursorTokenResponse(BaseModel):
    created_at: datetime
    id: str
    position: int | None = None


class CursorPageResponse[T](BaseModel):
    items: list[T]
    next_cursor: CursorTokenResponse | None = None
