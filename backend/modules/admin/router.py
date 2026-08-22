from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse, PlainTextResponse
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.admin import get_admin_user
from backend.core.pagination import build_cursor_page, fetch_limit, token_from_created_at_id
from backend.db.session import get_db
from backend.modules.admin.schemas import (
    AdminUserListResponse,
    AdminUserResponse,
    AdminUserStatusUpdate,
    AuditLogListResponse,
    AuditLogResponse,
    IdentityProviderCreateRequest,
    IdentityProviderResponse,
    IdentityProviderUpdateRequest,
    MetricsResponse,
    SecurityPostureFinding,
    SecurityPostureReportResponse,
    SecurityPostureSummary,
)
from backend.modules.admin.security_posture import run_security_posture_audit
from backend.modules.audit.export_service import AuditExportService, audit_log_to_dict
from backend.modules.audit.repository import AuditRepository
from backend.modules.identity_access.models import IdentityProvider, User
from backend.modules.identity_access.repository import IdentityRepository
from backend.modules.notifications.models import Notification

router = APIRouter()


def _user_to_response(user: User) -> AdminUserResponse:
    roles = ["user"]
    if user.is_admin:
        roles.append("admin")

    return AdminUserResponse(
        id=user.id,
        email=user.email,
        full_name=user.full_name,
        roles=roles,
        is_active=user.is_active,
        is_verified=user.is_verified,
        is_admin=user.is_admin,
        mfa_enabled=user.mfa_enabled,
        created_at=user.created_at,
    )


@router.get("/users", response_model=AdminUserListResponse)
async def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    search: str | None = Query(default=None, min_length=1),
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    filters = []
    if search:
        search_term = f"%{search.strip()}%"
        filters.append(
            or_(
                User.email.ilike(search_term),
                User.full_name.ilike(search_term),
            )
        )

    total_query = select(func.count()).select_from(User)
    data_query = select(User).order_by(User.created_at.desc())

    if filters:
        total_query = total_query.where(*filters)
        data_query = data_query.where(*filters)

    total = await db.scalar(total_query)
    result = await db.execute(data_query.offset((page - 1) * page_size).limit(page_size))

    return AdminUserListResponse(
        items=[_user_to_response(user) for user in result.scalars().all()],
        total=total or 0,
        page=page,
        page_size=page_size,
    )


@router.get("/users/{user_id}", response_model=AdminUserResponse)
async def get_user(
    user_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    repo = IdentityRepository(db)
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return _user_to_response(user)


@router.patch("/users/{user_id}/status", response_model=AdminUserResponse)
async def update_user_status(
    user_id: str,
    payload: AdminUserStatusUpdate,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    if user_id == admin.id:
        raise HTTPException(status_code=400, detail="Cannot change your own status")
    repo = IdentityRepository(db)
    user = await repo.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.is_active = payload.is_active
    audit_repo = AuditRepository(db)
    await audit_repo.log(
        action="admin.update_user_status",
        user_id=admin.id,
        resource_type="user",
        resource_id=user.id,
        metadata={"is_active": payload.is_active},
    )
    await db.commit()
    return _user_to_response(user)


@router.get("/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    limit: int = Query(default=50, ge=1, le=200),
    cursor_created_at: datetime | None = Query(default=None),
    cursor_id: str | None = Query(default=None),
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    workspace_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    logs, total = await AuditExportService(db).list_filtered(
        limit=fetch_limit(limit),
        cursor_created_at=cursor_created_at,
        cursor_id=cursor_id,
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        workspace_id=workspace_id,
    )
    page, next_cursor = build_cursor_page(
        logs,
        limit,
        token_from_row=token_from_created_at_id,
    )
    return AuditLogListResponse(
        items=[AuditLogResponse(**audit_log_to_dict(log)) for log in page],
        total=total,
        next_cursor=next_cursor,
    )


@router.get("/audit-logs/export")
async def export_audit_logs(
    format: str = Query(default="ndjson", pattern="^(ndjson|csv)$"),
    action: str | None = None,
    user_id: str | None = None,
    resource_type: str | None = None,
    workspace_id: str | None = None,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    rows = await AuditExportService(db).export_rows(
        action=action,
        user_id=user_id,
        resource_type=resource_type,
        workspace_id=workspace_id,
    )
    await AuditRepository(db).log(
        "admin.audit_export",
        user_id=admin.id,
        metadata={"format": format, "row_count": len(rows)},
    )
    await db.commit()
    stamp = datetime.now(UTC).strftime("%Y%m%dT%H%M%SZ")
    if format == "csv":
        payload = AuditExportService.to_csv(rows)
        return PlainTextResponse(
            content=payload,
            media_type="text/csv",
            headers={"Content-Disposition": f'attachment; filename="audit-export-{stamp}.csv"'},
        )
    payload = AuditExportService.to_ndjson(rows)
    return PlainTextResponse(
        content=payload,
        media_type="application/x-ndjson",
        headers={"Content-Disposition": f'attachment; filename="audit-export-{stamp}.ndjson"'},
    )


def _identity_provider_response(row: IdentityProvider) -> IdentityProviderResponse:
    return IdentityProviderResponse(
        id=row.id,
        slug=row.slug,
        name=row.name,
        provider_type=row.provider_type,
        issuer=row.issuer,
        client_id=row.client_id,
        scopes=list(row.scopes_json or []),
        domain_allowlist=list(row.domain_allowlist_json or []),
        enabled=row.enabled,
        enforce_sso=row.enforce_sso,
        has_client_secret=bool(row.secrets_ref),
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


@router.get("/identity-providers", response_model=list[IdentityProviderResponse])
async def list_identity_providers(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    result = await db.execute(select(IdentityProvider).order_by(IdentityProvider.name.asc()))
    return [_identity_provider_response(row) for row in result.scalars().all()]


@router.post("/identity-providers", response_model=IdentityProviderResponse, status_code=201)
async def create_identity_provider(
    payload: IdentityProviderCreateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from uuid import uuid4

    from backend.modules.identity_access.sso_service import SsoService

    existing = await db.execute(
        select(IdentityProvider).where(IdentityProvider.slug == payload.slug)
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=409, detail="identity provider slug already exists")
    row = IdentityProvider(
        id=str(uuid4()),
        slug=payload.slug.strip().lower(),
        name=payload.name.strip(),
        provider_type=payload.provider_type,
        issuer=payload.issuer.strip().rstrip("/"),
        client_id=payload.client_id.strip(),
        secrets_ref=SsoService.encrypt_client_secret(payload.client_secret),
        scopes_json=list(payload.scopes),
        domain_allowlist_json=[item.lower() for item in payload.domain_allowlist],
        enabled=payload.enabled,
        enforce_sso=payload.enforce_sso,
    )
    db.add(row)
    await AuditRepository(db).log(
        "admin.identity_provider_create",
        user_id=admin.id,
        resource_type="identity_provider",
        resource_id=row.id,
        metadata={"slug": row.slug},
    )
    await db.commit()
    await db.refresh(row)
    return _identity_provider_response(row)


@router.patch("/identity-providers/{provider_id}", response_model=IdentityProviderResponse)
async def update_identity_provider(
    provider_id: str,
    payload: IdentityProviderUpdateRequest,
    db: AsyncSession = Depends(get_db),
    admin: User = Depends(get_admin_user),
):
    from backend.modules.identity_access.sso_service import SsoService

    row = await db.get(IdentityProvider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="identity provider not found")
    if payload.name is not None:
        row.name = payload.name.strip()
    if payload.issuer is not None:
        row.issuer = payload.issuer.strip().rstrip("/")
    if payload.client_id is not None:
        row.client_id = payload.client_id.strip()
    if payload.client_secret is not None and payload.client_secret.strip():
        row.secrets_ref = SsoService.encrypt_client_secret(payload.client_secret)
    if payload.scopes is not None:
        row.scopes_json = list(payload.scopes)
    if payload.domain_allowlist is not None:
        row.domain_allowlist_json = [item.lower() for item in payload.domain_allowlist]
    if payload.enabled is not None:
        row.enabled = payload.enabled
    if payload.enforce_sso is not None:
        row.enforce_sso = payload.enforce_sso
    row.updated_at = datetime.now(UTC)
    await AuditRepository(db).log(
        "admin.identity_provider_update",
        user_id=admin.id,
        resource_type="identity_provider",
        resource_id=row.id,
        metadata={"slug": row.slug},
    )
    await db.commit()
    await db.refresh(row)
    return _identity_provider_response(row)


@router.post("/identity-providers/{provider_id}/test")
async def test_identity_provider(
    provider_id: str,
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    from backend.modules.identity_access.sso_service import SsoService

    row = await db.get(IdentityProvider, provider_id)
    if row is None:
        raise HTTPException(status_code=404, detail="identity provider not found")
    return await SsoService(db).test_provider(row)


@router.get("/metrics", response_model=MetricsResponse)
async def get_metrics(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    total = await db.scalar(select(func.count()).select_from(User))
    verified = await db.scalar(
        select(func.count()).select_from(User).where(User.is_verified.is_(True))
    )
    active = await db.scalar(select(func.count()).select_from(User).where(User.is_active.is_(True)))
    notifs = await db.scalar(select(func.count()).select_from(Notification))

    return MetricsResponse(
        total_users=total or 0,
        verified_users=verified or 0,
        active_users=active or 0,
        total_notifications=notifs or 0,
    )


def _posture_to_response(report) -> SecurityPostureReportResponse:
    summary = report.summary
    return SecurityPostureReportResponse(
        generated_at=report.generated_at,
        environment=report.environment,
        summary=SecurityPostureSummary(
            total=summary.get("total", 0),
            critical=summary.get("critical", 0),
            high=summary.get("high", 0),
            medium=summary.get("medium", 0),
            low=summary.get("low", 0),
            info=summary.get("info", 0),
        ),
        findings=[SecurityPostureFinding(**item.to_dict()) for item in report.findings],
    )


@router.get("/security-posture", response_model=SecurityPostureReportResponse)
async def get_security_posture(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    report = await run_security_posture_audit(db)
    return _posture_to_response(report)


@router.get("/security-posture/export")
async def export_security_posture(
    db: AsyncSession = Depends(get_db),
    _: User = Depends(get_admin_user),
):
    report = await run_security_posture_audit(db)
    payload = report.to_dict()
    filename = f"security-posture-{report.generated_at.strftime('%Y%m%dT%H%M%SZ')}.json"
    return JSONResponse(
        content=payload,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
