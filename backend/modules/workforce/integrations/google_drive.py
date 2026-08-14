"""Google Drive OAuth and read-only Drive API operations."""

from __future__ import annotations

import base64
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
from backend.modules.orchestration.security import decrypt_secret, encrypt_secret
from backend.modules.workforce.integrations.drive_acl import normalize_google_drive_acl
from backend.modules.workforce.models import ConnectorDefinition, ConnectorInstallation, ConnectorOAuthState
from backend.modules.workforce.services.connector_service import resolve_installation_config

DRIVE_API_BASE = "https://www.googleapis.com/drive/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_DRIVE_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/drive.readonly",
)
_EXPORT_MIME = {
    "application/vnd.google-apps.document": "text/plain",
    "application/vnd.google-apps.spreadsheet": "text/csv",
    "application/vnd.google-apps.presentation": "text/plain",
}


class GoogleDriveAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _pkce_challenge(verifier: str) -> str:
    digest = hashlib.sha256(verifier.encode()).digest()
    return base64.urlsafe_b64encode(digest).decode().rstrip("=")


class GoogleDriveOAuthService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def begin(
        self,
        owner_id: str,
        *,
        company_id: str | None = None,
        scopes: list[str] | None = None,
        redirect_after: str | None = None,
    ) -> dict[str, Any]:
        redirect_uri = settings.GOOGLE_DRIVE_OAUTH_REDIRECT_URI or settings.GOOGLE_OAUTH_REDIRECT_URI
        if not settings.GOOGLE_CLIENT_ID or not redirect_uri or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Google Drive OAuth is not configured")
        requested = list(dict.fromkeys(scopes or GOOGLE_DRIVE_SCOPES))
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="google_drive",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret(verifier),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.GOOGLE_CLIENT_ID,
                "redirect_uri": redirect_uri,
                "response_type": "code",
                "scope": " ".join(requested),
                "state": state,
                "code_challenge": _pkce_challenge(verifier),
                "code_challenge_method": "S256",
                "access_type": "offline",
                "prompt": "consent",
            }
        )
        return {"authorization_url": f"{GOOGLE_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        redirect_uri = settings.GOOGLE_DRIVE_OAUTH_REDIRECT_URI or settings.GOOGLE_OAUTH_REDIRECT_URI
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(ConnectorOAuthState.provider == "google_drive", ConnectorOAuthState.state_hash == state_hash)
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state is None or oauth_state.consumed_at or oauth_state.expires_at <= _utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        verifier = decrypt_secret(oauth_state.encrypted_code_verifier)
        async with managed_http_client("google-oauth") as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "code": code,
                    "code_verifier": verifier,
                    "grant_type": "authorization_code",
                    "redirect_uri": redirect_uri,
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google OAuth exchange failed")
        token = response.json()
        if not token.get("refresh_token"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google did not return refresh token")
        definition = await self._definition()
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Google Drive",
            status="active",
            config_json={
                "token_expires_at": (
                    _utcnow() + timedelta(seconds=int(token.get("expires_in") or 0))
                ).isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
            },
            secrets_ref=encrypt_secret(
                json.dumps({"access_token": token["access_token"], "refresh_token": token["refresh_token"]})
            ),
            metadata_json={"provider": "google_drive"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.google_drive.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "google_drive")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="google_drive",
                name="Google Drive",
                description="Read-only Google Drive connector for RAG sync",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class GoogleDriveAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(cls, db: AsyncSession, *, owner_id: str, installation_id: str) -> GoogleDriveAdapter:
        result = await db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(ConnectorDefinition, ConnectorDefinition.id == ConnectorInstallation.connector_definition_id)
            .where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.slug == "google_drive",
            )
        )
        row = result.first()
        if row is None:
            raise GoogleDriveAPIError("Authorized Google Drive installation not found")
        return cls(db, row[0])

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        access_token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if access_token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return access_token
        refresh_token = str(config.get("refresh_token") or "")
        if not refresh_token:
            raise GoogleDriveAPIError("Google Drive refresh token unavailable")
        async with managed_http_client("google-oauth") as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.GOOGLE_CLIENT_ID,
                    "client_secret": settings.GOOGLE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise GoogleDriveAPIError("Google Drive token refresh rejected")
        token = response.json()
        access_token = str(token["access_token"])
        self.installation.secrets_ref = encrypt_secret(
            json.dumps({"access_token": access_token, "refresh_token": refresh_token})
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
        async with managed_http_client("google-drive", base_url=DRIVE_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise GoogleDriveAPIError(
                "Google Drive API request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        if raw:
            return response.content
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "google_drive.search_files":
            q_parts = ["trashed = false"]
            if arguments.get("folder_id"):
                q_parts.append(f"'{arguments['folder_id']}' in parents")
            if arguments.get("query"):
                q_parts.append(f"name contains '{arguments['query']}'")
            body = await self.request(
                "GET",
                "/files",
                params={
                    "q": " and ".join(q_parts),
                    "pageSize": min(max(int(arguments.get("limit") or 25), 1), 100),
                    "fields": "files(id,name,mimeType,modifiedTime,parents,webViewLink),nextPageToken",
                },
            )
            return body if isinstance(body, dict) else {}
        if operation == "google_drive.get_file_metadata":
            file_id = str(arguments["file_id"])
            body = await self.request(
                "GET",
                f"/files/{file_id}",
                params={"fields": "id,name,mimeType,modifiedTime,parents,owners,permissions,trashed,webViewLink"},
            )
            if isinstance(body, dict):
                body["acl_snapshot"] = normalize_google_drive_acl(file_body=body)
            return body if isinstance(body, dict) else {}
        if operation == "google_drive.get_file_content":
            meta = await self.execute("google_drive.get_file_metadata", {"file_id": arguments["file_id"]})
            mime = str(meta.get("mimeType") or "")
            export_mime = _EXPORT_MIME.get(mime)
            if export_mime:
                raw = await self.request(
                    "GET",
                    f"/files/{arguments['file_id']}/export",
                    params={"mimeType": export_mime},
                    raw=True,
                )
                content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""
            else:
                raw = await self.request(
                    "GET",
                    f"/files/{arguments['file_id']}",
                    params={"alt": "media"},
                    raw=True,
                )
                content = raw.decode("utf-8", errors="replace") if isinstance(raw, bytes) else ""
            return {"file_id": arguments["file_id"], "content": content, "metadata": meta}
        if operation == "google_drive.list_changes":
            params: dict[str, Any] = {
                "fields": "nextPageToken,newStartPageToken,changes(fileId,removed,file(id,name,mimeType,trashed,modifiedTime,parents))",
                "pageSize": 100,
            }
            if arguments.get("page_token"):
                params["pageToken"] = arguments["page_token"]
            body = await self.request("GET", "/changes", params=params)
            return body if isinstance(body, dict) else {}
        if operation == "google_drive.get_start_page_token":
            body = await self.request("GET", "/changes/startPageToken")
            return body if isinstance(body, dict) else {}
        raise GoogleDriveAPIError(f"Unsupported Google Drive operation: {operation}")

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
