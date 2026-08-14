"""Control-plane pub/sub event bus."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "agent"


def control_plane_now() -> datetime:
    return datetime.now(UTC)


def task_is_active(status: str) -> bool:
    return status not in {"completed", "approved", "archived", "synced_to_github"}


@dataclass
class ControlPlaneEvent:
    event_type: str
    project_id: str | None
    member_id: str | None
    task_id: str | None
    run_id: str | None
    status: str | None
    payload: dict[str, Any]
    emitted_at: datetime


class ControlPlanePubSub:
    def __init__(self) -> None:
        self._queues: set[Any] = set()

    async def publish(self, event: ControlPlaneEvent) -> None:
        for queue in list(self._queues):
            await queue.put(event)

    async def subscribe(self):
        import asyncio

        queue: asyncio.Queue[ControlPlaneEvent] = asyncio.Queue()
        self._queues.add(queue)
        try:
            while True:
                yield await queue.get()
        finally:
            self._queues.discard(queue)


control_plane_pubsub = ControlPlanePubSub()

# Backward-compatible aliases used by extracted modules.
_slugify = slugify
_now = control_plane_now
_task_is_active = task_is_active
