"""HubSpot OAuth and CRM read/enrichment operations."""

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
from backend.modules.orchestration.execution.hitl.commit_authorization import (
    CommitAuthorizationError,
    authorize_and_claim_execution,
    build_idempotency_key,
    mark_execution_failed,
    mark_execution_sending,
    mark_execution_succeeded,
)
from backend.modules.orchestration.security import encrypt_secret
from backend.modules.workforce.integrations.crm_records import (
    HUBSPOT_CONTACT_UPDATE_ALLOWLIST,
    filter_allowlisted_fields,
    hubspot_crm_arguments_hash,
)
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

HUBSPOT_AUTHORIZE_URL = "https://app.hubspot.com/oauth/authorize"
HUBSPOT_TOKEN_URL = "https://api.hubapi.com/oauth/v1/token"
HUBSPOT_API_BASE = "https://api.hubapi.com"
HUBSPOT_SCOPES = (
    "oauth",
    "crm.objects.contacts.read",
    "crm.objects.contacts.write",
    "crm.objects.companies.read",
    "crm.objects.companies.write",
)


class HubSpotAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class HubSpotOAuthService:
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
        if not settings.HUBSPOT_CLIENT_ID or not settings.HUBSPOT_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "HubSpot OAuth is not configured"
            )
        requested = list(dict.fromkeys(scopes or HUBSPOT_SCOPES))
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="hubspot",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("hubspot"),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.HUBSPOT_CLIENT_ID,
                "redirect_uri": settings.HUBSPOT_OAUTH_REDIRECT_URI,
                "scope": " ".join(requested),
                "state": state,
            }
        )
        return {"authorization_url": f"{HUBSPOT_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "hubspot",
                ConnectorOAuthState.state_hash == state_hash,
            )
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state is None or oauth_state.consumed_at or oauth_state.expires_at <= _utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        async with managed_http_client("hubspot-oauth") as client:
            response = await client.post(
                HUBSPOT_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.HUBSPOT_CLIENT_ID,
                    "client_secret": settings.HUBSPOT_CLIENT_SECRET,
                    "redirect_uri": settings.HUBSPOT_OAUTH_REDIRECT_URI,
                    "code": code,
                },
                headers=external_headers(),
            )
        token = response.json()
        if response.status_code >= 400 or "access_token" not in token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "HubSpot OAuth exchange failed")
        definition = await self._definition()
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="HubSpot",
            status="active",
            config_json={
                "token_expires_at": (
                    _utcnow() + timedelta(seconds=int(token.get("expires_in") or 3600))
                ).isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
                "hub_id": token.get("hub_id"),
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": token["access_token"],
                        "refresh_token": token.get("refresh_token") or "",
                    }
                )
            ),
            metadata_json={"provider": "hubspot"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.hubspot.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "hubspot")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="hubspot",
                name="HubSpot",
                description="Read and enrich HubSpot CRM records with approval-gated writes",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class HubSpotAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> HubSpotAdapter:
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
                ConnectorDefinition.slug == "hubspot",
            )
        )
        row = result.first()
        if row is None:
            raise HubSpotAPIError("Authorized HubSpot installation not found")
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
            raise HubSpotAPIError("HubSpot refresh token unavailable")
        async with managed_http_client("hubspot-oauth") as client:
            response = await client.post(
                HUBSPOT_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.HUBSPOT_CLIENT_ID,
                    "client_secret": settings.HUBSPOT_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise HubSpotAPIError("HubSpot token refresh rejected")
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
        json_payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = await self._access_token()
        async with managed_http_client("hubspot-api", base_url=HUBSPOT_API_BASE) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise HubSpotAPIError(
                "HubSpot API request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "hubspot.search_contacts":
            query = str(arguments.get("query") or "").strip()
            filters = []
            if query:
                filters.append(
                    {
                        "filters": [
                            {
                                "propertyName": "email",
                                "operator": "CONTAINS_TOKEN",
                                "value": query,
                            }
                        ]
                    }
                )
            payload: dict[str, Any] = {
                "limit": min(max(int(arguments.get("limit") or 25), 1), 100),
                "properties": ["firstname", "lastname", "email", "phone", "jobtitle", "company"],
            }
            if filters:
                payload["filterGroups"] = filters
            return await self.request(
                "POST", "/crm/v3/objects/contacts/search", json_payload=payload
            )
        if operation == "hubspot.get_contact":
            contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
            return await self.request(
                "GET",
                f"/crm/v3/objects/contacts/{contact_id}",
                params={
                    "properties": "firstname,lastname,email,phone,jobtitle,company,website,lifecyclestage"
                },
            )
        if operation == "hubspot.search_companies":
            query = str(arguments.get("query") or "").strip()
            filters = []
            if query:
                filters.append(
                    {
                        "filters": [
                            {
                                "propertyName": "name",
                                "operator": "CONTAINS_TOKEN",
                                "value": query,
                            }
                        ]
                    }
                )
            payload = {
                "limit": min(max(int(arguments.get("limit") or 25), 1), 100),
                "properties": ["name", "domain", "industry", "phone", "city", "state"],
            }
            if filters:
                payload["filterGroups"] = filters
            return await self.request(
                "POST", "/crm/v3/objects/companies/search", json_payload=payload
            )
        if operation == "hubspot.get_company":
            company_id = str(arguments.get("company_id") or arguments.get("record_id") or "")
            return await self.request(
                "GET",
                f"/crm/v3/objects/companies/{company_id}",
                params={"properties": "name,domain,industry,phone,city,state,country"},
            )
        if operation == "hubspot.update_contact":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.update_contact_exactly_once(arguments)
            return await self._update_contact(arguments)
        if operation == "hubspot.create_note":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.create_note_exactly_once(arguments)
            return await self._create_note(arguments)
        if operation == "hubspot.send_email":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.send_email_exactly_once(arguments)
            raise HubSpotAPIError(
                "hubspot.send_email requires approval_request_id and workflow_run_id"
            )
        raise HubSpotAPIError(f"Unsupported HubSpot operation: {operation}")

    async def _update_contact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
        fields = filter_allowlisted_fields(
            arguments.get("fields"), allowlist=HUBSPOT_CONTACT_UPDATE_ALLOWLIST
        )
        if not fields:
            raise HubSpotAPIError("No allowlisted contact fields provided for update")
        requested = set(dict(arguments.get("fields") or {}).keys())
        rejected = sorted(requested - HUBSPOT_CONTACT_UPDATE_ALLOWLIST)
        if rejected:
            raise HubSpotAPIError(f"Rejected non-allowlisted HubSpot fields: {', '.join(rejected)}")
        body = await self.request(
            "PATCH",
            f"/crm/v3/objects/contacts/{contact_id}",
            json_payload={"properties": fields},
        )
        return {"contact_id": contact_id, "updated_fields": sorted(fields.keys()), "result": body}

    async def _create_note(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
        note_body = str(arguments.get("note_body") or arguments.get("body") or "")
        note = await self.request(
            "POST",
            "/crm/v3/objects/notes",
            json_payload={
                "properties": {
                    "hs_timestamp": _utcnow().isoformat(),
                    "hs_note_body": note_body,
                }
            },
        )
        note_id = str(note.get("id") or "")
        if note_id and contact_id:
            await self.request(
                "PUT",
                f"/crm/v3/objects/notes/{note_id}/associations/contacts/{contact_id}/note_to_contact",
            )
        return note

    async def _send_email(self, arguments: dict[str, Any]) -> dict[str, Any]:
        email_id = str(arguments.get("email_id") or "")
        email_to = str(arguments.get("email_to") or arguments.get("to") or "")
        if not email_id or not email_to:
            raise HubSpotAPIError("hubspot.send_email requires email_id and email_to")
        return await self.request(
            "POST",
            "/marketing/v3/transactional/single-email/send",
            json_payload={
                "emailId": email_id,
                "message": {
                    "to": email_to,
                    "cc": arguments.get("cc") or [],
                    "bcc": arguments.get("bcc") or [],
                },
                "customProperties": {
                    "subject": str(
                        arguments.get("email_subject") or arguments.get("subject") or ""
                    ),
                    "body": str(arguments.get("email_body") or arguments.get("message") or ""),
                },
            },
        )

    async def _mutation_exactly_once(
        self,
        *,
        action_key: str,
        arguments: dict[str, Any],
        resource_key: str,
        perform: Any,
    ) -> dict[str, Any]:
        owner_id = self.installation.owner_id
        workflow_run_id = str(arguments.get("workflow_run_id") or "")
        approval_id = str(arguments.get("approval_request_id") or "")
        if not all((workflow_run_id, approval_id, resource_key)):
            raise HubSpotAPIError(
                f"{action_key} requires workflow_run_id, approval_request_id, and a resource key"
            )
        args_hash = hubspot_crm_arguments_hash({**arguments, "record_type": "contact"})
        try:
            claim = await authorize_and_claim_execution(
                self.db,
                owner_id=owner_id,
                action_key=action_key,
                raw_arguments=arguments,
                approval_id=approval_id,
                idempotency_key=build_idempotency_key(
                    workflow_run_id, approval_id, resource_key, action_key
                ),
                arguments_hash=args_hash,
                connector_installation_id=self.installation.id,
                workflow_run_id=workflow_run_id,
                require_consumed=True,
            )
        except CommitAuthorizationError as exc:
            raise HubSpotAPIError(str(exc), retryable="Concurrent duplicate" in str(exc)) from exc
        existing = claim.execution
        if claim.replayed:
            return dict(existing.result_json or {})
        await mark_execution_sending(
            self.db,
            existing,
            owner_id=owner_id,
            audit_action=f"connector.{action_key.replace('.', '_')}_attempted",
            audit_metadata={"workflow_run_id": workflow_run_id, "approval_request_id": approval_id},
        )
        try:
            output = await perform()
        except Exception as exc:
            await mark_execution_failed(self.db, existing, owner_id=owner_id, error=str(exc))
            raise
        await mark_execution_succeeded(self.db, existing, owner_id=owner_id, result=output)
        return output

    async def update_contact_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")

        async def perform() -> dict[str, Any]:
            return await self._update_contact(arguments)

        return await self._mutation_exactly_once(
            action_key="hubspot.update_contact",
            arguments=arguments,
            resource_key=contact_id,
            perform=perform,
        )

    async def create_note_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")

        async def perform() -> dict[str, Any]:
            return await self._create_note(arguments)

        return await self._mutation_exactly_once(
            action_key="hubspot.create_note",
            arguments=arguments,
            resource_key=contact_id,
            perform=perform,
        )

    async def send_email_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        email_to = str(arguments.get("email_to") or arguments.get("to") or "")

        async def perform() -> dict[str, Any]:
            return await self._send_email(arguments)

        return await self._mutation_exactly_once(
            action_key="hubspot.send_email",
            arguments=arguments,
            resource_key=email_to,
            perform=perform,
        )

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
