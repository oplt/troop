"""Connector provider runtime contract."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.modules.workforce.connectors.manifest import ConnectorManifest


@dataclass(frozen=True, slots=True)
class ConnectorAuthContext:
    owner_id: str
    company_id: str | None = None
    installation_id: str | None = None
    redirect_uri: str | None = None
    scopes: list[str] | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorAuthResult:
    status: str
    authorization_url: str | None = None
    installation_id: str | None = None
    expires_at: datetime | None = None
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorHealthResult:
    ok: bool
    status: str = "unknown"
    reauth_required: bool = False
    details: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorTriggerRegistration:
    trigger_slug: str
    subscription_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True, slots=True)
class ConnectorNormalizedEvent:
    event_type: str
    dedupe_key: str
    payload: dict[str, Any]
    occurred_at: datetime | None = None
    installation_id: str | None = None


@dataclass(frozen=True, slots=True)
class ConnectorActionResult:
    status: str
    output: dict[str, Any] = field(default_factory=dict)
    error: str | None = None
    retryable: bool = False
    provider_status_code: int | None = None


_PROVIDER_METHODS = (
    "authorize",
    "refresh",
    "health",
    "register_trigger",
    "unregister_trigger",
    "normalize_event",
    "execute_action",
)


@runtime_checkable
class ConnectorProvider(Protocol):
    """Runtime adapter contract for connector lifecycle and execution."""

    @property
    def manifest(self) -> ConnectorManifest: ...

    async def authorize(
        self,
        db: AsyncSession,
        context: ConnectorAuthContext,
    ) -> ConnectorAuthResult: ...

    async def refresh(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorAuthResult: ...

    async def health(
        self,
        db: AsyncSession,
        installation_id: str,
    ) -> ConnectorHealthResult: ...

    async def register_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        trigger_slug: str,
        config: dict[str, Any],
    ) -> ConnectorTriggerRegistration: ...

    async def unregister_trigger(
        self,
        db: AsyncSession,
        installation_id: str,
        subscription_id: str,
    ) -> None: ...

    async def normalize_event(
        self,
        raw_event: dict[str, Any],
        *,
        installation_id: str | None = None,
    ) -> ConnectorNormalizedEvent: ...

    async def execute_action(
        self,
        db: AsyncSession,
        installation_id: str,
        action_slug: str,
        arguments: dict[str, Any],
        context: dict[str, Any],
    ) -> ConnectorActionResult: ...


def provider_implements_contract(provider: object) -> bool:
    """Return True when ``provider`` exposes the canonical connector lifecycle."""
    if not isinstance(provider, ConnectorProvider):
        return False
    manifest = getattr(provider, "manifest", None)
    if manifest is None or not hasattr(manifest, "provider_slug"):
        return False
    for method_name in _PROVIDER_METHODS:
        method = getattr(provider, method_name, None)
        if not callable(method):
            return False
    return True
