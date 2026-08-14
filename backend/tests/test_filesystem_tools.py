"""PERF-003: bounded and offloaded filesystem tool I/O."""

from __future__ import annotations

import asyncio
import time
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from backend.modules.orchestration.filesystem_tools import (
    FilesystemToolError,
    read_bounded_text_sync,
    write_bounded_text,
    write_bounded_text_sync,
)
from backend.modules.orchestration.tools import OrchestrationToolbox, ToolExecutionError


@pytest.mark.asyncio
async def test_read_bounded_text_sync_rejects_oversized_file(tmp_path: Path) -> None:
    target = tmp_path / "large.txt"
    target.write_bytes(b"x" * 200)
    with pytest.raises(FilesystemToolError, match="exceeds maximum read size"):
        read_bounded_text_sync(target, max_bytes=100)


@pytest.mark.asyncio
async def test_read_bounded_text_sync_reads_without_loading_beyond_limit(tmp_path: Path) -> None:
    target = tmp_path / "small.txt"
    target.write_text("hello")
    assert read_bounded_text_sync(target, max_bytes=100) == "hello"


@pytest.mark.asyncio
async def test_write_bounded_text_sync_rejects_oversized_content(tmp_path: Path) -> None:
    target = tmp_path / "out.txt"
    with pytest.raises(FilesystemToolError, match="Write exceeds maximum size"):
        write_bounded_text_sync(target, "x" * 20, max_bytes=10)


@pytest.mark.asyncio
async def test_fs_read_rejects_oversized_file_via_toolbox(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    (workspace / "big.bin").write_bytes(b"a" * 128)

    toolbox = OrchestrationToolbox(
        db=AsyncMock(),
        repo=MagicMock(),
        project=SimpleNamespace(
            id="p1",
            owner_id="o1",
            settings_json={"workspace_root": str(workspace)},
        ),
        task=None,
        run=None,
    )
    monkeypatch.setattr(
        "backend.modules.orchestration.tools.read_bounded_text",
        AsyncMock(
            side_effect=FilesystemToolError(
                "File exceeds maximum read size (128 bytes > 64 bytes)"
            )
        ),
    )
    with pytest.raises(ToolExecutionError, match="exceeds maximum read size"):
        await toolbox._fs_read({"path": "big.bin"})


@pytest.mark.asyncio
async def test_fs_write_rejects_oversized_content_via_toolbox(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()

    toolbox = OrchestrationToolbox(
        db=AsyncMock(),
        repo=MagicMock(),
        project=SimpleNamespace(
            id="p1",
            owner_id="o1",
            settings_json={"workspace_root": str(workspace)},
        ),
        task=None,
        run=None,
    )
    monkeypatch.setattr(
        "backend.modules.orchestration.tools.write_bounded_text",
        AsyncMock(
            side_effect=FilesystemToolError(
                "Write exceeds maximum size (100 bytes > 32 bytes)"
            )
        ),
    )
    with pytest.raises(ToolExecutionError, match="Write exceeds maximum size"):
        await toolbox._fs_write({"path": "out.txt", "content": "x" * 100})


@pytest.mark.asyncio
async def test_fs_read_offloads_blocking_io_to_thread(tmp_path: Path, monkeypatch) -> None:
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    target = workspace / "slow.txt"
    target.write_text("payload")

    async def slow_read(path: Path, *, max_bytes: int | None = None) -> str:
        return await asyncio.to_thread(_slow_read_sync, path)

    def _slow_read_sync(path: Path) -> str:
        time.sleep(0.2)
        return path.read_text(encoding="utf-8")

    toolbox = OrchestrationToolbox(
        db=AsyncMock(),
        repo=MagicMock(),
        project=SimpleNamespace(
            id="p1",
            owner_id="o1",
            settings_json={"workspace_root": str(workspace)},
        ),
        task=None,
        run=None,
    )
    monkeypatch.setattr("backend.modules.orchestration.tools.read_bounded_text", slow_read)

    order: list[str] = []

    async def run_read() -> None:
        order.append("read_start")
        await toolbox._fs_read({"path": "slow.txt"})
        order.append("read_end")

    async def ping() -> None:
        await asyncio.sleep(0.05)
        order.append("ping")

    await asyncio.gather(run_read(), ping())
    assert order.index("ping") < order.index("read_end")


@pytest.mark.asyncio
async def test_write_bounded_text_uses_thread_pool(tmp_path: Path) -> None:
    target = tmp_path / "nested" / "file.txt"
    written = await write_bounded_text(target, "saved", max_bytes=64)
    assert written == 5
    assert target.read_text(encoding="utf-8") == "saved"
