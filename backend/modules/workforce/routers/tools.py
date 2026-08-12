"""Tool and workflow registry endpoints."""

from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.schemas import ToolDefinitionResponse
from backend.modules.workforce.services.tool_registry import ToolRegistryService

router = APIRouter(prefix="/tools")


@router.get("", response_model=list[ToolDefinitionResponse])
async def list_workforce_tools(
    is_active: bool | None = True,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[ToolDefinitionResponse]:
    """List available tool definitions."""
    service = ToolRegistryService(db)
    tools = await service.list_tools(is_active=is_active)
    return [ToolDefinitionResponse.model_validate(t) for t in tools]
