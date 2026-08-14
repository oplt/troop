from datetime import datetime

from pydantic import BaseModel, EmailStr, Field

from backend.core.schemas import RequestModel


class AdminUserResponse(BaseModel):
    id: str
    email: EmailStr
    full_name: str | None
    roles: list[str]
    is_active: bool
    is_verified: bool
    is_admin: bool
    mfa_enabled: bool
    created_at: datetime


class AdminUserListResponse(BaseModel):
    items: list[AdminUserResponse]
    total: int
    page: int
    page_size: int


class AdminUserStatusUpdate(RequestModel):
    is_active: bool


class AuditLogResponse(BaseModel):
    id: str
    user_id: str | None
    workspace_id: str | None = None
    action: str
    resource_type: str | None
    resource_id: str | None
    ip_address: str | None
    created_at: datetime
    metadata: dict = {}


class AuditLogListResponse(BaseModel):
    items: list[AuditLogResponse]
    total: int
    page: int
    page_size: int


class IdentityProviderResponse(BaseModel):
    id: str
    slug: str
    name: str
    provider_type: str
    issuer: str
    client_id: str
    scopes: list[str]
    domain_allowlist: list[str]
    enabled: bool
    enforce_sso: bool
    has_client_secret: bool
    created_at: datetime
    updated_at: datetime


class IdentityProviderCreateRequest(RequestModel):
    slug: str
    name: str
    issuer: str
    client_id: str
    client_secret: str = ""
    provider_type: str = "oidc"
    scopes: list[str] = Field(default_factory=lambda: ["openid", "email", "profile"])
    domain_allowlist: list[str] = Field(default_factory=list)
    enabled: bool = False
    enforce_sso: bool = False


class IdentityProviderUpdateRequest(RequestModel):
    name: str | None = None
    issuer: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    scopes: list[str] | None = None
    domain_allowlist: list[str] | None = None
    enabled: bool | None = None
    enforce_sso: bool | None = None


class MetricsResponse(BaseModel):
    total_users: int
    verified_users: int
    active_users: int
    total_notifications: int


class SecurityPostureFinding(BaseModel):
    check_id: str
    severity: str
    title: str
    summary: str
    remediation: str
    remediation_url: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict = {}


class SecurityPostureSummary(BaseModel):
    total: int
    critical: int = 0
    high: int = 0
    medium: int = 0
    low: int = 0
    info: int = 0


class SecurityPostureReportResponse(BaseModel):
    generated_at: datetime
    environment: str
    summary: SecurityPostureSummary
    findings: list[SecurityPostureFinding]
