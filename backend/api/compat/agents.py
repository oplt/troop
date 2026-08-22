from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.compat.schemas import MarkdownImportPayload
from backend.api.deps.auth import get_current_user
from backend.core.logging import get_logger
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.observability.logging import log_event
from backend.modules.orchestration.presenters import to_agent_response
from backend.modules.orchestration.schemas import AgentCreate, AgentResponse, AgentUpdate
from backend.modules.orchestration.services.service import OrchestrationService

router = APIRouter()
logger = get_logger(__name__)


@router.get("", response_model=list[AgentResponse])
async def list_agent_profiles(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return [
        to_agent_response(item)
        for item in await OrchestrationService(db).list_agents(current_user, project_id)
    ]


@router.post("", response_model=AgentResponse, status_code=201)
async def create_agent_profile(
    payload: AgentCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).create_agent(current_user, payload.model_dump())
    log_event(
        logger,
        "agent_created",
        user_id=current_user.id,
        agent_id=item.id,
        project_id=item.project_id,
    )
    return to_agent_response(item)


@router.post("/import-markdown", response_model=AgentResponse, status_code=201)
async def import_agent_profile_markdown(
    payload: MarkdownImportPayload,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).import_agent_markdown(
        current_user,
        content=payload.content,
        project_id=payload.project_id,
        existing_agent_id=payload.existing_agent_id,
    )
    log_event(
        logger,
        "agent_imported_markdown",
        user_id=current_user.id,
        agent_id=item.id,
        project_id=item.project_id,
    )
    return to_agent_response(item)


@router.get("/{agent_id}", response_model=AgentResponse)
async def get_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    return to_agent_response(await OrchestrationService(db).get_agent(current_user, agent_id))


@router.put("/{agent_id}", response_model=AgentResponse)
async def put_agent_profile(
    agent_id: str,
    payload: AgentUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await OrchestrationService(db).update_agent(
        current_user,
        agent_id,
        payload.model_dump(exclude_unset=True),
    )
    return to_agent_response(item)


@router.delete("/{agent_id}", status_code=204)
async def delete_agent_profile(
    agent_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    await OrchestrationService(db).delete_agent(current_user, agent_id)
