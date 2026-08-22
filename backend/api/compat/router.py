from fastapi import APIRouter

from backend.api.compat.agents import router as agents_router
from backend.api.compat.memory import router as memory_router
from backend.api.compat.runs import router as runs_router
from backend.api.compat.tasks import router as tasks_router
from backend.api.compat.tools import router as tools_router

compat_router = APIRouter()
compat_router.include_router(agents_router, prefix="/agents", tags=["agents"])
compat_router.include_router(tools_router, prefix="/tools", tags=["tools"])
compat_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
compat_router.include_router(runs_router, tags=["runs"])
compat_router.include_router(memory_router, prefix="/memory", tags=["memory"])

__all__ = ["compat_router"]
