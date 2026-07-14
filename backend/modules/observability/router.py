from __future__ import annotations

from fastapi import APIRouter, HTTPException
from fastapi.responses import PlainTextResponse

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.modules.observability.metrics import metrics_registry
from backend.modules.observability.queue import refresh_queue_metrics

observability_router = APIRouter(tags=["observability"])


@observability_router.get("/metrics", response_class=PlainTextResponse)
async def metrics() -> PlainTextResponse:
    if not settings.METRICS_ENABLED or (settings.is_production and not settings.METRICS_PUBLIC):
        raise HTTPException(status_code=404, detail="Not found")
    if settings.METRICS_QUEUE_REFRESH_ENABLED:
        await refresh_queue_metrics(redis_client)
    return PlainTextResponse(
        metrics_registry.render_prometheus(),
        media_type="text/plain; version=0.0.4",
    )


__all__ = ["observability_router"]
