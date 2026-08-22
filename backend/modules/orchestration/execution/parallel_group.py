"""Manifest-validated parallel read groups for tool execution."""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass
from typing import Any, Literal

from backend.core.config import settings
from backend.modules.workforce.action_metadata import (
    IdempotencyStrategy,
    SideEffect,
    governance_for_action_key,
)
from backend.modules.workforce.services.tool_governance import (
    catalog_tool_requires_approval,
    tool_requires_hitl_execution_grant,
)

ToolCallBatchKind = Literal["serial", "parallel"]


@dataclass(frozen=True, slots=True)
class ToolCallBatch:
    kind: ToolCallBatchKind
    items: tuple[tuple[int, dict[str, Any]], ...]


def parallel_group_id(call: dict[str, Any]) -> str | None:
    raw = call.get("parallel_group_id")
    if raw is None:
        raw = call.get("parallel_group")
    if raw is None:
        return None
    text = str(raw).strip()
    return text or None


def provider_key_for_tool(tool_slug: str) -> str:
    slug = str(tool_slug or "").strip()
    if "." in slug:
        return slug.split(".", 1)[0]
    if slug.startswith("github_"):
        return "github"
    if slug.startswith(("mcp.", "a2a.")):
        return slug.split(".", 1)[0]
    return "native"


def tool_call_parallel_eligible(tool_slug: str) -> bool:
    """Runtime gate: only canonical read-only parallel_safe tools may fan out."""
    slug = str(tool_slug or "").strip()
    if not slug:
        return False
    if catalog_tool_requires_approval(slug) or tool_requires_hitl_execution_grant(slug):
        return False
    governance = governance_for_action_key(slug)
    if not governance.parallel_safe:
        return False
    if governance.side_effect != SideEffect.READ:
        return False
    return governance.idempotency_strategy in {
        IdempotencyStrategy.NONE,
        IdempotencyStrategy.APPROVAL_DEDUP_ONLY,
    }


def parallel_group_eligible(calls: Sequence[dict[str, Any]]) -> bool:
    if len(calls) < 2:
        return False
    group_ids = {parallel_group_id(call) for call in calls}
    if len(group_ids) != 1 or None in group_ids:
        return False
    for call in calls:
        tool_name = str(call.get("tool") or "").strip()
        if not tool_call_parallel_eligible(tool_name):
            return False
        if call.get("approval_granted"):
            continue
        if bool(call.get("requires_approval")):
            return False
    return True


def partition_tool_calls(tool_calls: list[dict[str, Any]]) -> list[ToolCallBatch]:
    batches: list[ToolCallBatch] = []
    index = 0
    while index < len(tool_calls):
        call = tool_calls[index]
        group_id = parallel_group_id(call)
        if group_id is None:
            batches.append(ToolCallBatch("serial", ((index, call),)))
            index += 1
            continue

        grouped: list[tuple[int, dict[str, Any]]] = [(index, call)]
        cursor = index + 1
        while cursor < len(tool_calls):
            next_call = tool_calls[cursor]
            if parallel_group_id(next_call) != group_id:
                break
            grouped.append((cursor, next_call))
            cursor += 1

        if len(grouped) > 1 and parallel_group_eligible([item[1] for item in grouped]):
            batches.append(ToolCallBatch("parallel", tuple(grouped)))
        else:
            for item in grouped:
                batches.append(ToolCallBatch("serial", (item,)))
        index = cursor
    return batches


class ParallelGroupLimiter:
    _workspace_limiters: dict[str, asyncio.Semaphore] = {}
    _provider_limiters: dict[tuple[str, str], asyncio.Semaphore] = {}
    _lock = asyncio.Lock()

    @classmethod
    async def acquire(cls, *, workspace_key: str, provider_key: str) -> None:
        workspace_sem = await cls._get_workspace_semaphore(workspace_key)
        provider_sem = await cls._get_provider_semaphore(workspace_key, provider_key)
        await workspace_sem.acquire()
        try:
            await provider_sem.acquire()
        except Exception:
            workspace_sem.release()
            raise

    @classmethod
    def release(cls, *, workspace_key: str, provider_key: str) -> None:
        provider_sem = cls._provider_limiters.get((workspace_key, provider_key))
        workspace_sem = cls._workspace_limiters.get(workspace_key)
        if provider_sem is not None:
            provider_sem.release()
        if workspace_sem is not None:
            workspace_sem.release()

    @classmethod
    async def _get_workspace_semaphore(cls, workspace_key: str) -> asyncio.Semaphore:
        async with cls._lock:
            sem = cls._workspace_limiters.get(workspace_key)
            if sem is None:
                sem = asyncio.Semaphore(max(1, settings.PARALLEL_READ_WORKSPACE_MAX_INFLIGHT))
                cls._workspace_limiters[workspace_key] = sem
            return sem

    @classmethod
    async def _get_provider_semaphore(
        cls, workspace_key: str, provider_key: str
    ) -> asyncio.Semaphore:
        key = (workspace_key, provider_key)
        async with cls._lock:
            sem = cls._provider_limiters.get(key)
            if sem is None:
                sem = asyncio.Semaphore(max(1, settings.PARALLEL_READ_PROVIDER_MAX_INFLIGHT))
                cls._provider_limiters[key] = sem
            return sem


async def run_parallel_group(
    calls: Sequence[tuple[int, dict[str, Any]]],
    *,
    workspace_key: str,
    execute_call: Callable[[int, dict[str, Any]], Awaitable[dict[str, Any]]],
    max_concurrency: int | None = None,
) -> list[tuple[int, dict[str, Any]]]:
    """Execute a validated parallel read group with bounded workspace/provider concurrency."""
    limit = max(1, max_concurrency or settings.PARALLEL_READ_GROUP_MAX_CONCURRENCY)
    semaphore = asyncio.Semaphore(min(limit, len(calls)))

    async def _run_one(index: int, call: dict[str, Any]) -> tuple[int, dict[str, Any]]:
        tool_name = str(call.get("tool") or "").strip()
        provider_key = provider_key_for_tool(tool_name)
        async with semaphore:
            await ParallelGroupLimiter.acquire(
                workspace_key=workspace_key, provider_key=provider_key
            )
            try:
                result = await execute_call(index, call)
            finally:
                ParallelGroupLimiter.release(workspace_key=workspace_key, provider_key=provider_key)
        return index, result

    gathered = await asyncio.gather(
        *(_run_one(index, call) for index, call in calls),
        return_exceptions=True,
    )
    ordered: list[tuple[int, dict[str, Any]]] = []
    for item in gathered:
        if isinstance(item, BaseException):
            raise item
        ordered.append(item)
    ordered.sort(key=lambda pair: pair[0])
    return ordered
