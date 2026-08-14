"""Tests for stable cursor pagination (DATA-001A)."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

from backend.core.pagination import (
    build_cursor_page,
    paginate_rows,
    simulate_desc_time_id_pages,
    token_from_created_at_id,
)


def test_paginate_rows_returns_next_cursor_when_extra_row_present() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    class _Row:
        def __init__(self, idx: int) -> None:
            self.created_at = base + timedelta(minutes=idx)
            self.id = f"id-{idx}"

    rows = [_Row(i) for i in range(3)]
    page, token = paginate_rows(rows, 2, token_from_row=token_from_created_at_id)
    assert len(page) == 2
    assert token is not None
    assert token.id == "id-1"


def test_build_cursor_page_has_no_next_cursor_on_short_page() -> None:
    base = datetime(2026, 1, 1, tzinfo=UTC)

    class _Row:
        created_at = base
        id = "only"

    page, next_cursor = build_cursor_page([_Row()], 50, token_from_row=token_from_created_at_id)
    assert len(page) == 1
    assert next_cursor is None


def test_desc_cursor_pages_cover_all_rows_without_dup_or_skip() -> None:
    base = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    rows = [
        (base + timedelta(seconds=idx), f"row-{idx:03d}")
        for idx in range(37)
    ]
    # Simulate a concurrent insert landing between page fetches.
    rows.insert(18, (base + timedelta(seconds=18, milliseconds=500), "row-concurrent"))

    pages = simulate_desc_time_id_pages(rows, limit=10)
    flattened = [item for page in pages for item in page]
    assert len(flattened) == len(rows)
    assert len(flattened) == len(set(flattened))
    assert sorted(flattened, reverse=True) == sorted(rows, reverse=True)


def test_desc_cursor_pages_handle_duplicate_created_at_with_id_tiebreak() -> None:
    base = datetime(2026, 6, 1, 12, 0, tzinfo=UTC)
    rows = [
        (base, "b"),
        (base, "a"),
        (base - timedelta(seconds=1), "c"),
    ]
    pages = simulate_desc_time_id_pages(rows, limit=2)
    flattened = [item for page in pages for item in page]
    assert flattened == [(base, "b"), (base, "a"), (base - timedelta(seconds=1), "c")]
