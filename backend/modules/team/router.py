from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.identity_access.models import User
from backend.modules.orchestration.service import OrchestrationService
from backend.modules.team.schemas import (
    ProjectAgentMembershipCreate,
    ProjectAgentMembershipResponse,
    ProjectAgentMembershipUpdate,
)

router = APIRouter()


def _project_agent(item) -> ProjectAgentMembershipResponse:
    return ProjectAgentMembershipResponse(
        id=item.id,
        project_id=item.project_id,
        agent_id=item.agent_id,
        role=item.role,
        is_default_manager=item.is_default_manager,
        created_at=item.created_at,
    )


@router.get("/projects/{project_id}/agents", response_model=list[ProjectAgentMembershipResponse])
async def list_project_agents(
    project_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return [_project_agent(item) for item in await service.list_project_agents(current_user, project_id)]


@router.post("/projects/{project_id}/agents", response_model=ProjectAgentMembershipResponse, status_code=201)
async def add_project_agent(
    project_id: str,
    payload: ProjectAgentMembershipCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return _project_agent(await service.add_project_agent(current_user, project_id, payload.model_dump()))


@router.patch("/projects/{project_id}/agents/{membership_id}", response_model=ProjectAgentMembershipResponse)
async def update_project_agent(
    project_id: str,
    membership_id: str,
    payload: ProjectAgentMembershipUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = OrchestrationService(db)
    return _project_agent(
        await service.update_project_agent(
            current_user,
            project_id,
            membership_id,
            payload.model_dump(exclude_unset=True),
        )
    )
