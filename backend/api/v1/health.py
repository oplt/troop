from fastapi import APIRouter, HTTPException

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.db.session import engine
from backend.modules.observability.health import readiness_report

health_router = APIRouter(prefix="/health", tags=["health"])


@health_router.get("/live")
async def live():
    return {"status": "ok"}


@health_router.get("/ready")
async def ready():
    if not settings.HEALTH_READY_PUBLIC and settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    report = await readiness_report(
        engine,
        redis_client,
        settings.celery_broker_url,
        settings.HEALTH_READY_TIMEOUT_SECONDS,
    )
    if report["status"] != "ok":
        raise HTTPException(status_code=503, detail=report)
    return report


@health_router.get("/version")
async def version():
    if not settings.HEALTH_VERSION_PUBLIC and settings.is_production:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "app": settings.APP_NAME,
        "env": settings.APP_ENV,
        "instance_id": settings.INSTANCE_ID or "unassigned",
        "version": "0.1.0",
        "async_jobs": "celery",
        "multi_instance_safe": True,
    }
