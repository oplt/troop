"""Google Calendar OAuth and Calendar API operations."""

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
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

CALENDAR_API_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_REVOKE_URL = "https://oauth2.googleapis.com/revoke"
GOOGLE_AUTHORIZE_URL = "https://accounts.google.com/o/oauth2/v2/auth"
GOOGLE_CALENDAR_SCOPES = (
    "openid",
    "email",
    "https://www.googleapis.com/auth/calendar.readonly",
    "https://www.googleapis.com/auth/calendar.events",
)


class GoogleCalendarAPIError(RuntimeError):
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


def _calendar_id(arguments: dict[str, Any]) -> str:
    return str(arguments.get("calendar_id") or "primary")


def _google_event_time(value: str, timezone: str) -> dict[str, str]:
    if "T" in value:
        return {"dateTime": value, "timeZone": timezone}
    return {"date": value}


def _google_event_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    timezone = str(arguments.get("timezone") or arguments.get("time_zone") or "UTC")
    payload: dict[str, Any] = {
        "summary": str(arguments.get("subject") or arguments.get("summary") or ""),
        "description": str(arguments.get("body") or arguments.get("description") or ""),
        "location": str(arguments.get("location") or ""),
        "start": _google_event_time(str(arguments.get("start_at") or arguments.get("start") or ""), timezone),
        "end": _google_event_time(str(arguments.get("end_at") or arguments.get("end") or ""), timezone),
    }
    attendees = arguments.get("attendees") or []
    if attendees:
        payload["attendees"] = [
            {"email": item.get("email") if isinstance(item, dict) else str(item)}
            for item in attendees
            if (item.get("email") if isinstance(item, dict) else item)
        ]
    return payload


class GoogleCalendarOAuthService:
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
        redirect_uri = (
            settings.GOOGLE_CALENDAR_OAUTH_REDIRECT_URI or settings.GOOGLE_OAUTH_REDIRECT_URI
        )
        if not settings.GOOGLE_CLIENT_ID or not redirect_uri or not settings.GOOGLE_CLIENT_SECRET:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {"code": "google_calendar_not_configured", "detail": "Google Calendar OAuth is not configured"},
            )
        requested = list(dict.fromkeys(scopes or GOOGLE_CALENDAR_SCOPES))
        state = secrets.token_urlsafe(32)
        verifier = secrets.token_urlsafe(64)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="google_calendar",
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
        redirect_uri = (
            settings.GOOGLE_CALENDAR_OAUTH_REDIRECT_URI or settings.GOOGLE_OAUTH_REDIRECT_URI
        )
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "google_calendar",
                ConnectorOAuthState.state_hash == state_hash,
            )
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if (
            oauth_state is None
            or oauth_state.consumed_at is not None
            or oauth_state.expires_at <= _utcnow()
        ):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        verifier = decrypt_secret(oauth_state.encrypted_code_verifier)
        if not verifier:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "OAuth verifier unavailable")
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
        if not token.get("access_token") or not token.get("refresh_token"):
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Google did not return refresh token")
        definition = await self._definition()
        expires_at = _utcnow() + timedelta(seconds=max(0, int(token.get("expires_in") or 0)))
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Google Calendar",
            status="active",
            config_json={
                "token_expires_at": expires_at.isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": token["access_token"],
                        "refresh_token": token["refresh_token"],
                    }
                )
            ),
            metadata_json={"provider": "google_calendar", "connection_state": "connected"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await self.db.flush()
        adapter = GoogleCalendarAdapter(self.db, installation)
        calendar_list = await adapter.request("GET", "/users/me/calendarList/primary")
        email = str(calendar_list.get("id") or "")
        installation.name = email or "Google Calendar"
        installation.metadata_json = {
            **installation.metadata_json,
            "email_address": email,
            "calendar_id": "primary",
        }
        await AuditRepository(self.db).log(
            "connector.google_calendar.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "google_calendar")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="google_calendar",
                name="Google Calendar",
                description="Native Google Calendar OAuth connector",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class GoogleCalendarAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> GoogleCalendarAdapter:
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
                ConnectorDefinition.slug == "google_calendar",
            )
        )
        row = result.first()
        if row is None:
            raise GoogleCalendarAPIError("Authorized Google Calendar installation not found")
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
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise GoogleCalendarAPIError("Google Calendar refresh token unavailable")
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
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise GoogleCalendarAPIError("Google Calendar token refresh rejected")
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
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        async with managed_http_client("google-calendar", base_url=CALENDAR_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code == 401:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
        if response.status_code >= 400:
            raise GoogleCalendarAPIError(
                "Google Calendar API request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        calendar_id = _calendar_id(arguments)
        if operation == "google_calendar.list_events":
            return await self.request(
                "GET",
                f"/calendars/{calendar_id}/events",
                params={
                    "timeMin": str(arguments.get("time_min") or ""),
                    "timeMax": str(arguments.get("time_max") or ""),
                    "maxResults": min(max(int(arguments.get("limit") or 25), 1), 250),
                    "singleEvents": "true",
                    "orderBy": "startTime",
                },
            )
        if operation == "google_calendar.get_event":
            return await self.request(
                "GET",
                f"/calendars/{calendar_id}/events/{arguments['event_id']}",
            )
        if operation == "google_calendar.get_availability":
            return await self.request(
                "POST",
                "/freeBusy",
                json_payload={
                    "timeMin": str(arguments.get("time_min") or ""),
                    "timeMax": str(arguments.get("time_max") or ""),
                    "timeZone": str(arguments.get("timezone") or "UTC"),
                    "items": [
                        {
                            "id": str(
                                item.get("calendar_id")
                                if isinstance(item, dict)
                                else item or calendar_id
                            )
                        }
                        for item in (arguments.get("calendars") or [{"calendar_id": calendar_id}])
                    ],
                },
            )
        if operation == "google_calendar.create_event":
            return await self.request(
                "POST",
                f"/calendars/{calendar_id}/events",
                json_payload=_google_event_payload(arguments),
            )
        if operation == "google_calendar.update_event":
            return await self.request(
                "PUT",
                f"/calendars/{calendar_id}/events/{arguments['event_id']}",
                json_payload=_google_event_payload(arguments),
            )
        if operation == "google_calendar.cancel_event":
            await self.request(
                "DELETE",
                f"/calendars/{calendar_id}/events/{arguments['event_id']}",
            )
            return {"event_id": str(arguments["event_id"]), "status": "cancelled"}
        raise GoogleCalendarAPIError(f"Unsupported Google Calendar operation: {operation}")

    async def revoke(self) -> None:
        config = resolve_installation_config(self.installation)
        token = str(config.get("refresh_token") or config.get("access_token") or "")
        if token:
            async with managed_http_client("google-oauth") as client:
                await client.post(
                    GOOGLE_REVOKE_URL,
                    data={"token": token},
                    headers=external_headers(),
                )
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
