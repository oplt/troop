from fastapi import APIRouter

from backend.app.agents.router import (
    agents_router,
    memory_router,
    runs_router,
    tasks_router,
    tools_router,
)
from backend.modules.admin.router import router as admin_router
from backend.modules.ai.router import router as ai_router
from backend.modules.calendar.router import router as calendar_router
from backend.modules.companies.router import router as companies_router
from backend.modules.github.router import router as github_router
from backend.modules.identity_access.router import router as auth_router
from backend.modules.notifications.router import router as notifications_router
from backend.modules.orchestration.router import router as orchestration_router
from backend.modules.platform.router import router as platform_router
from backend.modules.rag.router import router as rag_router
from backend.modules.profile.router import router as profile_router
from backend.modules.settings.router import router as settings_router
from backend.modules.users.router import router as users_router
from backend.modules.workforce.routers import router as workforce_router

api_router = APIRouter(prefix="/api/v1")

api_router.include_router(auth_router, prefix="/auth", tags=["auth"])
api_router.include_router(ai_router, prefix="/ai", tags=["ai"])
api_router.include_router(calendar_router, prefix="/calendar", tags=["calendar"])
api_router.include_router(companies_router, prefix="/companies", tags=["companies"])
api_router.include_router(users_router, prefix="/users", tags=["users"])
api_router.include_router(profile_router, prefix="/profile", tags=["profile"])
api_router.include_router(orchestration_router, prefix="/orchestration", tags=["orchestration"])
api_router.include_router(rag_router, prefix="/rag", tags=["rag"])
api_router.include_router(github_router, prefix="/orchestration", tags=["github"])
api_router.include_router(notifications_router, prefix="/notifications", tags=["notifications"])
api_router.include_router(platform_router, prefix="/platform", tags=["platform"])
api_router.include_router(settings_router, prefix="/settings", tags=["settings"])
api_router.include_router(admin_router, prefix="/admin", tags=["admin"])
api_router.include_router(agents_router, prefix="/agents", tags=["agents"])
api_router.include_router(tools_router, prefix="/tools", tags=["tools"])
api_router.include_router(tasks_router, prefix="/tasks", tags=["tasks"])
api_router.include_router(runs_router, prefix="/runs", tags=["runs"])
api_router.include_router(memory_router, prefix="/memory", tags=["memory"])
api_router.include_router(workforce_router, prefix="/workforce", tags=["workforce"])
