from fastapi import APIRouter, Cookie, Depends, HTTPException, Query, Request, Response
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.api.deps.workspace import get_session_workspace_context
from backend.core.config import settings
from backend.core.logging import get_logger
from backend.core.rate_limit import (
    auth_rate_limit_key,
    check_rate_limit,
    clear_rate_limit,
    enforce_rate_limit,
    increment_rate_limit,
)
from backend.core.security import create_access_token, generate_csrf_token
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.identity_access.schemas import (
    AuthSessionResponse,
    AuthUserResponse,
    ForgotPasswordRequest,
    GenericMessageResponse,
    MfaDisableRequest,
    MfaEnableResponse,
    MfaVerifyRequest,
    ResendVerificationRequest,
    ResetPasswordRequest,
    SignInRequest,
    SignUpRequest,
    VerifyEmailRequest,
    WorkspaceContextResponse,
    WorkspaceListResponse,
)
from backend.modules.identity_access.service import IdentityService
from backend.modules.identity_access.workspace_authorization import WorkspaceAuthorizationService
from backend.modules.identity_access.workspace_context import WorkspaceContext

router = APIRouter()
logger = get_logger("backend.auth")

_REFRESH_COOKIE_MAX_AGE = 60 * 60 * 24 * settings.REFRESH_TOKEN_EXPIRE_DAYS
_ACCESS_COOKIE_MAX_AGE = 60 * settings.ACCESS_TOKEN_EXPIRE_MINUTES


def _cookie_kwargs() -> dict:
    return {
        "secure": settings.COOKIE_SECURE,
        "samesite": settings.COOKIE_SAMESITE,
        "domain": settings.COOKIE_DOMAIN,
    }


def _delete_cookie(response: Response, key: str, path: str) -> None:
    response.delete_cookie(
        key,
        path=path,
        domain=settings.COOKIE_DOMAIN,
        secure=settings.COOKIE_SECURE,
        samesite=settings.COOKIE_SAMESITE,
    )


def _clear_cookie_variants(response: Response, key: str, paths: tuple[str, ...]) -> None:
    for path in paths:
        _delete_cookie(response, key, path)


def _set_refresh_cookie(response: Response, token: str) -> None:
    _clear_cookie_variants(response, settings.REFRESH_COOKIE_NAME, ("/", "/api/v1"))
    response.set_cookie(
        key=settings.REFRESH_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path="/api/v1/auth",
        **_cookie_kwargs(),
    )


def _set_access_cookie(response: Response, token: str) -> None:
    _clear_cookie_variants(
        response,
        settings.ACCESS_COOKIE_NAME,
        ("/api/v1", "/api/v1/auth"),
    )
    response.set_cookie(
        key=settings.ACCESS_COOKIE_NAME,
        value=token,
        httponly=True,
        max_age=_ACCESS_COOKIE_MAX_AGE,
        path="/",
        **_cookie_kwargs(),
    )


def _set_csrf_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=token,
        httponly=False,
        max_age=_REFRESH_COOKIE_MAX_AGE,
        path="/",
        **_cookie_kwargs(),
    )


def _clear_auth_cookies(response: Response) -> None:
    paths = ("/", "/api/v1", "/api/v1/auth")
    _clear_cookie_variants(response, settings.ACCESS_COOKIE_NAME, paths)
    _clear_cookie_variants(response, settings.REFRESH_COOKIE_NAME, paths)
    _clear_cookie_variants(response, settings.CSRF_COOKIE_NAME, paths)


def _build_user(
    user: User,
    *,
    workspace_ctx: WorkspaceContext | None = None,
) -> AuthUserResponse:
    active_workspace = None
    if workspace_ctx is not None:
        active_workspace = _build_workspace_context(workspace_ctx)
    return AuthUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        mfa_enabled=user.mfa_enabled,
        active_workspace=active_workspace,
    )


def _build_workspace_context(ctx: WorkspaceContext) -> WorkspaceContextResponse:
    return WorkspaceContextResponse(
        id=ctx.workspace.id,
        name=ctx.workspace.name,
        slug=ctx.workspace.slug,
        role=ctx.primary_role,
        is_default=ctx.workspace.is_default,
    )


# ------------------------------------------------------------------ core auth


@router.post("/sign-up", response_model=GenericMessageResponse, status_code=202)
async def sign_up(
    payload: SignUpRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=(
            f"rate_limit:signup:"
            f"{request.client.host if request.client else 'unknown'}:{payload.email}"
        ),
        max_attempts=5,
        window_seconds=3600,
    )
    service = IdentityService(db)
    await service.sign_up(
        payload.email,
        payload.password,
        payload.full_name,
        payload.admin_invite_code,
    )
    detail = (
        "If the account can be created, a verification email will be sent shortly."
        if settings.REQUIRE_EMAIL_VERIFICATION
        else "If the account can be created, you can sign in shortly."
    )
    return GenericMessageResponse(detail=detail)


@router.post("/sign-in", response_model=AuthSessionResponse)
async def sign_in(
    payload: SignInRequest,
    request: Request,
    response: Response,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=auth_rate_limit_key(request, payload.email),
        max_attempts=10,
        window_seconds=60,
    )
    failure_key = (
        f"rate_limit:auth_fail:"
        f"{request.client.host if request.client else 'unknown'}:{payload.email}"
    )
    await enforce_rate_limit(failure_key, settings.AUTH_FAILURE_LIMIT)
    service = IdentityService(db)
    try:
        result = await service.sign_in(payload.email, payload.password, payload.mfa_code)
    except HTTPException as exc:
        if exc.status_code in {401, 403}:
            await increment_rate_limit(failure_key, settings.AUTH_FAILURE_WINDOW_SECONDS)
            logger.warning(
                "authentication_failed email=%s ip=%s status=%s",
                payload.email,
                request.client.host if request.client else "unknown",
                exc.status_code,
            )
        raise

    await clear_rate_limit(failure_key)
    access_token = create_access_token(result["user"].id, result["session_id"])
    csrf_token = generate_csrf_token()
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, result["refresh_token"])
    _set_csrf_cookie(response, csrf_token)
    from backend.modules.audit.repository import AuditRepository

    await AuditRepository(db).log(
        "auth.sign_in",
        user_id=result["user"].id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        metadata={"method": "password"},
    )
    await db.commit()
    workspace_ctx = await WorkspaceAuthorizationService(db).resolve_active_workspace(
        result["user"]
    )
    return AuthSessionResponse(user=_build_user(result["user"], workspace_ctx=workspace_ctx))


@router.post("/refresh", response_model=AuthSessionResponse)
async def refresh(
    response: Response,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    if not refresh_token:
        raise HTTPException(status_code=401, detail="Missing refresh token")
    service = IdentityService(db)
    result = await service.refresh(refresh_token)
    access_token = create_access_token(result["user"].id, result["session_id"])
    csrf_token = generate_csrf_token()
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, result["refresh_token"])
    _set_csrf_cookie(response, csrf_token)
    workspace_ctx = await WorkspaceAuthorizationService(db).resolve_active_workspace(
        result["user"]
    )
    return AuthSessionResponse(user=_build_user(result["user"], workspace_ctx=workspace_ctx))


@router.post("/logout", status_code=204)
async def logout(
    response: Response,
    request: Request,
    refresh_token: str | None = Cookie(default=None, alias=settings.REFRESH_COOKIE_NAME),
    db: AsyncSession = Depends(get_db),
):
    user_id: str | None = None
    if refresh_token:
        from backend.core.security import hash_refresh_token
        from backend.modules.audit.repository import AuditRepository
        from backend.modules.identity_access.repository import IdentityRepository

        repo = IdentityRepository(db)
        session = await repo.get_refresh_session_by_hash(hash_refresh_token(refresh_token))
        if session:
            user_id = session.user_id
        service = IdentityService(db)
        await service.logout(refresh_token)
        if user_id:
            await AuditRepository(db).log(
                "auth.sign_out",
                user_id=user_id,
                ip_address=request.client.host if request.client else None,
                user_agent=request.headers.get("user-agent"),
            )
            await db.commit()
    _clear_auth_cookies(response)


# ------------------------------------------------------------------ enterprise SSO (ENT-001)


@router.get("/sso/providers")
async def list_sso_providers(db: AsyncSession = Depends(get_db)) -> list[dict]:
    from backend.modules.identity_access.sso_service import SsoService

    return await SsoService(db).list_public_providers()


@router.get("/sso/{provider_slug}/authorize")
async def start_sso_authorize(
    provider_slug: str,
    redirect_after: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    from backend.modules.identity_access.sso_service import SsoService

    url = await SsoService(db).build_authorize_url(provider_slug, redirect_after=redirect_after)
    return RedirectResponse(url=url, status_code=302)


@router.get("/sso/callback")
async def sso_callback(
    request: Request,
    response: Response,
    code: str | None = None,
    state: str | None = None,
    db: AsyncSession = Depends(get_db),
):
    if not code or not state:
        raise HTTPException(status_code=400, detail="missing OIDC callback parameters")
    from backend.modules.identity_access.sso_service import SsoService

    service = SsoService(db)
    result = await service.handle_callback(
        code=code,
        state=state,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )
    access_token = create_access_token(result["user"].id, result["session_id"])
    csrf_token = generate_csrf_token()
    _set_access_cookie(response, access_token)
    _set_refresh_cookie(response, result["refresh_token"])
    _set_csrf_cookie(response, csrf_token)
    redirect_target = str(result.get("redirect_after") or settings.FRONTEND_URL)
    return RedirectResponse(url=redirect_target, status_code=302)


@router.get("/me", response_model=AuthUserResponse)
async def me(
    current_user: User = Depends(get_authenticated_user),
    workspace_ctx: WorkspaceContext = Depends(get_session_workspace_context),
):
    return _build_user(current_user, workspace_ctx=workspace_ctx)


@router.get("/workspaces", response_model=WorkspaceListResponse)
async def list_workspaces(
    current_user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
):
    auth = WorkspaceAuthorizationService(db)
    memberships = await auth.list_accessible_workspaces(current_user)
    return WorkspaceListResponse(
        items=[
            WorkspaceContextResponse(
                id=workspace.id,
                name=workspace.name,
                slug=workspace.slug,
                role=membership.role,
                is_default=workspace.is_default,
            )
            for workspace, membership in memberships
        ]
    )


# ------------------------------------------------------------------ email verification


@router.post("/verify-email", status_code=204)
async def verify_email(
    payload: VerifyEmailRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=f"rate_limit:verify:{request.client.host if request.client else 'unknown'}",
        max_attempts=10,
        window_seconds=3600,
    )
    service = IdentityService(db)
    await service.verify_email(payload.token)


@router.post("/resend-verification", status_code=204)
async def resend_verification(
    payload: ResendVerificationRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=f"rate_limit:resend:{request.client.host if request.client else 'unknown'}",
        max_attempts=3,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.resend_verification(payload.email)


# ------------------------------------------------------------------ password reset


@router.post("/forgot-password", status_code=204)
async def forgot_password(
    payload: ForgotPasswordRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    await check_rate_limit(
        key=(
            f"rate_limit:forgot:"
            f"{request.client.host if request.client else 'unknown'}:{payload.email}"
        ),
        max_attempts=5,
        window_seconds=300,
    )
    service = IdentityService(db)
    await service.forgot_password(payload.email)


@router.post("/reset-password", status_code=204)
async def reset_password(payload: ResetPasswordRequest, db: AsyncSession = Depends(get_db)):
    service = IdentityService(db)
    await service.reset_password(payload.token, payload.new_password)


# ------------------------------------------------------------------ MFA


@router.post("/mfa/enable", response_model=MfaEnableResponse)
async def mfa_enable(
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = IdentityService(db)
    return await service.mfa_enable(current_user)


@router.post("/mfa/verify", status_code=204)
async def mfa_verify(
    payload: MfaVerifyRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = IdentityService(db)
    await service.mfa_verify_enable(current_user, payload.code)


@router.post("/mfa/disable", status_code=204)
async def mfa_disable(
    payload: MfaDisableRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_authenticated_user),
):
    service = IdentityService(db)
    await service.mfa_disable(current_user, payload.code)
