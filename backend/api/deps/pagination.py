"""Shared FastAPI cursor pagination query parameters."""

from __future__ import annotations

from datetime import datetime

from fastapi import Query

from backend.core.config import settings


def cursor_limit_query(
    *,
    default: int | None = None,
    maximum: int | None = None,
) -> int:
    return Query(
        default if default is not None else settings.CURSOR_PAGE_DEFAULT_LIMIT,
        ge=1,
        le=maximum if maximum is not None else settings.CURSOR_PAGE_MAX_LIMIT,
    )


def cursor_created_at_query() -> datetime | None:
    return Query(default=None)


def cursor_id_query() -> str | None:
    return Query(default=None)


def cursor_position_query() -> int | None:
    return Query(default=None)
