"""Ownership helpers for workforce foreign IDs."""

from __future__ import annotations

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.companies.models import Company
from backend.modules.projects.orchestration_models import OrchestratorProject, OrchestratorTask


async def assert_company_owned(db: AsyncSession, owner_id: str, company_id: str | None) -> None:
    if not company_id:
        return
    result = await db.execute(
        select(Company.id).where(Company.id == company_id, Company.owner_id == owner_id)
    )
    if result.scalar_one_or_none() is None:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="company access denied")


async def assert_project_owned(
    db: AsyncSession, owner_id: str, project_id: str | None
) -> OrchestratorProject | None:
    if not project_id:
        return None
    result = await db.execute(
        select(OrchestratorProject).where(OrchestratorProject.id == project_id)
    )
    project = result.scalar_one_or_none()
    if project is None or project.owner_id != owner_id:
        raise HTTPException(status.HTTP_403_FORBIDDEN, detail="project access denied")
    return project


async def assert_task_owned(
    db: AsyncSession, owner_id: str, task_id: str | None
) -> OrchestratorTask | None:
    if not task_id:
        return None
    result = await db.execute(select(OrchestratorTask).where(OrchestratorTask.id == task_id))
    task = result.scalar_one_or_none()
    if task is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, detail="task not found")
    await assert_project_owned(db, owner_id, task.project_id)
    return task
