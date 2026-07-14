from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta


@dataclass(frozen=True, slots=True)
class MemoryRetention:
    ttl_days: int | None
    expires_at: datetime | None
    policy: str


def resolve_retention(
    ttl_days: int | None,
    *,
    default_ttl_days: int = 0,
    max_ttl_days: int = 3650,
    policy: str = "default",
) -> MemoryRetention:
    value = default_ttl_days if ttl_days is None else ttl_days
    if value < 0:
        raise ValueError("Memory TTL cannot be negative")
    if value > max_ttl_days:
        raise ValueError(f"Memory TTL cannot exceed {max_ttl_days} days")
    return MemoryRetention(
        ttl_days=value or None,
        expires_at=(datetime.now(UTC) + timedelta(days=value)) if value else None,
        policy=(policy or "default")[:64],
    )
