"""Microsoft OneDrive/SharePoint OAuth and read-only Graph drive operations."""

from __future__ import annotations

import hashlib
import json
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from urllib.parse import urlencode
from uuid import uuid4

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import settings
from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.audit.repository import AuditRepository
from backend.modules.orchestration.security import encrypt_secret
from backend.modules.workforce.integrations.drive_acl import normalize_microsoft_drive_acl
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
MICROSOFT_DRIVE_AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_DRIVE_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_DRIVE_SCOPES = (
    "offline_access",
    "openid",
    "profile",
    "email",
    "Files.Read.All",
    "Sites.Read.All",
)


class MicrosoftDriveAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class MicrosoftDriveOAuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    def _client(self) -> tuple[str, str, str]:
        client_id = settings.MICROSOFT_DRIVE_CLIENT_ID or settings.OUTLOOK_CLIENT_ID
        client_secret = settings.MICROSOFT_DRIVE_CLIENT_SECRET or settings.OUTLOOK_CLIENT_SECRET
        redirect_uri = (
            settings.MICROSOFT_DRIVE_OAUTH_REDIRECT_URI
            or settings.OUTLOOK_OAUTH_REDIRECT_URI.replace("/outlook/", "/microsoft_drive/")
        )
        return client_id, client_secret, redirect_uri

    async def begin(
        self,
        owner_id: str,
        *,
        company_id: str | None = None,
        scopes: list[str] | None = None,
        redirect_after: str | None = None,
    ) -> dict[str, Any]:
        client_id, client_secret, redirect_uri = self._client()
        if not client_id or not client_secret or not redirect_uri:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Microsoft Drive OAuth is not configured"
            )
        requested = list(dict.fromkeys(scopes or MICROSOFT_DRIVE_SCOPES))
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="microsoft_drive",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("microsoft_drive"),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": client_id,
                "response_type": "code",
                "redirect_uri": redirect_uri,
                "response_mode": "query",
                "scope": " ".join(requested),
                "state": state,
            }
        )
        return {
            "authorization_url": f"{MICROSOFT_DRIVE_AUTHORIZE_URL}?{query}",
            "scopes": requested,
        }

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        client_id, client_secret, redirect_uri = self._client()
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "microsoft_drive",
                ConnectorOAuthState.state_hash == state_hash,
            )
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state is None or oauth_state.consumed_at or oauth_state.expires_at <= _utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        async with managed_http_client("microsoft-drive-oauth") as client:
            response = await client.post(
                MICROSOFT_DRIVE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "code": code,
                    "redirect_uri": redirect_uri,
                    "grant_type": "authorization_code",
                },
                headers=external_headers(),
            )
        token = response.json()
        if response.status_code >= 400 or "access_token" not in token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Microsoft Drive OAuth failed")
        definition = await self._definition()
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Microsoft Drive",
            status="active",
            config_json={
                "token_expires_at": (
                    _utcnow() + timedelta(seconds=int(token.get("expires_in") or 0))
                ).isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": token["access_token"],
                        "refresh_token": token.get("refresh_token") or "",
                    }
                )
            ),
            metadata_json={"provider": "microsoft_drive"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.microsoft_drive.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "microsoft_drive")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="microsoft_drive",
                name="Microsoft Drive",
                description="Read-only OneDrive/SharePoint connector for RAG sync",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class MicrosoftDriveAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> MicrosoftDriveAdapter:
        result = await db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(
                ConnectorDefinition,
                ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
            )
            .where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.slug == "microsoft_drive",
            )
        )
        row = result.first()
        if row is None:
            raise MicrosoftDriveAPIError("Authorized Microsoft Drive installation not found")
        return cls(db, row[0])

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        access_token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if access_token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return access_token
        refresh_token = str(config.get("refresh_token") or "")
        client_id = settings.MICROSOFT_DRIVE_CLIENT_ID or settings.OUTLOOK_CLIENT_ID
        client_secret = settings.MICROSOFT_DRIVE_CLIENT_SECRET or settings.OUTLOOK_CLIENT_SECRET
        if not refresh_token:
            raise MicrosoftDriveAPIError("Microsoft Drive refresh token unavailable")
        async with managed_http_client("microsoft-drive-oauth") as client:
            response = await client.post(
                MICROSOFT_DRIVE_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise MicrosoftDriveAPIError("Microsoft Drive token refresh rejected")
        token = response.json()
        access_token = str(token["access_token"])
        self.installation.secrets_ref = encrypt_secret(
            json.dumps(
                {
                    "access_token": access_token,
                    "refresh_token": token.get("refresh_token") or refresh_token,
                }
            )
        )
        public = dict(self.installation.config_json or {})
        public["token_expires_at"] = (
            _utcnow() + timedelta(seconds=int(token.get("expires_in") or 3600))
        ).isoformat()
        self.installation.config_json = public
        await self.db.flush()
        return access_token

    async def request(
        self,
        method: str,
        path: str,
        *,
        params: dict[str, Any] | None = None,
        raw: bool = False,
    ) -> dict[str, Any] | bytes:
        token = await self._access_token()
        async with managed_http_client("microsoft-graph", base_url=GRAPH_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise MicrosoftDriveAPIError(
                "Microsoft Drive Graph request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        if raw:
            return response.content
        return response.json() if response.content else {}

    def _drive_root(self, arguments: dict[str, Any]) -> str:
        drive_id = str(arguments.get("drive_id") or "")
        if drive_id:
            return f"/drives/{drive_id}/root"
        site_id = str(arguments.get("site_id") or "")
        if site_id:
            return f"/sites/{site_id}/drive/root"
        return "/me/drive/root"

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "microsoft_drive.search_files":
            root = self._drive_root(arguments)
            body = await self.request(
                "GET",
                f"{root}/search(q='{arguments.get('query', '')}')",
                params={"$top": min(max(int(arguments.get("limit") or 25), 1), 100)},
            )
            return body if isinstance(body, dict) else {}
        if operation == "microsoft_drive.get_file_metadata":
            item_id = str(arguments["file_id"])
            root = self._drive_root(arguments)
            body = await self.request(
                "GET",
                f"{root.replace('/root', '')}/items/{item_id}",
                params={"$expand": "permissions"},
            )
            if isinstance(body, dict):
                email = str((self.installation.metadata_json or {}).get("email_address") or "")
                body["acl_snapshot"] = normalize_microsoft_drive_acl(
                    file_body=body, owner_email=email
                )
            return body if isinstance(body, dict) else {}
        if operation == "microsoft_drive.get_file_content":
            item_id = str(arguments["file_id"])
            root = self._drive_root(arguments).replace("/root", "")
            raw = await self.request("GET", f"{root}/items/{item_id}/content", raw=True)
            meta = await self.execute("microsoft_drive.get_file_metadata", arguments)
            content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""
            return {"file_id": item_id, "content": content, "metadata": meta}
        if operation == "microsoft_drive.list_delta":
            root = self._drive_root(arguments)
            path = arguments.get("delta_link") or f"{root}/delta"
            if str(path).startswith("http"):
                async with managed_http_client("microsoft-graph") as client:
                    token = await self._access_token()
                    response = await client.get(
                        str(path),
                        headers=external_headers({"Authorization": f"Bearer {token}"}),
                    )
                if response.status_code >= 400:
                    raise MicrosoftDriveAPIError("Microsoft Drive delta request failed")
                return response.json()
            body = await self.request("GET", str(path))
            return body if isinstance(body, dict) else {}
        raise MicrosoftDriveAPIError(f"Unsupported Microsoft Drive operation: {operation}")

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
