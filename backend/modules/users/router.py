from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_current_user
from backend.api.deps.db import get_db
from backend.modules.audit.repository import AuditRepository
from backend.modules.identity_access.models import User
from backend.modules.users.schemas import (
    PasswordChangeRequest,
    SessionResponse,
    UserDirectoryResponse,
    UserProfileResponse,
    UserProfileUpdate,
)
from backend.modules.users.service import UsersService

router = APIRouter()


@router.get("/me", response_model=UserProfileResponse)
async def get_me(current_user: User = Depends(get_current_user)):
    return UserProfileResponse(
        id=current_user.id,
        email=current_user.email,
        full_name=current_user.full_name,
        is_verified=current_user.is_verified,
        mfa_enabled=current_user.mfa_enabled,
    )


@router.get("/directory", response_model=list[UserDirectoryResponse])
async def list_directory(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_current_user),
):
    service = UsersService(db)
    users = await service.list_directory()
    return [
        UserDirectoryResponse(
            id=user.id,
            email=user.email,
            full_name=user.full_name,
        )
        for user in users
    ]


@router.patch("/me", response_model=UserProfileResponse)
async def update_me(
    payload: UserProfileUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = UsersService(db)
    updated = await service.update_profile(current_user, payload.full_name)
    return UserProfileResponse(
        id=updated.id,
        email=updated.email,
        full_name=updated.full_name,
        is_verified=updated.is_verified,
        mfa_enabled=updated.mfa_enabled,
    )


@router.patch("/me/password", status_code=204)
async def change_password(
    payload: PasswordChangeRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = UsersService(db)
    await service.change_password(current_user, payload.current_password, payload.new_password)
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        action="user.password_changed",
        user_id=current_user.id,
        resource_type="user",
        resource_id=current_user.id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()


@router.get("/me/sessions", response_model=list[SessionResponse])
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = UsersService(db)
    sessions = await service.list_sessions(current_user)
    return [
        SessionResponse(id=s.id, created_at=s.created_at, expires_at=s.expires_at)
        for s in sessions
    ]


@router.delete("/me/sessions/{session_id}", status_code=204)
async def revoke_session(
    session_id: str,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    service = UsersService(db)
    await service.revoke_session(current_user, session_id)
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        action="user.session_revoked",
        user_id=current_user.id,
        resource_type="refresh_session",
        resource_id=session_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    await db.commit()
