"""Salesforce OAuth and CRM read/enrichment operations."""

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
    SALESFORCE_CONTACT_UPDATE_ALLOWLIST,
    filter_allowlisted_fields,
    salesforce_crm_arguments_hash,
)
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

SALESFORCE_AUTHORIZE_URL = "https://login.salesforce.com/services/oauth2/authorize"
SALESFORCE_TOKEN_URL = "https://login.salesforce.com/services/oauth2/token"
SALESFORCE_SCOPES = ("api", "refresh_token", "offline_access")


class SalesforceAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


class SalesforceOAuthService:
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
        if not settings.SALESFORCE_CLIENT_ID or not settings.SALESFORCE_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Salesforce OAuth is not configured"
            )
        requested = list(dict.fromkeys(scopes or SALESFORCE_SCOPES))
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="salesforce",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("salesforce"),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "response_type": "code",
                "client_id": settings.SALESFORCE_CLIENT_ID,
                "redirect_uri": settings.SALESFORCE_OAUTH_REDIRECT_URI,
                "scope": " ".join(requested),
                "state": state,
            }
        )
        return {"authorization_url": f"{SALESFORCE_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "salesforce",
                ConnectorOAuthState.state_hash == state_hash,
            )
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state is None or oauth_state.consumed_at or oauth_state.expires_at <= _utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        async with managed_http_client("salesforce-oauth") as client:
            response = await client.post(
                SALESFORCE_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.SALESFORCE_CLIENT_ID,
                    "client_secret": settings.SALESFORCE_CLIENT_SECRET,
                    "redirect_uri": settings.SALESFORCE_OAUTH_REDIRECT_URI,
                    "code": code,
                },
                headers=external_headers(),
            )
        token = response.json()
        if response.status_code >= 400 or "access_token" not in token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Salesforce OAuth exchange failed")
        definition = await self._definition()
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Salesforce",
            status="active",
            config_json={
                "instance_url": str(token.get("instance_url") or ""),
                "token_expires_at": (
                    _utcnow() + timedelta(seconds=int(token.get("expires_in") or 3600))
                ).isoformat(),
                "granted_scopes": SALESFORCE_SCOPES,
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": token["access_token"],
                        "refresh_token": token.get("refresh_token") or "",
                    }
                )
            ),
            metadata_json={"provider": "salesforce"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.salesforce.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "salesforce")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="salesforce",
                name="Salesforce",
                description="Read and enrich Salesforce CRM records with approval-gated writes",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class SalesforceAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> SalesforceAdapter:
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
                ConnectorDefinition.slug == "salesforce",
            )
        )
        row = result.first()
        if row is None:
            raise SalesforceAPIError("Authorized Salesforce installation not found")
        return cls(db, row[0])

    def _instance_url(self) -> str:
        return str((self.installation.config_json or {}).get("instance_url") or "").rstrip("/")

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        access_token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if access_token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return access_token
        refresh_token = str(config.get("refresh_token") or "")
        if not refresh_token:
            raise SalesforceAPIError("Salesforce refresh token unavailable")
        async with managed_http_client("salesforce-oauth") as client:
            response = await client.post(
                SALESFORCE_TOKEN_URL,
                data={
                    "grant_type": "refresh_token",
                    "client_id": settings.SALESFORCE_CLIENT_ID,
                    "client_secret": settings.SALESFORCE_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
                headers=external_headers(),
            )
        if response.status_code >= 400:
            raise SalesforceAPIError("Salesforce token refresh rejected")
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
        if token.get("instance_url"):
            public["instance_url"] = str(token["instance_url"])
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
        instance_url = self._instance_url()
        if not instance_url:
            raise SalesforceAPIError("Salesforce instance_url is not configured")
        token = await self._access_token()
        async with managed_http_client("salesforce-api", base_url=instance_url) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise SalesforceAPIError(
                "Salesforce API request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "salesforce.search_contacts":
            query = str(arguments.get("query") or arguments.get("soql") or "").strip()
            if query.upper().startswith("SELECT"):
                soql = query
            else:
                safe = query.replace("'", "\\'")
                soql = (
                    "SELECT Id, FirstName, LastName, Email, Phone, Title, Account.Name "
                    f"FROM Contact WHERE Name LIKE '%{safe}%' OR Email LIKE '%{safe}%' "
                    f"LIMIT {min(max(int(arguments.get('limit') or 25), 1), 100)}"
                )
            return await self.request("GET", "/services/data/v59.0/query", params={"q": soql})
        if operation == "salesforce.get_contact":
            contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
            return await self.request("GET", f"/services/data/v59.0/sobjects/Contact/{contact_id}")
        if operation == "salesforce.search_accounts":
            query = str(arguments.get("query") or arguments.get("soql") or "").strip()
            if query.upper().startswith("SELECT"):
                soql = query
            else:
                safe = query.replace("'", "\\'")
                soql = (
                    "SELECT Id, Name, Website, Industry, Phone, BillingCity, BillingState "
                    f"FROM Account WHERE Name LIKE '%{safe}%' "
                    f"LIMIT {min(max(int(arguments.get('limit') or 25), 1), 100)}"
                )
            return await self.request("GET", "/services/data/v59.0/query", params={"q": soql})
        if operation == "salesforce.get_account":
            account_id = str(arguments.get("account_id") or arguments.get("record_id") or "")
            return await self.request("GET", f"/services/data/v59.0/sobjects/Account/{account_id}")
        if operation == "salesforce.update_contact":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.update_contact_exactly_once(arguments)
            return await self._update_contact(arguments)
        if operation == "salesforce.create_task":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.create_task_exactly_once(arguments)
            return await self._create_task(arguments)
        if operation == "salesforce.send_email":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.send_email_exactly_once(arguments)
            raise SalesforceAPIError(
                "salesforce.send_email requires approval_request_id and workflow_run_id"
            )
        raise SalesforceAPIError(f"Unsupported Salesforce operation: {operation}")

    async def _update_contact(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
        fields = filter_allowlisted_fields(
            arguments.get("fields"), allowlist=SALESFORCE_CONTACT_UPDATE_ALLOWLIST
        )
        if not fields:
            raise SalesforceAPIError("No allowlisted contact fields provided for update")
        requested = set(dict(arguments.get("fields") or {}).keys())
        rejected = sorted(requested - SALESFORCE_CONTACT_UPDATE_ALLOWLIST)
        if rejected:
            raise SalesforceAPIError(
                f"Rejected non-allowlisted Salesforce fields: {', '.join(rejected)}"
            )
        body = await self.request(
            "PATCH",
            f"/services/data/v59.0/sobjects/Contact/{contact_id}",
            json_payload=fields,
        )
        return {"contact_id": contact_id, "updated_fields": sorted(fields.keys()), "result": body}

    async def _create_task(self, arguments: dict[str, Any]) -> dict[str, Any]:
        who_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
        payload = {
            "Subject": str(
                arguments.get("task_subject") or arguments.get("subject") or "Follow up"
            ),
            "Description": str(
                arguments.get("task_description") or arguments.get("description") or ""
            ),
            "Status": "Not Started",
            "Priority": str(arguments.get("priority") or "Normal"),
        }
        if who_id:
            payload["WhoId"] = who_id
        what_id = str(arguments.get("account_id") or "")
        if what_id:
            payload["WhatId"] = what_id
        return await self.request(
            "POST", "/services/data/v59.0/sobjects/Task", json_payload=payload
        )

    async def _send_email(self, arguments: dict[str, Any]) -> dict[str, Any]:
        recipient_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")
        if not recipient_id:
            raise SalesforceAPIError("salesforce.send_email requires contact_id/recipient_id")
        return await self.request(
            "POST",
            "/services/data/v59.0/actions/standard/emailSimple",
            json_payload={
                "inputs": [
                    {
                        "emailSubject": str(
                            arguments.get("email_subject") or arguments.get("subject") or ""
                        ),
                        "emailBody": str(
                            arguments.get("email_body") or arguments.get("message") or ""
                        ),
                        "senderType": "CurrentUser",
                        "recipientId": recipient_id,
                    }
                ]
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
            raise SalesforceAPIError(
                f"{action_key} requires workflow_run_id, approval_request_id, and a resource key"
            )
        args_hash = salesforce_crm_arguments_hash({**arguments, "record_type": "contact"})
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
            raise SalesforceAPIError(
                str(exc), retryable="Concurrent duplicate" in str(exc)
            ) from exc
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
            action_key="salesforce.update_contact",
            arguments=arguments,
            resource_key=contact_id,
            perform=perform,
        )

    async def create_task_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")

        async def perform() -> dict[str, Any]:
            return await self._create_task(arguments)

        return await self._mutation_exactly_once(
            action_key="salesforce.create_task",
            arguments=arguments,
            resource_key=contact_id,
            perform=perform,
        )

    async def send_email_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        contact_id = str(arguments.get("contact_id") or arguments.get("record_id") or "")

        async def perform() -> dict[str, Any]:
            return await self._send_email(arguments)

        return await self._mutation_exactly_once(
            action_key="salesforce.send_email",
            arguments=arguments,
            resource_key=contact_id,
            perform=perform,
        )

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
