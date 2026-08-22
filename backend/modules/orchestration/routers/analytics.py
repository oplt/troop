from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.schemas import CostAggregationResponse, ExecutionInsightsResponse
from backend.modules.orchestration.services.service import OrchestrationService

router = APIRouter(prefix="/analytics", tags=["orchestration-analytics"])


@router.get("/cost", response_model=CostAggregationResponse)
async def cost_analytics(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).aggregate_cost_analytics(current_user, days)
    return CostAggregationResponse(**payload)


@router.get("/execution-insights", response_model=ExecutionInsightsResponse)
async def execution_insights(
    days: int = Query(7, ge=1, le=90),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    payload = await OrchestrationService(db).execution_insights(current_user, days)
    return ExecutionInsightsResponse(**payload)


@router.get("/agent-performance")
async def agent_performance(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).agent_performance_scorecard(current_user, days)


@router.get("/budget-projection")
async def budget_projection(
    days: int = Query(30, ge=1, le=365),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return await OrchestrationService(db).project_budget_projection(current_user, days)
