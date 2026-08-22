"""Microsoft Calendar OAuth and Graph calendar operations."""

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
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

GRAPH_API_BASE = "https://graph.microsoft.com/v1.0"
MICROSOFT_CALENDAR_AUTHORIZE_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/authorize"
MICROSOFT_CALENDAR_TOKEN_URL = "https://login.microsoftonline.com/common/oauth2/v2.0/token"
MICROSOFT_CALENDAR_SCOPES = (
    "offline_access",
    "openid",
    "profile",
    "email",
    "Calendars.Read",
    "Calendars.ReadWrite",
)


class MicrosoftCalendarAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _graph_attendees(attendees: Any) -> list[dict[str, Any]]:
    raw = attendees if isinstance(attendees, list) else ([attendees] if attendees else [])
    return [
        {
            "emailAddress": {
                "address": str(item.get("email") if isinstance(item, dict) else item),
                "name": str(item.get("name") if isinstance(item, dict) else ""),
            },
            "type": "required",
        }
        for item in raw
        if (item.get("email") if isinstance(item, dict) else item)
    ]


def _graph_event_payload(arguments: dict[str, Any]) -> dict[str, Any]:
    timezone = str(arguments.get("timezone") or arguments.get("time_zone") or "UTC")
    payload: dict[str, Any] = {
        "subject": str(arguments.get("subject") or arguments.get("summary") or ""),
        "body": {
            "contentType": "Text",
            "content": str(arguments.get("body") or arguments.get("description") or ""),
        },
        "location": {"displayName": str(arguments.get("location") or "")},
        "start": {
            "dateTime": str(arguments.get("start_at") or arguments.get("start") or ""),
            "timeZone": timezone,
        },
        "end": {
            "dateTime": str(arguments.get("end_at") or arguments.get("end") or ""),
            "timeZone": timezone,
        },
    }
    attendees = _graph_attendees(arguments.get("attendees"))
    if attendees:
        payload["attendees"] = attendees
    if arguments.get("is_online_meeting"):
        payload["isOnlineMeeting"] = True
        payload["onlineMeetingProvider"] = "teamsForBusiness"
    return payload


class MicrosoftCalendarOAuthService:
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
            settings.MICROSOFT_CALENDAR_OAUTH_REDIRECT_URI
            or settings.OUTLOOK_OAUTH_REDIRECT_URI.replace("/outlook/", "/microsoft_calendar/")
        )
        client_id = settings.MICROSOFT_CALENDAR_CLIENT_ID or settings.OUTLOOK_CLIENT_ID
        client_secret = settings.MICROSOFT_CALENDAR_CLIENT_SECRET or settings.OUTLOOK_CLIENT_SECRET
        if not client_id or not redirect_uri or not client_secret:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                {
                    "code": "microsoft_calendar_not_configured",
                    "detail": "Microsoft Calendar OAuth is not configured",
                },
            )
        requested = list(dict.fromkeys(scopes or MICROSOFT_CALENDAR_SCOPES))
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="microsoft_calendar",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("microsoft_calendar"),
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
            "authorization_url": f"{MICROSOFT_CALENDAR_AUTHORIZE_URL}?{query}",
            "scopes": requested,
        }

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        redirect_uri = (
            settings.MICROSOFT_CALENDAR_OAUTH_REDIRECT_URI
            or settings.OUTLOOK_OAUTH_REDIRECT_URI.replace("/outlook/", "/microsoft_calendar/")
        )
        client_id = settings.MICROSOFT_CALENDAR_CLIENT_ID or settings.OUTLOOK_CLIENT_ID
        client_secret = settings.MICROSOFT_CALENDAR_CLIENT_SECRET or settings.OUTLOOK_CLIENT_SECRET
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "microsoft_calendar",
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
        async with managed_http_client("microsoft-calendar-oauth") as client:
            response = await client.post(
                MICROSOFT_CALENDAR_TOKEN_URL,
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
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Microsoft Calendar OAuth failed")
        if not token.get("refresh_token"):
            raise HTTPException(
                status.HTTP_400_BAD_REQUEST, "Microsoft did not return refresh token"
            )
        definition = await self._definition()
        expires_at = _utcnow() + timedelta(seconds=max(0, int(token.get("expires_in") or 0)))
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Microsoft Calendar",
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
            metadata_json={"provider": "microsoft_calendar", "connection_state": "connected"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await self.db.flush()
        adapter = MicrosoftCalendarAdapter(self.db, installation)
        profile = await adapter.request("GET", "/me")
        email = str(profile.get("mail") or profile.get("userPrincipalName") or "")
        installation.name = email or "Microsoft Calendar"
        installation.metadata_json = {
            **installation.metadata_json,
            "email_address": email,
        }
        await AuditRepository(self.db).log(
            "connector.microsoft_calendar.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "microsoft_calendar")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="microsoft_calendar",
                name="Microsoft Calendar",
                description="Native Microsoft Calendar OAuth connector",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class MicrosoftCalendarAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> MicrosoftCalendarAdapter:
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
                ConnectorDefinition.slug == "microsoft_calendar",
            )
        )
        row = result.first()
        if row is None:
            raise MicrosoftCalendarAPIError("Authorized Microsoft Calendar installation not found")
        return cls(db, row[0])

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        access_token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if access_token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return access_token
        refresh_token = str(config.get("refresh_token") or "")
        client_id = settings.MICROSOFT_CALENDAR_CLIENT_ID or settings.OUTLOOK_CLIENT_ID
        client_secret = settings.MICROSOFT_CALENDAR_CLIENT_SECRET or settings.OUTLOOK_CLIENT_SECRET
        if not refresh_token:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise MicrosoftCalendarAPIError("Microsoft Calendar refresh token unavailable")
        async with managed_http_client("microsoft-calendar-oauth") as client:
            response = await client.post(
                MICROSOFT_CALENDAR_TOKEN_URL,
                data={
                    "client_id": client_id,
                    "client_secret": client_secret,
                    "refresh_token": refresh_token,
                    "grant_type": "refresh_token",
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            self.installation.status = "reauthorization_required"
            await self.db.flush()
            raise MicrosoftCalendarAPIError("Microsoft Calendar token refresh rejected")
        token = response.json()
        access_token = str(token["access_token"])
        new_refresh = str(token.get("refresh_token") or refresh_token)
        self.installation.secrets_ref = encrypt_secret(
            json.dumps({"access_token": access_token, "refresh_token": new_refresh})
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
        async with managed_http_client("microsoft-graph", base_url=GRAPH_API_BASE) as client:
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
            raise MicrosoftCalendarAPIError(
                "Microsoft Calendar Graph request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "microsoft_calendar.list_events":
            return await self.request(
                "GET",
                "/me/calendar/events",
                params={
                    "$filter": (
                        f"start/dateTime ge '{arguments.get('time_min')}' and end/dateTime le '{arguments.get('time_max')}'"
                        if arguments.get("time_min") and arguments.get("time_max")
                        else None
                    ),
                    "$top": min(max(int(arguments.get("limit") or 25), 1), 250),
                    "$orderby": "start/dateTime",
                },
            )
        if operation == "microsoft_calendar.get_event":
            return await self.request("GET", f"/me/events/{arguments['event_id']}")
        if operation == "microsoft_calendar.get_availability":
            schedules = [
                str(item.get("email") if isinstance(item, dict) else item)
                for item in (arguments.get("schedules") or [])
                if (item.get("email") if isinstance(item, dict) else item)
            ]
            if not schedules:
                email = str((self.installation.metadata_json or {}).get("email_address") or "")
                schedules = [email] if email else []
            return await self.request(
                "POST",
                "/me/calendar/getSchedule",
                json_payload={
                    "schedules": schedules,
                    "startTime": {
                        "dateTime": str(arguments.get("time_min") or ""),
                        "timeZone": str(arguments.get("timezone") or "UTC"),
                    },
                    "endTime": {
                        "dateTime": str(arguments.get("time_max") or ""),
                        "timeZone": str(arguments.get("timezone") or "UTC"),
                    },
                    "availabilityViewInterval": int(arguments.get("interval_minutes") or 30),
                },
            )
        if operation == "microsoft_calendar.create_event":
            return await self.request(
                "POST",
                "/me/events",
                json_payload=_graph_event_payload(arguments),
            )
        if operation == "microsoft_calendar.update_event":
            return await self.request(
                "PATCH",
                f"/me/events/{arguments['event_id']}",
                json_payload=_graph_event_payload(arguments),
            )
        if operation == "microsoft_calendar.cancel_event":
            await self.request("DELETE", f"/me/events/{arguments['event_id']}")
            return {"event_id": str(arguments["event_id"]), "status": "cancelled"}
        raise MicrosoftCalendarAPIError(f"Unsupported Microsoft Calendar operation: {operation}")

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
