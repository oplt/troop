from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.compat.schemas import (
    MemoryCreate,
    MemoryResponse,
    MemoryScope,
    MemorySearch,
    MemoryUpdate,
    memory_response,
)
from backend.api.deps.auth import get_current_user
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.memory.layer.schemas import MemoryFilters
from backend.modules.memory.layer.service import MemoryService

router = APIRouter()


def _scope_metadata(
    scope: MemoryScope,
    scope_id: str,
    metadata: dict,
) -> tuple[str | None, dict]:
    normalized = dict(metadata)
    project_id = normalized.get("project_id")
    if scope == "company":
        normalized["company_id"] = scope_id
        project_id = None
    elif scope == "project":
        normalized["project_id"] = scope_id
        project_id = scope_id
    elif scope == "agent":
        normalized["agent_id"] = scope_id
    elif scope == "task":
        normalized["task_id"] = scope_id
    normalized.setdefault("entry_type", normalized.get("entry_type") or "note")
    return project_id, normalized


def _scope_filters(scope: MemoryScope, scope_id: str, user_id: str) -> MemoryFilters:
    filters = MemoryFilters(user_id=user_id, scope=scope)
    if scope == "company":
        filters.company_id = scope_id
    elif scope == "project":
        filters.project_id = scope_id
    elif scope == "agent":
        filters.agent_id = scope_id
    elif scope == "task":
        filters.task_id = scope_id
    return filters


@router.post("", response_model=MemoryResponse, status_code=201)
async def create_memory(
    payload: MemoryCreate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    project_id, metadata = _scope_metadata(
        payload.scope,
        payload.scope_id,
        payload.metadata,
    )
    item = await MemoryService(db).add_memory(
        current_user.id,
        payload.content,
        metadata,
        scope=payload.scope,
        project_id=project_id,
    )
    if item is None:
        raise HTTPException(
            status_code=422,
            detail="Memory was blocked by privacy policy or memory is disabled.",
        )
    return memory_response(item)


@router.get("", response_model=list[MemoryResponse])
async def list_memory(
    scope: MemoryScope,
    scope_id: str,
    limit: int = Query(default=50, ge=1, le=100),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = await MemoryService(db).list_memories(
        current_user.id,
        limit=limit,
        filters=_scope_filters(scope, scope_id, current_user.id),
    )
    return [memory_response(item) for item in records]


@router.post("/search", response_model=list[MemoryResponse])
async def search_memory(
    payload: MemorySearch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    records = await MemoryService(db).search_memories(
        current_user.id,
        payload.query,
        limit=payload.limit,
        filters=_scope_filters(payload.scope, payload.scope_id, current_user.id),
    )
    return [memory_response(item) for item in records]


@router.patch("/{memory_id}", response_model=MemoryResponse)
async def update_memory(
    memory_id: str,
    payload: MemoryUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    item = await MemoryService(db).update_memory(
        memory_id,
        user_id=current_user.id,
        content=payload.content,
        metadata=payload.metadata,
    )
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found or update blocked")
    return memory_response(item)


@router.delete("/{memory_id}", status_code=204)
async def delete_memory(
    memory_id: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    ok = await MemoryService(db).delete_memory(memory_id, user_id=current_user.id)
    if not ok:
        raise HTTPException(status_code=404, detail="Memory not found")
