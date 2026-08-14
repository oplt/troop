"""Linear OAuth and GraphQL issue operations."""

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
from backend.modules.workforce.integrations.issue_tracking import linear_issue_arguments_hash
from backend.modules.workforce.models import ConnectorDefinition, ConnectorInstallation, ConnectorOAuthState
from backend.modules.workforce.services.connector_service import resolve_installation_config

LINEAR_AUTHORIZE_URL = "https://linear.app/oauth/authorize"
LINEAR_TOKEN_URL = "https://api.linear.app/oauth/token"
LINEAR_GRAPHQL_URL = "https://api.linear.app/graphql"
LINEAR_SCOPES = ("read", "write", "issues:create", "comments:create")


class LinearAPIError(RuntimeError):
    def __init__(self, message: str, *, status_code: int | None = None, retryable: bool = False):
        super().__init__(message)
        self.status_code = status_code
        self.retryable = retryable


def _utcnow() -> datetime:
    return datetime.now(UTC)


def _hash_secret(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def _issue_ref(arguments: dict[str, Any]) -> str:
    return str(arguments.get("issue_id") or arguments.get("issue_key") or "")


class LinearOAuthService:
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
        if not settings.LINEAR_CLIENT_ID or not settings.LINEAR_OAUTH_REDIRECT_URI:
            raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Linear OAuth is not configured")
        requested = list(dict.fromkeys(scopes or LINEAR_SCOPES))
        state = secrets.token_urlsafe(32)
        row = ConnectorOAuthState(
            owner_id=owner_id,
            company_id=company_id,
            provider="linear",
            state_hash=_hash_secret(state),
            encrypted_code_verifier=encrypt_secret("linear"),
            requested_scopes_json=requested,
            redirect_after=redirect_after,
            expires_at=_utcnow() + timedelta(minutes=settings.CONNECTOR_OAUTH_STATE_TTL_MINUTES),
        )
        self.db.add(row)
        await self.db.commit()
        query = urlencode(
            {
                "client_id": settings.LINEAR_CLIENT_ID,
                "redirect_uri": settings.LINEAR_OAUTH_REDIRECT_URI,
                "response_type": "code",
                "scope": ",".join(requested),
                "state": state,
            }
        )
        return {"authorization_url": f"{LINEAR_AUTHORIZE_URL}?{query}", "scopes": requested}

    async def complete(self, *, code: str, state: str) -> tuple[ConnectorInstallation, str | None]:
        state_hash = _hash_secret(state)
        result = await self.db.execute(
            select(ConnectorOAuthState)
            .where(ConnectorOAuthState.provider == "linear", ConnectorOAuthState.state_hash == state_hash)
            .with_for_update()
        )
        oauth_state = result.scalar_one_or_none()
        if oauth_state is None or oauth_state.consumed_at or oauth_state.expires_at <= _utcnow():
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired OAuth state")
        async with managed_http_client("linear-oauth") as client:
            response = await client.post(
                LINEAR_TOKEN_URL,
                data={
                    "grant_type": "authorization_code",
                    "client_id": settings.LINEAR_CLIENT_ID,
                    "client_secret": settings.LINEAR_CLIENT_SECRET,
                    "code": code,
                    "redirect_uri": settings.LINEAR_OAUTH_REDIRECT_URI,
                },
                headers=external_headers(),
            )
        token = response.json()
        if response.status_code >= 400 or "access_token" not in token:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Linear OAuth exchange failed")
        definition = await self._definition()
        installation = ConnectorInstallation(
            id=str(uuid4()),
            connector_definition_id=definition.id,
            owner_id=oauth_state.owner_id,
            company_id=oauth_state.company_id,
            name="Linear",
            status="active",
            config_json={
                "token_expires_at": (
                    _utcnow() + timedelta(seconds=int(token.get("expires_in") or 3600))
                ).isoformat(),
                "granted_scopes": str(token.get("scope") or "").split(","),
            },
            secrets_ref=encrypt_secret(
                json.dumps(
                    {
                        "access_token": token["access_token"],
                        "refresh_token": token.get("refresh_token") or "",
                    }
                )
            ),
            metadata_json={"provider": "linear"},
        )
        self.db.add(installation)
        oauth_state.consumed_at = _utcnow()
        await AuditRepository(self.db).log(
            "connector.linear.connected",
            user_id=installation.owner_id,
            resource_type="connector_installation",
            resource_id=installation.id,
        )
        await self.db.commit()
        await self.db.refresh(installation)
        return installation, oauth_state.redirect_after

    async def _definition(self) -> ConnectorDefinition:
        result = await self.db.execute(
            select(ConnectorDefinition).where(ConnectorDefinition.slug == "linear")
        )
        definition = result.scalar_one_or_none()
        if definition is None:
            definition = ConnectorDefinition(
                slug="linear",
                name="Linear",
                description="Read and manage Linear issues with approval-gated writes",
                provider_type="native",
                config_schema_json={"type": "object", "properties": {}},
                metadata_json={"catalog": True},
            )
            self.db.add(definition)
            await self.db.flush()
        return definition


class LinearAdapter:
    def __init__(self, db: AsyncSession, installation: ConnectorInstallation) -> None:
        self.db = db
        self.installation = installation

    @classmethod
    async def for_owner(cls, db: AsyncSession, *, owner_id: str, installation_id: str) -> LinearAdapter:
        result = await db.execute(
            select(ConnectorInstallation, ConnectorDefinition)
            .join(ConnectorDefinition, ConnectorDefinition.id == ConnectorInstallation.connector_definition_id)
            .where(
                ConnectorInstallation.id == installation_id,
                ConnectorInstallation.owner_id == owner_id,
                ConnectorInstallation.status == "active",
                ConnectorDefinition.slug == "linear",
            )
        )
        row = result.first()
        if row is None:
            raise LinearAPIError("Authorized Linear installation not found")
        return cls(db, row[0])

    async def _access_token(self) -> str:
        config = resolve_installation_config(self.installation)
        return str(config.get("access_token") or "")

    async def graphql(self, query: str, variables: dict[str, Any] | None = None) -> dict[str, Any]:
        token = await self._access_token()
        if not token:
            raise LinearAPIError("Linear access token unavailable")
        async with managed_http_client("linear-api") as client:
            response = await client.post(
                LINEAR_GRAPHQL_URL,
                json={"query": query, "variables": variables or {}},
                headers=external_headers({"Authorization": token}),
            )
        body = response.json() if response.content else {}
        if response.status_code >= 400:
            raise LinearAPIError(
                "Linear GraphQL request failed",
                status_code=response.status_code,
                retryable=response.status_code in {408, 429, 500, 502, 503, 504},
            )
        if body.get("errors"):
            raise LinearAPIError(str(body["errors"][0].get("message") or "Linear GraphQL error"))
        return dict(body.get("data") or {})

    async def execute(self, operation: str, arguments: dict[str, Any]) -> dict[str, Any]:
        if operation == "linear.search_issues":
            query_text = str(arguments.get("query") or "").strip()
            team_id = str(arguments.get("team_id") or "")
            limit = min(max(int(arguments.get("limit") or 25), 1), 100)
            filter_parts = []
            if team_id:
                filter_parts.append(f'team: {{ id: {{ eq: "{team_id}" }} }}')
            if query_text:
                filter_parts.append(f'title: {{ containsIgnoreCase: "{query_text}" }}')
            filter_expr = ", ".join(filter_parts) if filter_parts else ""
            data = await self.graphql(
                f"""
                query SearchIssues {{
                  issues(first: {limit}, filter: {{ {filter_expr} }}) {{
                    nodes {{
                      id
                      identifier
                      title
                      description
                      url
                      priority
                      state {{ id name }}
                      assignee {{ id name email }}
                      team {{ id name }}
                    }}
                  }}
                }}
                """
            )
            return data
        if operation == "linear.get_issue":
            issue_ref = _issue_ref(arguments)
            data = await self.graphql(
                """
                query Issue($id: String!) {
                  issue(id: $id) {
                    id
                    identifier
                    title
                    description
                    url
                    priority
                    state { id name }
                    assignee { id name email }
                    team { id name }
                    comments { nodes { id body createdAt user { name email } } }
                  }
                }
                """,
                {"id": issue_ref},
            )
            return data
        if operation == "linear.get_issue_comments":
            issue_ref = _issue_ref(arguments)
            data = await self.graphql(
                """
                query IssueComments($id: String!) {
                  issue(id: $id) {
                    id
                    identifier
                    comments { nodes { id body createdAt user { name email } } }
                  }
                }
                """,
                {"id": issue_ref},
            )
            return data
        if operation == "linear.create_issue":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.create_issue_exactly_once(arguments)
            data = await self.graphql(
                """
                mutation CreateIssue($input: IssueCreateInput!) {
                  issueCreate(input: $input) {
                    success
                    issue { id identifier title url }
                  }
                }
                """,
                {
                    "input": {
                        "teamId": str(arguments["team_id"]),
                        "title": str(arguments.get("title") or arguments.get("summary") or ""),
                        "description": str(arguments.get("description") or ""),
                        "priority": int(arguments["priority"]) if str(arguments.get("priority") or "").isdigit() else None,
                    }
                },
            )
            return data
        if operation == "linear.update_issue":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.update_issue_exactly_once(arguments)
            issue_ref = _issue_ref(arguments)
            input_payload: dict[str, Any] = {}
            if arguments.get("title") or arguments.get("summary"):
                input_payload["title"] = str(arguments.get("title") or arguments.get("summary"))
            if arguments.get("description"):
                input_payload["description"] = str(arguments["description"])
            if arguments.get("state_id"):
                input_payload["stateId"] = str(arguments["state_id"])
            if arguments.get("priority") and str(arguments["priority"]).isdigit():
                input_payload["priority"] = int(arguments["priority"])
            if not input_payload:
                raise LinearAPIError("linear.update_issue requires at least one field to update")
            data = await self.graphql(
                """
                mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
                  issueUpdate(id: $id, input: $input) {
                    success
                    issue { id identifier title url state { name } }
                  }
                }
                """,
                {"id": issue_ref, "input": input_payload},
            )
            return data
        if operation == "linear.add_comment":
            if arguments.get("approval_request_id") and arguments.get("workflow_run_id"):
                return await self.add_comment_exactly_once(arguments)
            issue_ref = _issue_ref(arguments)
            body = str(arguments.get("comment_body") or arguments.get("comment") or "")
            data = await self.graphql(
                """
                mutation CommentCreate($input: CommentCreateInput!) {
                  commentCreate(input: $input) {
                    success
                    comment { id body createdAt }
                  }
                }
                """,
                {"input": {"issueId": issue_ref, "body": body}},
            )
            return data
        raise LinearAPIError(f"Unsupported Linear operation: {operation}")

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
            raise LinearAPIError(
                f"{action_key} requires workflow_run_id, approval_request_id, and a resource key"
            )
        args_hash = linear_issue_arguments_hash(arguments)
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
            raise LinearAPIError(str(exc), retryable="Concurrent duplicate" in str(exc)) from exc
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
        team_id = str(arguments.get("team_id") or "")

        async def perform() -> dict[str, Any]:
            return await self.graphql(
                """
                mutation CreateIssue($input: IssueCreateInput!) {
                  issueCreate(input: $input) {
                    success
                    issue { id identifier title url }
                  }
                }
                """,
                {
                    "input": {
                        "teamId": team_id,
                        "title": str(arguments.get("title") or arguments.get("summary") or ""),
                        "description": str(arguments.get("description") or ""),
                    }
                },
            )

        return await self._mutation_exactly_once(
            action_key="linear.create_issue",
            arguments=arguments,
            resource_key=team_id,
            perform=perform,
        )

    async def update_issue_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        issue_ref = _issue_ref(arguments)

        async def perform() -> dict[str, Any]:
            input_payload: dict[str, Any] = {}
            if arguments.get("title") or arguments.get("summary"):
                input_payload["title"] = str(arguments.get("title") or arguments.get("summary"))
            if arguments.get("description"):
                input_payload["description"] = str(arguments["description"])
            if arguments.get("state_id"):
                input_payload["stateId"] = str(arguments["state_id"])
            if not input_payload:
                raise LinearAPIError("linear.update_issue requires at least one field to update")
            return await self.graphql(
                """
                mutation UpdateIssue($id: String!, $input: IssueUpdateInput!) {
                  issueUpdate(id: $id, input: $input) {
                    success
                    issue { id identifier title url state { name } }
                  }
                }
                """,
                {"id": issue_ref, "input": input_payload},
            )

        return await self._mutation_exactly_once(
            action_key="linear.update_issue",
            arguments=arguments,
            resource_key=issue_ref,
            perform=perform,
        )

    async def add_comment_exactly_once(self, arguments: dict[str, Any]) -> dict[str, Any]:
        issue_ref = _issue_ref(arguments)
        body = str(arguments.get("comment_body") or arguments.get("comment") or "")

        async def perform() -> dict[str, Any]:
            return await self.graphql(
                """
                mutation CommentCreate($input: CommentCreateInput!) {
                  commentCreate(input: $input) {
                    success
                    comment { id body createdAt }
                  }
                }
                """,
                {"input": {"issueId": issue_ref, "body": body}},
            )

        return await self._mutation_exactly_once(
            action_key="linear.add_comment",
            arguments=arguments,
            resource_key=f"{issue_ref}:{body[:64]}",
            perform=perform,
        )

    async def revoke(self) -> None:
        self.installation.status = "revoked"
        self.installation.secrets_ref = None
        await self.db.flush()
