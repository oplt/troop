from datetime import UTC, date, datetime, time, timedelta

from backend.modules.calendar.repository import date_range_bounds


def test_date_range_bounds_are_half_open_utc() -> None:
    start, end = date_range_bounds(date(2026, 8, 13), date(2026, 8, 13))
    assert start == datetime(2026, 8, 13, 0, 0, tzinfo=UTC)
    assert end == datetime(2026, 8, 14, 0, 0, tzinfo=UTC)


def test_date_range_bounds_include_start_exclude_next_midnight() -> None:
    start, end = date_range_bounds(date(2026, 8, 13), date(2026, 8, 14))
    assert start == datetime.combine(date(2026, 8, 13), time.min, tzinfo=UTC)
    assert end == datetime.combine(date(2026, 8, 15), time.min, tzinfo=UTC)
    assert end - start == timedelta(days=2)


def test_calendar_repository_query_avoids_cast() -> None:
    from pathlib import Path

    source = (Path(__file__).resolve().parents[1] / "modules/calendar/repository.py").read_text()
    assert "cast(" not in source
    assert "from sqlalchemy import Date" not in source
    assert "due_date >=" in source
    assert "due_date <" in source
