from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.schemas import (
    PortfolioControlPlaneResponse,
    PortfolioExecutionPolicyResponse,
    PortfolioExecutionPolicyUpdate,
    PortfolioProjectSummary,
)
from backend.modules.orchestration.services.service import OrchestrationService

router = APIRouter(tags=["orchestration-portfolio"])


@router.get("/portfolio", response_model=list[PortfolioProjectSummary])
async def orchestration_portfolio(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    rows = await OrchestrationService(db).summarize_portfolio(current_user)
    return [PortfolioProjectSummary(**row) for row in rows]


@router.get("/portfolio/control-plane", response_model=PortfolioControlPlaneResponse)
async def orchestration_portfolio_control_plane(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).portfolio_control_plane(current_user)
    return PortfolioControlPlaneResponse(**payload)


@router.get("/portfolio/execution-policy", response_model=PortfolioExecutionPolicyResponse)
async def orchestration_portfolio_execution_policy(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).get_portfolio_execution_policy(current_user)
    return PortfolioExecutionPolicyResponse(**payload)


@router.put("/portfolio/execution-policy", response_model=PortfolioExecutionPolicyResponse)
async def update_orchestration_portfolio_execution_policy(
    payload: PortfolioExecutionPolicyUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    data = await OrchestrationService(db).update_portfolio_execution_policy(
        current_user,
        payload.model_dump(exclude_none=True),
    )
    return PortfolioExecutionPolicyResponse(**data)
