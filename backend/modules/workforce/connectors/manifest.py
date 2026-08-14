"""Connector manifest schema — extension boundary for provider metadata."""

from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from backend.modules.workforce.action_metadata import ActionGovernanceMetadata


class AuthStrategyType(StrEnum):
    OAUTH2 = "oauth2"
    API_KEY = "api_key"
    BOT_TOKEN = "bot_token"
    SERVICE_ACCOUNT = "service_account"
    NONE = "none"


class OperationKind(StrEnum):
    TRIGGER = "trigger"
    SEARCH = "search"
    READ = "read"
    ACTION = "action"


class WebhookVerificationStrategy(StrEnum):
    NONE = "none"
    HMAC_SECRET = "hmac_secret"
    OIDC_JWT = "oidc_jwt"
    PROVIDER_SIGNATURE = "provider_signature"
    CLIENT_STATE = "client_state"


class ReauthorizationBehavior(StrEnum):
    MANUAL = "manual"
    AUTO_REFRESH = "auto_refresh"
    REVOKE_AND_RECONNECT = "revoke_and_reconnect"


class ConnectorScopeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope: str
    label: str
    description: str = ""
    required_for: list[str] = Field(default_factory=list)


class ConnectorAuthManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: AuthStrategyType
    scopes: list[ConnectorScopeManifest] = Field(default_factory=list)
    config_schema: dict[str, Any] = Field(default_factory=dict)
    reauthorization: ReauthorizationBehavior = ReauthorizationBehavior.AUTO_REFRESH
    pkce_required: bool = False


class RateLimitManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requests_per_minute: int | None = None
    burst: int | None = None
    scope: Literal["installation", "workspace", "provider"] = "installation"


class HealthProbeManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_slug: str | None = None
    interval_seconds: int = Field(default=3600, ge=60)
    timeout_seconds: int = Field(default=10, ge=1, le=120)


class WebhookManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    strategy: WebhookVerificationStrategy = WebhookVerificationStrategy.NONE
    verification_header: str | None = None
    dedupe_key_fields: list[str] = Field(default_factory=list)
    supports_registration: bool = False


class ConnectorOperationManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    slug: str
    name: str
    description: str = ""
    operation_kind: OperationKind
    input_schema: dict[str, Any] = Field(default_factory=dict)
    output_schema: dict[str, Any] = Field(default_factory=dict)
    risk_level: str = "low"
    requires_approval: bool = False
    required_scopes: list[str] = Field(default_factory=list)
    governance: ActionGovernanceMetadata | None = None
    rate_limit: RateLimitManifest | None = None
    parallel_safe: bool = False

    @property
    def idempotency_strategy(self) -> str:
        if self.governance is None:
            return "none"
        return self.governance.idempotency_strategy.value


class ConnectorManifest(BaseModel):
    """Canonical provider metadata consumed by registry, policy, and UI layers."""

    model_config = ConfigDict(extra="forbid")

    provider_slug: str
    version: str
    name: str
    description: str = ""
    provider_type: Literal["native", "mcp", "a2a"] = "native"
    auth: ConnectorAuthManifest
    triggers: list[ConnectorOperationManifest] = Field(default_factory=list)
    actions: list[ConnectorOperationManifest] = Field(default_factory=list)
    webhook: WebhookManifest | None = None
    health: HealthProbeManifest | None = None
    rate_limits: RateLimitManifest | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @model_validator(mode="after")
    def _validate_unique_operation_slugs(self) -> ConnectorManifest:
        slugs = [op.slug for op in self.all_operations()]
        if len(slugs) != len(set(slugs)):
            raise ValueError(f"duplicate operation slugs in manifest `{self.provider_slug}`")
        return self

    def all_operations(self) -> list[ConnectorOperationManifest]:
        return [*self.triggers, *self.actions]

    def get_operation(self, slug: str) -> ConnectorOperationManifest | None:
        for operation in self.all_operations():
            if operation.slug == slug:
                return operation
        return None

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")
