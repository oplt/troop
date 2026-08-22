"""Jira Cloud OAuth and REST issue operations."""

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
from backend.modules.workforce.integrations.issue_tracking import jira_issue_arguments_hash
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOAuthState,
)
from backend.modules.workforce.services.connector_service import resolve_installation_config

ATLASSIAN_AUTHORIZE_URL = "https://auth.atlassian.com/authorize"
ATLASSIAN_TOKEN_URL = "https://auth.atlassian.com/oauth/token"
ATLASSIAN_RESOURCES_URL = "https://api.atlassian.com/oauth/token/accessible-resources"
JIRA_SCOPES = (
    "offline_access",
    "read:jira-work",
    "write:jira-work",
)


class JiraAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _jira_description(text: str) -> dict[str, Any]:
    body = str(text or "").strip()
    if not body:
        return {"type": "doc", "version": 1, "content": []}
    return {
        "type": "doc",
        "version": 1,
        "content": [{"type": "paragraph", "content": [{"type": "text", "text": body}]}],
    }


def _issue_ref(arguments: dict[str, Any]) -> str:
    return str(arguments.get("issue_key") or arguments.get("issue_id") or "")


class JiraOAuthService:
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
        if not settings.JIRA_CLIENT_ID or not settings.JIRA_OAUTH_REDIRECT_URI:
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY, "Jira OAuth is not configured"
            )
        requested = list(dict.fromkeys(scopes or JIRA_SCOPES))
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="jira",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("jira"),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "audience": "api.atlassian.com",
                "client_id": settings.JIRA_CLIENT_ID,
                "scope": " ".join(requested),
                "redirect_uri": settings.JIRA_OAUTH_REDIRECT_URI,
                "state": state,
                "response_type": "code",
                "prompt": "consent",
            }
        )
        return {"authorization_url": f"{ATLASSIAN_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(
                ConnectorOAuthState.provider == "jira", ConnectorOAuthState.state_hash == state_hash
            )
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state is None or oauth_state.consumed_at or oauth_state.expires_at <= _utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        async with managed_http_client("jira-oauth") as client:
            response = await client.post(
                ATLASSIAN_TOKEN_URL,
                json={
                    "grant_type": "authorization_code",
                    "client_id": settings.JIRA_CLIENT_ID,
                    "client_secret": settings.JIRA_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.JIRA_OAUTH_REDIRECT_URI,
                },
                headers=external_headers({"Content-Type": "application/json"}),
            )
        token = response.json()
        if response.status_code >= 400 or "access_token" not in token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Jira OAuth exchange failed")
        access_token = str(token["access_token"])
        async with managed_http_client("jira-api") as client:
            resources_resp = await client.get(
                ATLASSIAN_RESOURCES_URL,
                headers=external_headers({"Authorization": f"Bearer {access_token}"}),
            )
        resources = resources_resp.json() if resources_resp.content else []
        cloud_id = ""
        site_name = ""
        if isinstance(resources, list) and resources:
            primary = resources[0]
            cloud_id = str(primary.get("id") or "")
            site_name = str(primary.get("name") or "")
        definition = await self._definition()
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name=site_name or "Jira",
            status="active",
            config_json={
                "cloud_id": cloud_id,
                "site_name": site_name,
                "token_expires_at": (
                    _utcnow() + timedelta(seconds=int(token.get("expires_in") or 3600))
                ).isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(),
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": access_token,
                        "refresh_token": token.get("refresh_token") or "",
                    }
                )
            ),
            metadata_json={"provider": "jira", "site_name": site_name},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.jira.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "jira")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="jira",
                name="Jira",
                description="Read and manage Jira issues with approval-gated writes",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class JiraAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(
        cls, db: AsyncSession, *, owner_id: str, installation_id: str
    ) -> JiraAdapter:
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
                ConnectorDefinition.slug == "jira",
            )
        )
        row = result.first()
        if row is None:
            raise JiraAPIError("Authorized Jira installation not found")
        return cls(db, row[0])

    def _cloud_id(self, arguments: dict[str, Any] | None = None) -> str:
        if arguments and arguments.get("cloud_id"):
            return str(arguments["cloud_id"])
        return str((self.installation.config_json or {}).get("cloud_id") or "")

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        access_token = str(config.get("access_token") or "")
        expires_raw = (self.installation.config_json or {}).get("token_expires_at")
        expires_at = datetime.fromisoformat(expires_raw) if expires_raw else None
        if access_token and expires_at and expires_at > _utcnow() + timedelta(seconds=60):
            return access_token
        refresh_token = str(config.get("refresh_token") or "")
        if not refresh_token:
            raise JiraAPIError("Jira refresh token unavailable")
        async with managed_http_client("jira-oauth") as client:
            response = await client.post(
                ATLASSIAN_TOKEN_URL,
                json={
                    "grant_type": "refresh_token",
                    "client_id": settings.JIRA_CLIENT_ID,
                    "client_secret": settings.JIRA_CLIENT_SECRET,
                    "refresh_token": refresh_token,
                },
                headers=external_headers({"Content-Type": "application/json"}),
            )
        if response.status_code >= 400:
            raise JiraAPIError("Jira token refresh rejected")
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
        arguments: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        cloud_id = self._cloud_id(arguments)
        if not cloud_id:
            raise JiraAPIError("Jira cloud_id is not configured for this installation")
        token = await self._access_token()
        base = f"https://api.atlassian.com/ex/jira/{cloud_id}/rest/api/3"
        async with managed_http_client("jira-api", base_url=base) as client:
            response = await client.request(
                method,
                path,
                params=params,
                json=json_payload,
                headers=external_headers({"Authorization": f"Bearer {token}"}),
            )
        if response.status_code >= 400:
            raise JiraAPIError(
                "Jira API request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        return response.json() if response.content else {}

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        merged = {**arguments, "cloud_id": self._cloud_id(arguments)}
        if operation == "jira.search_issues":
            return await self.request(
                "GET",
                "/search",
                params={
                    "jql": str(arguments.get("jql") or "order by updated DESC"),
                    "maxResults": min(max(int(arguments.get("limit") or 25), 1), 100),
                    "fields": str(
                        arguments.get("fields")
                        or "summary,status,assignee,description,updated,project,issuetype,priority"
                    ),
                },
                arguments=merged,
            )
        if operation == "jira.get_issue":
            issue_ref = _issue_ref(arguments)
            return await self.request(
                "GET",
                f"/issue/{issue_ref}",
                params={"expand": str(arguments.get("expand") or "renderedFields,names")},
                arguments=merged,
            )
        if operation == "jira.get_issue_comments":
            issue_ref = _issue_ref(arguments)
            return await self.request("GET", f"/issue/{issue_ref}/comment", arguments=merged)
        if operation == "jira.create_issue":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.create_issue_exactly_once(merged)
            fields: dict[str, Any] = {
                "project": {"key": str(arguments["project_key"])},
                "summary": str(arguments.get("summary") or ""),
                "issuetype": {"name": str(arguments.get("issue_type") or "Task")},
            }
            description = str(arguments.get("description") or "")
            if description:
                fields["description"] = _jira_description(description)
            if arguments.get("priority"):
                fields["priority"] = {"name": str(arguments["priority"])}
            if arguments.get("assignee_account_id"):
                fields["assignee"] = {"id": str(arguments["assignee_account_id"])}
            return await self.request(
                "POST", "/issue", json_payload={"fields": fields}, arguments=merged
            )
        if operation == "jira.update_issue":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.update_issue_exactly_once(merged)
            issue_ref = _issue_ref(arguments)
            fields: dict[str, Any] = {}
            if arguments.get("summary"):
                fields["summary"] = str(arguments["summary"])
            if arguments.get("description"):
                fields["description"] = _jira_description(str(arguments["description"]))
            if arguments.get("priority"):
                fields["priority"] = {"name": str(arguments["priority"])}
            if not fields:
                raise JiraAPIError("jira.update_issue requires at least one field to update")
            await self.request(
                "PUT", f"/issue/{issue_ref}", json_payload={"fields": fields}, arguments=merged
            )
            return {"issue_key": issue_ref, "updated_fields": sorted(fields.keys())}
        if operation == "jira.add_comment":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.add_comment_exactly_once(merged)
            issue_ref = _issue_ref(arguments)
            body = str(arguments.get("comment_body") or arguments.get("comment") or "")
            return await self.request(
                "POST",
                f"/issue/{issue_ref}/comment",
                json_payload={"body": _jira_description(body)},
                arguments=merged,
            )
        raise JiraAPIError(f"Unsupported Jira operation: {operation}")

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
            raise JiraAPIError(
                f"{action_key} requires workflow_run_id, approval_request_id, and a resource key"
            )
        args_hash = jira_issue_arguments_hash(arguments)
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
            raise JiraAPIError(str(exc), retryable="Concurrent duplicate" in str(exc)) from exc
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

    async def create_issue_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        project_key = str(arguments.get("project_key") or "")

        async def perform() -> dict[str, Any]:
            fields: dict[str, Any] = {
                "project": {"key": project_key},
                "summary": str(arguments.get("summary") or ""),
                "issuetype": {"name": str(arguments.get("issue_type") or "Task")},
            }
            description = str(arguments.get("description") or "")
            if description:
                fields["description"] = _jira_description(description)
            if arguments.get("priority"):
                fields["priority"] = {"name": str(arguments["priority"])}
            return await self.request(
                "POST", "/issue", json_payload={"fields": fields}, arguments=arguments
            )

        return await self._mutation_exactly_once(
            action_key="jira.create_issue",
            arguments=arguments,
            resource_key=project_key,
            perform=perform,
        )

    async def update_issue_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        issue_ref = _issue_ref(arguments)

        async def perform() -> dict[str, Any]:
            fields: dict[str, Any] = {}
            if arguments.get("summary"):
                fields["summary"] = str(arguments["summary"])
            if arguments.get("description"):
                fields["description"] = _jira_description(str(arguments["description"]))
            if arguments.get("priority"):
                fields["priority"] = {"name": str(arguments["priority"])}
            if not fields:
                raise JiraAPIError("jira.update_issue requires at least one field to update")
            await self.request(
                "PUT", f"/issue/{issue_ref}", json_payload={"fields": fields}, arguments=arguments
            )
            return {"issue_key": issue_ref, "updated_fields": sorted(fields.keys())}

        return await self._mutation_exactly_once(
            action_key="jira.update_issue",
            arguments=arguments,
            resource_key=issue_ref,
            perform=perform,
        )

    async def add_comment_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        issue_ref = _issue_ref(arguments)
        body = str(arguments.get("comment_body") or arguments.get("comment") or "")

        async def perform() -> dict[str, Any]:
            return await self.request(
                "POST",
                f"/issue/{issue_ref}/comment",
                json_payload={"body": _jira_description(body)},
                arguments=arguments,
            )

        return await self._mutation_exactly_once(
            action_key="jira.add_comment",
            arguments=arguments,
            resource_key=f"{issue_ref}:{body[:64]}",
            perform=perform,
        )

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
