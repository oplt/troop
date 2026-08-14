"""Tests for manifest-validated parallel read tool groups (PERF-007)."""

from __future__ import annotations

import asyncio
import time
from typing import Any

import pytest

from backend.modules.orchestration.execution.parallel_group import (
    ParallelGroupLimiter,
    parallel_group_eligible,
    parallel_group_id,
    partition_tool_calls,
    provider_key_for_tool,
    run_parallel_group,
    tool_call_parallel_eligible,
)


def _read_call(tool: str, *, group: str = "ctx") -> dict[str, Any]:
    return {"tool": tool, "parallel_group_id": group, "arguments": {}}


def test_parallel_group_id_accepts_aliases():
    assert parallel_group_id({"parallel_group_id": "a"}) == "a"
    assert parallel_group_id({"parallel_group": "b"}) == "b"
    assert parallel_group_id({}) is None
    assert parallel_group_id({"parallel_group_id": "  "}) is None


def test_read_tools_are_parallel_eligible():
    assert tool_call_parallel_eligible("fs_read") is True
    assert tool_call_parallel_eligible("gmail.search_messages") is True


def test_write_tools_are_not_parallel_eligible():
    assert tool_call_parallel_eligible("fs_write") is False
    assert tool_call_parallel_eligible("github_create_pr") is False
    assert tool_call_parallel_eligible("gmail.send_draft") is False


def test_mixed_group_falls_back_to_serial_batches():
    calls = [
        _read_call("fs_read", group="g1"),
        {"tool": "fs_write", "parallel_group_id": "g1", "arguments": {}},
    ]
    batches = partition_tool_calls(calls)
    assert len(batches) == 2
    assert all(batch.kind == "serial" for batch in batches)


def test_valid_read_group_partitions_as_parallel():
    calls = [
        _read_call("fs_read", group="ctx"),
        _read_call("gmail.search_messages", group="ctx"),
    ]
    assert parallel_group_eligible(calls) is True
    batches = partition_tool_calls(calls)
    assert len(batches) == 1
    assert batches[0].kind == "parallel"
    assert len(batches[0].items) == 2


def test_single_group_member_stays_serial():
    calls = [_read_call("fs_read", group="solo")]
    batches = partition_tool_calls(calls)
    assert len(batches) == 1
    assert batches[0].kind == "serial"


def test_provider_key_for_tool():
    assert provider_key_for_tool("github_create_pr") == "github"
    assert provider_key_for_tool("mcp.linear.search") == "mcp"
    assert provider_key_for_tool("fs_read") == "native"


@pytest.mark.asyncio
async def test_run_parallel_group_orders_results_by_index():
    async def execute_call(index: int, call: dict[str, Any]) -> dict[str, Any]:
        await asyncio.sleep(0.01 * (3 - index))
        return {"tool": call["tool"], "status": "completed", "index": index}

    calls = [(0, _read_call("fs_read")), (1, _read_call("gmail.search_messages"))]
    results = await run_parallel_group(
        calls,
        workspace_key="ws-1",
        execute_call=execute_call,
        max_concurrency=4,
    )
    assert [index for index, _ in results] == [0, 1]
    assert results[0][1]["tool"] == "fs_read"
    assert results[1][1]["tool"] == "gmail.search_messages"


@pytest.mark.asyncio
async def test_parallel_group_faster_than_serial_for_mocked_io():
    delay_s = 0.05
    call_count = 0

    async def execute_call(index: int, call: dict[str, Any]) -> dict[str, Any]:
        nonlocal call_count
        call_count += 1
        await asyncio.sleep(delay_s)
        return {"tool": call["tool"], "status": "completed"}

    calls = [
        (0, _read_call("fs_read", group="bench")),
        (1, _read_call("gmail.search_messages", group="bench")),
        (2, _read_call("web_fetch", group="bench")),
    ]

    serial_start = time.perf_counter()
    for index, call in calls:
        await execute_call(index, call)
    serial_elapsed = time.perf_counter() - serial_start

    call_count = 0
    parallel_start = time.perf_counter()
    await run_parallel_group(
        calls,
        workspace_key="bench-ws",
        execute_call=execute_call,
        max_concurrency=4,
    )
    parallel_elapsed = time.perf_counter() - parallel_start

    assert call_count == len(calls)
    assert parallel_elapsed < serial_elapsed * 0.75


@pytest.mark.asyncio
async def test_parallel_group_limiter_acquire_release():
    ParallelGroupLimiter._workspace_limiters.clear()
    ParallelGroupLimiter._provider_limiters.clear()
    await ParallelGroupLimiter.acquire(workspace_key="ws", provider_key="native")
    ParallelGroupLimiter.release(workspace_key="ws", provider_key="native")
