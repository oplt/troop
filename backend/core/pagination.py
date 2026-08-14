"""Stable cursor pagination helpers (created_at + id tie-breaker)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, TypeVar

from sqlalchemy import tuple_
from sqlalchemy.sql import Select

T = TypeVar("T")


class _HasCreatedAtId(Protocol):
    created_at: Any
    id: Any


class _HasPositionCreatedAtId(Protocol):
    position: Any
    created_at: Any
    id: Any


@dataclass(frozen=True, slots=True)
class CursorToken:
    created_at: datetime
    id: str
    position: int | None = None


def fetch_limit(limit: int) -> int:
    """Request one extra row to detect a next page without a COUNT query."""
    return max(1, limit) + 1


def paginate_rows(
    rows: list[T],
    limit: int,
    *,
    token_from_row: Any,
) -> tuple[list[T], CursorToken | None]:
    if len(rows) > limit:
        page = rows[:limit]
        return page, token_from_row(page[-1])
    return rows, None


def token_from_created_at_id(row: _HasCreatedAtId) -> CursorToken:
    return CursorToken(created_at=row.created_at, id=str(row.id))


def token_from_position_created_at_id(row: _HasPositionCreatedAtId) -> CursorToken:
    return CursorToken(
        created_at=row.created_at,
        id=str(row.id),
        position=int(row.position),
    )


def apply_desc_time_id_cursor(
    stmt: Select[Any],
    model: type[_HasCreatedAtId],
    *,
    cursor_created_at: datetime | None,
    cursor_id: str | None,
) -> Select[Any]:
    if cursor_created_at is not None and cursor_id:
        return stmt.where(
            tuple_(model.created_at, model.id) < tuple_(cursor_created_at, cursor_id)
        )
    if cursor_created_at is not None:
        return stmt.where(model.created_at < cursor_created_at)
    return stmt


def apply_asc_time_id_cursor(
    stmt: Select[Any],
    model: type[_HasCreatedAtId],
    *,
    cursor_created_at: datetime | None,
    cursor_id: str | None,
) -> Select[Any]:
    if cursor_created_at is not None and cursor_id:
        return stmt.where(
            tuple_(model.created_at, model.id) > tuple_(cursor_created_at, cursor_id)
        )
    if cursor_created_at is not None:
        return stmt.where(model.created_at > cursor_created_at)
    return stmt


def apply_asc_position_time_id_cursor(
    stmt: Select[Any],
    model: type[_HasPositionCreatedAtId],
    *,
    cursor_position: int | None,
    cursor_created_at: datetime | None,
    cursor_id: str | None,
) -> Select[Any]:
    if cursor_position is not None and cursor_created_at is not None and cursor_id:
        return stmt.where(
            tuple_(model.position, model.created_at, model.id)
            > tuple_(cursor_position, cursor_created_at, cursor_id)
        )
    return stmt


def simulate_desc_time_id_pages(
    rows: list[tuple[datetime, str]],
    *,
    limit: int,
) -> list[list[tuple[datetime, str]]]:
    """Pure cursor walk used to prove no duplicates/skips for a fixed row set."""
    from dataclasses import dataclass

    @dataclass
    class _Row:
        created_at: datetime
        id: str

    sorted_rows = sorted(rows, key=lambda item: (item[0], item[1]), reverse=True)
    entities = [_Row(created_at=ca, id=row_id) for ca, row_id in sorted_rows]
    pages: list[list[tuple[datetime, str]]] = []
    cursor_created_at: datetime | None = None
    cursor_id: str | None = None

    while True:
        remaining = entities
        if cursor_created_at is not None and cursor_id:
            remaining = [
                row
                for row in entities
                if (row.created_at, row.id) < (cursor_created_at, cursor_id)
            ]
        elif cursor_created_at is not None:
            remaining = [row for row in entities if row.created_at < cursor_created_at]

        page_entities, next_token = paginate_rows(
            remaining[: fetch_limit(limit)],
            limit,
            token_from_row=token_from_created_at_id,
        )
        if not page_entities:
            break
        pages.append([(row.created_at, row.id) for row in page_entities])
        if next_token is None:
            break
        cursor_created_at = next_token.created_at
        cursor_id = next_token.id

    return pages


def build_cursor_page(
    rows: list[T],
    limit: int,
    *,
    token_from_row: Any,
) -> tuple[list[T], Any]:
    page, token = paginate_rows(rows, limit, token_from_row=token_from_row)
    return page, to_cursor_response(token)


def to_cursor_response(token: CursorToken | None):
    from backend.core.schemas import CursorTokenResponse

    if token is None:
        return None
    return CursorTokenResponse(
        created_at=token.created_at,
        id=token.id,
        position=token.position,
    )
