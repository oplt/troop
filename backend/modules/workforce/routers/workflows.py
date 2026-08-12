"""Workflow definition endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.repository import WorkforceRepository
from backend.modules.workforce.schemas import WorkflowDefinitionResponse

router = APIRouter(prefix="/workflows")


@router.get("", response_model=list[WorkflowDefinitionResponse])
async def list_workflows(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[WorkflowDefinitionResponse]:
    """List workflow definitions available to the user."""
    repo = WorkforceRepository(db)
    workflows = await repo.list_workflows(user.id)
    return [WorkflowDefinitionResponse.model_validate(w) for w in workflows]
