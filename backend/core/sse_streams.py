"""Shared server-sent event snapshot streams for live UI invalidation."""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, StreamingResponse

from backend.core.config import settings
from backend.modules.observability.metrics import record_sse_event

_sse_slots = asyncio.Semaphore(max(1, settings.SSE_MAX_CONNECTIONS))


async def live_snapshot_stream(
    snapshot_factory: Callable[[], Awaitable[Any]],
    *,
    request: Request,
    stream_name: str,
):
    try:
        await asyncio.wait_for(_sse_slots.acquire(), timeout=0.05)
    except TimeoutError:
        record_sse_event(stream_name, "rejected")
        return JSONResponse(
            status_code=503,
            content={"detail": "Live stream capacity is temporarily exhausted"},
            headers={"Retry-After": "5"},
        )

    last_signature: str | None = None
    record_sse_event(stream_name, "opened", delta_connections=1)

    async def event_stream():
        nonlocal last_signature
        loop = asyncio.get_running_loop()
        started_at = loop.time()
        last_heartbeat_at = started_at
        try:
            while loop.time() - started_at < settings.SSE_MAX_DURATION_SECONDS:
                if await request.is_disconnected():
                    record_sse_event(stream_name, "disconnected")
                    return

                snapshot = await snapshot_factory()
                payload = json.dumps(snapshot, default=str, sort_keys=True)
                now = loop.time()
                if len(payload.encode("utf-8")) > settings.SSE_MAX_PAYLOAD_BYTES:
                    record_sse_event(stream_name, "payload_dropped")
                elif payload != last_signature:
                    last_signature = payload
                    last_heartbeat_at = now
                    record_sse_event(stream_name, "snapshot")
                    yield f"event: snapshot\ndata: {payload}\n\n"
                elif now - last_heartbeat_at >= settings.SSE_HEARTBEAT_SECONDS:
                    last_heartbeat_at = now
                    record_sse_event(stream_name, "heartbeat")
                    yield "event: heartbeat\ndata: {}\n\n"

                await asyncio.sleep(max(0.1, settings.SSE_POLL_INTERVAL_SECONDS))
        except asyncio.CancelledError:
            record_sse_event(stream_name, "cancelled")
            raise
        finally:
            _sse_slots.release()
            record_sse_event(stream_name, "closed", delta_connections=-1)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
