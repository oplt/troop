"""Workforce routers package."""

from fastapi import APIRouter

from backend.modules.workforce.routers import (
    connectors,
    departments,
    integrations,
    intelligence,
    marketplace,
    skill_drafts,
    skills,
    tools,
    workflows,
)

router = APIRouter()

router.include_router(departments.router, tags=["workforce-departments"])
router.include_router(skills.router, tags=["workforce-skills"])
router.include_router(skill_drafts.router, tags=["workforce-skill-drafts"])
router.include_router(intelligence.router, tags=["workforce-intelligence"])
router.include_router(tools.router, tags=["workforce-tools"])
router.include_router(workflows.router, tags=["workforce-workflows"])
router.include_router(marketplace.router, tags=["workforce-marketplace"])
router.include_router(connectors.router, tags=["workforce-connectors"])
router.include_router(integrations.router, tags=["workforce-integrations"])

__all__ = ["router"]
