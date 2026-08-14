"""Bounded, thread-offloaded filesystem helpers for orchestration tools."""

from __future__ import annotations

import asyncio
from pathlib import Path

from backend.core.config import settings


class FilesystemToolError(ValueError):
    """Raised when filesystem tool limits or path checks fail."""


def fs_tool_max_read_bytes() -> int:
    return max(1, int(getattr(settings, "FS_TOOL_MAX_READ_BYTES", 262_144)))


def fs_tool_max_write_bytes() -> int:
    return max(1, int(getattr(settings, "FS_TOOL_MAX_WRITE_BYTES", 524_288)))


def read_bounded_text_sync(path: Path, *, max_bytes: int | None = None) -> str:
    limit = max_bytes or fs_tool_max_read_bytes()
    if not path.is_file():
        raise FileNotFoundError(f"File does not exist: {path}")
    size = path.stat().st_size
    if size > limit:
        raise FilesystemToolError(f"File exceeds maximum read size ({size} bytes > {limit} bytes)")
    with path.open("rb") as handle:
        raw = handle.read(limit)
    return raw.decode("utf-8", errors="replace")


def write_bounded_text_sync(path: Path, content: str, *, max_bytes: int | None = None) -> int:
    limit = max_bytes or fs_tool_max_write_bytes()
    encoded = content.encode("utf-8")
    if len(encoded) > limit:
        raise FilesystemToolError(
            f"Write exceeds maximum size ({len(encoded)} bytes > {limit} bytes)"
        )
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encoded)
    return len(encoded)


async def read_bounded_text(path: Path, *, max_bytes: int | None = None) -> str:
    return await asyncio.to_thread(read_bounded_text_sync, path, max_bytes=max_bytes)


async def write_bounded_text(path: Path, content: str, *, max_bytes: int | None = None) -> int:
    return await asyncio.to_thread(
        write_bounded_text_sync,
        path,
        content,
        max_bytes=max_bytes,
    )
