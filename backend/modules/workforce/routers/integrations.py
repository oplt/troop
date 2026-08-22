"""Native Gmail/Telegram connector and external-event endpoints."""

from __future__ import annotations

from contextlib import suppress
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request, status
from fastapi.responses import PlainTextResponse, RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.core.config import settings
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
from backend.modules.workforce.integrations.drive_sync import DriveSyncService
from backend.modules.workforce.integrations.events import (
    ExternalEventService,
    TriggerSubscriptionService,
    verify_pubsub_authentication,
)
from backend.modules.workforce.integrations.gmail import (
    GmailAdapter,
    GmailAPIError,
    GmailOAuthService,
)
from backend.modules.workforce.integrations.google_calendar import (
    GoogleCalendarAdapter,
    GoogleCalendarAPIError,
    GoogleCalendarOAuthService,
)
from backend.modules.workforce.integrations.google_drive import (
    GoogleDriveAdapter,
    GoogleDriveAPIError,
    GoogleDriveOAuthService,
)
from backend.modules.workforce.integrations.hubspot import (
    HubSpotAdapter,
    HubSpotAPIError,
    HubSpotOAuthService,
)
from backend.modules.workforce.integrations.jira import JiraAdapter, JiraAPIError, JiraOAuthService
from backend.modules.workforce.integrations.linear import (
    LinearAdapter,
    LinearAPIError,
    LinearOAuthService,
)
from backend.modules.workforce.integrations.microsoft_calendar import (
    MicrosoftCalendarAdapter,
    MicrosoftCalendarAPIError,
    MicrosoftCalendarOAuthService,
)
from backend.modules.workforce.integrations.microsoft_drive import (
    MicrosoftDriveAdapter,
    MicrosoftDriveAPIError,
    MicrosoftDriveOAuthService,
)
from backend.modules.workforce.integrations.outlook import (
    OutlookAdapter,
    OutlookAPIError,
    OutlookOAuthService,
)
from backend.modules.workforce.integrations.salesforce import (
    SalesforceAdapter,
    SalesforceAPIError,
    SalesforceOAuthService,
)
from backend.modules.workforce.integrations.slack import (
    SlackIdentityService,
    SlackOAuthService,
    SlackWebhookService,
    validate_slack_request_signature,
)
from backend.modules.workforce.integrations.teams import (
    TeamsIdentityService,
    TeamsOAuthService,
    TeamsWebhookService,
    validate_teams_bot_jwt,
)
from backend.modules.workforce.integrations.telegram import (
    TelegramAdapter,
    TelegramIdentityService,
    TelegramWebhookService,
    validate_telegram_webhook_secret,
)
from backend.modules.workforce.models import (
    ConnectorDefinition,
    ConnectorInstallation,
    ConnectorOperation,
    ExternalKnowledgeSource,
    SlackIdentityBinding,
    TeamsIdentityBinding,
    TelegramIdentityBinding,
    TriggerSubscription,
)
from backend.modules.workforce.services.connector_service import ConnectorService

router = APIRouter()


class GmailAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class OutlookAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class GoogleCalendarAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class MicrosoftCalendarAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class GoogleDriveAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class MicrosoftDriveAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class JiraAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class LinearAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class HubSpotAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class SalesforceAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class KnowledgeSourceCreateRequest(RequestModel):
    project_id: str
    connector_installation_id: str
    provider: str = Field(pattern="^(google_drive|microsoft_drive)$")
    root_config_json: dict[str, Any] = Field(default_factory=dict)
    company_id: str | None = None


class KnowledgeSourceResponse(BaseModel):
    id: str
    project_id: str
    connector_installation_id: str
    provider: str
    status: str
    sync_cursor: str | None = None
    last_synced_at: str | None = None
    root_config_json: dict[str, Any] = Field(default_factory=dict)


class TelegramLinkRequest(RequestModel):
    connector_installation_id: str
    company_id: str | None = None


class SlackAuthorizeRequest(RequestModel):
    company_id: str | None = None
    redirect_after: str | None = None


class SlackLinkRequest(RequestModel):
    connector_installation_id: str
    company_id: str | None = None


class TeamsAuthorizeRequest(RequestModel):
    company_id: str | None = None
    redirect_after: str | None = None


class TeamsLinkRequest(RequestModel):
    connector_installation_id: str
    company_id: str | None = None


class LinkResponse(BaseModel):
    binding_id: str
    expires_at: str
    deep_link_url: str


class SubscriptionResponse(BaseModel):
    id: str
    connector_installation_id: str
    workflow_id: str
    workflow_version_id: str
    node_id: str
    provider: str
    status: str
    expires_at: str | None = None
    last_event_at: str | None = None
    metadata_json: dict[str, Any] = Field(default_factory=dict)


@router.post("/connectors/gmail/authorize")
async def authorize_gmail(
    payload: GmailAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await GmailOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/outlook/authorize")
async def authorize_outlook(
    payload: OutlookAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await OutlookOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/google_calendar/authorize")
async def authorize_google_calendar(
    payload: GoogleCalendarAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await GoogleCalendarOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/microsoft_calendar/authorize")
async def authorize_microsoft_calendar(
    payload: MicrosoftCalendarAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await MicrosoftCalendarOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/google_drive/authorize")
async def authorize_google_drive(
    payload: GoogleDriveAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await GoogleDriveOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/microsoft_drive/authorize")
async def authorize_microsoft_drive(
    payload: MicrosoftDriveAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await MicrosoftDriveOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/jira/authorize")
async def authorize_jira(
    payload: JiraAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await JiraOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/linear/authorize")
async def authorize_linear(
    payload: LinearAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await LinearOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/hubspot/authorize")
async def authorize_hubspot(
    payload: HubSpotAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await HubSpotOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


@router.post("/connectors/salesforce/authorize")
async def authorize_salesforce(
    payload: SalesforceAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await SalesforceOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        scopes=payload.scopes,
        redirect_after=payload.redirect_after,
    )


async def _provider_installation_status(
    db: AsyncSession,
    *,
    owner_id: str,
    provider: str,
) -> dict[str, Any]:
    result = await db.execute(
        select(ConnectorInstallation, ConnectorDefinition)
        .join(
            ConnectorDefinition,
            ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
        )
        .where(
            ConnectorInstallation.owner_id == owner_id,
            ConnectorDefinition.slug == provider,
        )
        .order_by(ConnectorInstallation.updated_at.desc())
    )
    rows = result.all()
    if not rows:
        return {
            "provider": provider,
            "status": "disconnected",
            "installation_id": None,
            "account_label": None,
            "granted_scopes": [],
            "required_scopes": [],
            "last_successful_event_at": None,
            "expires_at": None,
            "error": None,
            "metadata": {},
        }
    installation = rows[0][0]
    config = dict(installation.config_json or {})
    metadata = dict(installation.metadata_json or {})
    subscription = None
    if provider == "gmail":
        subscription_result = await db.execute(
            select(TriggerSubscription)
            .where(
                TriggerSubscription.owner_id == owner_id,
                TriggerSubscription.connector_installation_id == installation.id,
            )
            .order_by(TriggerSubscription.updated_at.desc())
            .limit(1)
        )
        subscription = subscription_result.scalar_one_or_none()
    if provider == "outlook":
        subscription_result = await db.execute(
            select(TriggerSubscription)
            .where(
                TriggerSubscription.owner_id == owner_id,
                TriggerSubscription.connector_installation_id == installation.id,
            )
            .order_by(TriggerSubscription.updated_at.desc())
            .limit(1)
        )
        subscription = subscription_result.scalar_one_or_none()
    binding = None
    if provider == "telegram":
        binding_result = await db.execute(
            select(TelegramIdentityBinding)
            .where(
                TelegramIdentityBinding.owner_id == owner_id,
                TelegramIdentityBinding.connector_installation_id == installation.id,
                TelegramIdentityBinding.status == "active",
            )
            .order_by(TelegramIdentityBinding.created_at.desc())
            .limit(1)
        )
        binding = binding_result.scalar_one_or_none()
    slack_binding = None
    if provider == "slack":
        binding_result = await db.execute(
            select(SlackIdentityBinding)
            .where(
                SlackIdentityBinding.owner_id == owner_id,
                SlackIdentityBinding.connector_installation_id == installation.id,
                SlackIdentityBinding.status == "active",
            )
            .order_by(SlackIdentityBinding.created_at.desc())
            .limit(1)
        )
        slack_binding = binding_result.scalar_one_or_none()
    teams_binding = None
    if provider == "teams":
        binding_result = await db.execute(
            select(TeamsIdentityBinding)
            .where(
                TeamsIdentityBinding.owner_id == owner_id,
                TeamsIdentityBinding.connector_installation_id == installation.id,
                TeamsIdentityBinding.status == "active",
            )
            .order_by(TeamsIdentityBinding.created_at.desc())
            .limit(1)
        )
        teams_binding = binding_result.scalar_one_or_none()
    display_status = installation.status
    if provider == "telegram" and installation.status == "active":
        display_status = "linked" if binding else "connected"
    if provider == "slack" and installation.status == "active":
        display_status = "linked" if slack_binding else "connected"
    if provider == "teams" and installation.status == "active":
        display_status = "linked" if teams_binding else "connected"
    return {
        "provider": provider,
        "status": display_status,
        "installation_id": installation.id,
        "account_label": (
            metadata.get("email_address")
            or metadata.get("team_name")
            or metadata.get("tenant_name")
            or (binding.telegram_username if binding else None)
            or (slack_binding.slack_username if slack_binding else None)
            or (teams_binding.teams_username if teams_binding else None)
            or installation.name
        ),
        "granted_scopes": list(config.get("granted_scopes") or []),
        "required_scopes": [],
        "last_successful_event_at": (
            subscription.last_event_at.isoformat()
            if subscription and subscription.last_event_at
            else metadata.get("last_successful_event_at")
        ),
        "expires_at": (
            subscription.expires_at.isoformat()
            if subscription and subscription.expires_at
            else config.get("token_expires_at")
        ),
        "error": metadata.get("last_error"),
        "metadata": {
            "connection_count": len(rows),
            "watch_status": subscription.status if subscription else None,
            "telegram_binding_id": binding.id if binding else None,
            "slack_binding_id": slack_binding.id if slack_binding else None,
            "teams_binding_id": teams_binding.id if teams_binding else None,
        },
    }


@router.get("/connectors/gmail/status")
async def gmail_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="gmail")


@router.get("/connectors/outlook/status")
async def outlook_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="outlook")


@router.get("/connectors/google_calendar/status")
async def google_calendar_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="google_calendar")


@router.get("/connectors/microsoft_calendar/status")
async def microsoft_calendar_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="microsoft_calendar")


@router.get("/connectors/google_drive/status")
async def google_drive_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="google_drive")


@router.get("/connectors/microsoft_drive/status")
async def microsoft_drive_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="microsoft_drive")


@router.get("/connectors/jira/status")
async def jira_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="jira")


@router.get("/connectors/linear/status")
async def linear_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="linear")


@router.get("/connectors/hubspot/status")
async def hubspot_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="hubspot")


@router.get("/connectors/salesforce/status")
async def salesforce_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="salesforce")


@router.get("/connectors/telegram/status")
async def telegram_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="telegram")


@router.get("/connectors/slack/status")
async def slack_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="slack")


@router.post("/connectors/slack/authorize")
async def authorize_slack(
    payload: SlackAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await SlackOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        redirect_after=payload.redirect_after,
    )


@router.get("/connectors/teams/status")
async def teams_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="teams")


@router.post("/connectors/teams/authorize")
async def authorize_teams(
    payload: TeamsAuthorizeRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    return await TeamsOAuthService(db).begin(
        user.id,
        company_id=payload.company_id,
        redirect_after=payload.redirect_after,
    )


@router.get("/connectors/gmail/callback")
async def gmail_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await GmailOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "gmail",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/slack/callback")
async def slack_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await SlackOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "slack",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/teams/callback")
async def teams_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await TeamsOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "teams",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/outlook/callback")
async def outlook_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await OutlookOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "outlook",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/google_calendar/callback")
async def google_calendar_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await GoogleCalendarOAuthService(db).complete(
        code=code, state=state
    )
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "google_calendar",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/microsoft_calendar/callback")
async def microsoft_calendar_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await MicrosoftCalendarOAuthService(db).complete(
        code=code, state=state
    )
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "microsoft_calendar",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/google_drive/callback")
async def google_drive_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await GoogleDriveOAuthService(db).complete(
        code=code, state=state
    )
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "google_drive",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/microsoft_drive/callback")
async def microsoft_drive_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await MicrosoftDriveOAuthService(db).complete(
        code=code, state=state
    )
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "microsoft_drive",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/jira/callback")
async def jira_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await JiraOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "jira",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/linear/callback")
async def linear_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await LinearOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "linear",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/hubspot/callback")
async def hubspot_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await HubSpotOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "hubspot",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.get("/connectors/salesforce/callback")
async def salesforce_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await SalesforceOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after if redirect_after and redirect_after.startswith("/") else "/integrations"
    )
    if target_path.startswith("//"):
        target_path = "/integrations"
    separator = "&" if "?" in target_path else "?"
    query = urlencode(
        {
            "integration": "salesforce",
            "status": "connected",
            "installation_id": installation.id,
        }
    )
    return RedirectResponse(
        url=f"{settings.FRONTEND_URL.rstrip('/')}{target_path}{separator}{query}",
        status_code=status.HTTP_302_FOUND,
    )


@router.post("/connectors/gmail/{installation_id}/disconnect")
async def disconnect_gmail(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await GmailAdapter.for_owner(db, owner_id=user.id, installation_id=installation_id)
    with suppress(GmailAPIError):
        await adapter.stop_watch()
    subscriptions = await db.execute(
        select(TriggerSubscription).where(
            TriggerSubscription.owner_id == user.id,
            TriggerSubscription.connector_installation_id == installation_id,
        )
    )
    for subscription in subscriptions.scalars().all():
        subscription.status = "disabled"
    await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/outlook/{installation_id}/disconnect")
async def disconnect_outlook(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await OutlookAdapter.for_owner(db, owner_id=user.id, installation_id=installation_id)
    subscriptions = await db.execute(
        select(TriggerSubscription).where(
            TriggerSubscription.owner_id == user.id,
            TriggerSubscription.connector_installation_id == installation_id,
        )
    )
    for subscription in subscriptions.scalars().all():
        with suppress(OutlookAPIError):
            await adapter.stop_subscription(subscription)
        subscription.status = "disabled"
    await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/google_calendar/{installation_id}/disconnect")
async def disconnect_google_calendar(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await GoogleCalendarAdapter.for_owner(
        db, owner_id=user.id, installation_id=installation_id
    )
    with suppress(GoogleCalendarAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/microsoft_calendar/{installation_id}/disconnect")
async def disconnect_microsoft_calendar(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await MicrosoftCalendarAdapter.for_owner(
        db, owner_id=user.id, installation_id=installation_id
    )
    with suppress(MicrosoftCalendarAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/google_drive/{installation_id}/disconnect")
async def disconnect_google_drive(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await GoogleDriveAdapter.for_owner(
        db, owner_id=user.id, installation_id=installation_id
    )
    with suppress(GoogleDriveAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/microsoft_drive/{installation_id}/disconnect")
async def disconnect_microsoft_drive(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await MicrosoftDriveAdapter.for_owner(
        db, owner_id=user.id, installation_id=installation_id
    )
    with suppress(MicrosoftDriveAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/jira/{installation_id}/disconnect")
async def disconnect_jira(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await JiraAdapter.for_owner(db, owner_id=user.id, installation_id=installation_id)
    with suppress(JiraAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/linear/{installation_id}/disconnect")
async def disconnect_linear(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await LinearAdapter.for_owner(db, owner_id=user.id, installation_id=installation_id)
    with suppress(LinearAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/hubspot/{installation_id}/disconnect")
async def disconnect_hubspot(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await HubSpotAdapter.for_owner(db, owner_id=user.id, installation_id=installation_id)
    with suppress(HubSpotAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


@router.post("/connectors/salesforce/{installation_id}/disconnect")
async def disconnect_salesforce(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, str]:
    adapter = await SalesforceAdapter.for_owner(
        db, owner_id=user.id, installation_id=installation_id
    )
    with suppress(SalesforceAPIError):
        await adapter.revoke()
    await db.commit()
    return {"status": "revoked"}


def _serialize_knowledge_source(row: ExternalKnowledgeSource) -> KnowledgeSourceResponse:
    return KnowledgeSourceResponse(
        id=row.id,
        project_id=row.project_id,
        connector_installation_id=row.connector_installation_id,
        provider=row.provider,
        status=row.status,
        sync_cursor=row.sync_cursor,
        last_synced_at=row.last_synced_at.isoformat() if row.last_synced_at else None,
        root_config_json=dict(row.root_config_json or {}),
    )


@router.post("/knowledge-sources", response_model=KnowledgeSourceResponse)
async def create_knowledge_source(
    payload: KnowledgeSourceCreateRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> KnowledgeSourceResponse:
    from backend.modules.orchestration.services.service import OrchestrationService
    from backend.modules.workforce.authz import assert_company_owned

    await assert_company_owned(db, user.id, payload.company_id)
    await OrchestrationService(db).get_project(user, payload.project_id)
    installation = await db.get(ConnectorInstallation, payload.connector_installation_id)
    if installation is None or installation.owner_id != user.id or installation.status != "active":
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Connector installation not found")
    source = ExternalKnowledgeSource(
        owner_id=user.id,
        company_id=payload.company_id or installation.company_id,
        project_id=payload.project_id,
        connector_installation_id=payload.connector_installation_id,
        provider=payload.provider,
        root_config_json=dict(payload.root_config_json or {}),
        status="active",
    )
    db.add(source)
    await db.commit()
    await db.refresh(source)
    return _serialize_knowledge_source(source)


@router.get("/knowledge-sources", response_model=list[KnowledgeSourceResponse])
async def list_knowledge_sources(
    project_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[KnowledgeSourceResponse]:
    from backend.modules.orchestration.services.service import OrchestrationService

    await OrchestrationService(db).get_project(user, project_id)
    result = await db.execute(
        select(ExternalKnowledgeSource)
        .where(
            ExternalKnowledgeSource.owner_id == user.id,
            ExternalKnowledgeSource.project_id == project_id,
        )
        .order_by(ExternalKnowledgeSource.created_at.desc())
    )
    return [_serialize_knowledge_source(row) for row in result.scalars().all()]


@router.post("/knowledge-sources/{source_id}/sync")
async def sync_knowledge_source(
    source_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    try:
        result = await DriveSyncService(db).sync_source(source_id, actor_user_id=user.id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    except (GoogleDriveAPIError, MicrosoftDriveAPIError) as exc:
        raise HTTPException(status.HTTP_502_BAD_GATEWAY, str(exc)) from exc
    return result


@router.get("/connector-operations")
async def list_connector_operations(
    connector_definition_id: str | None = None,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    _ = user
    await ConnectorService(db).seed_definitions()
    query = select(ConnectorOperation).where(ConnectorOperation.is_active.is_(True))
    if connector_definition_id:
        query = query.where(ConnectorOperation.connector_definition_id == connector_definition_id)
    result = await db.execute(query.order_by(ConnectorOperation.slug.asc()))
    return [
        {
            "id": row.id,
            "connector_definition_id": row.connector_definition_id,
            "slug": row.slug,
            "operation_type": row.operation_type,
            "name": row.name,
            "description": row.description,
            "input_schema_json": row.input_schema_json,
            "output_schema_json": row.output_schema_json,
            "risk_level": row.risk_level,
            "requires_approval": row.requires_approval,
            "required_scopes": row.required_scopes_json,
        }
        for row in result.scalars().all()
    ]


@router.post("/connectors/telegram/link", response_model=LinkResponse)
async def create_telegram_link(
    payload: TelegramLinkRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> LinkResponse:
    binding, token = await TelegramIdentityService(db).create_link(
        user.id,
        payload.connector_installation_id,
        company_id=payload.company_id,
    )
    bot_username = settings.TELEGRAM_BOT_USERNAME.strip().lstrip("@")
    if not bot_username:
        raise HTTPException(
            status.HTTP_503_SERVICE_UNAVAILABLE, "Telegram bot username is not configured"
        )
    return LinkResponse(
        binding_id=binding.id,
        expires_at=binding.token_expires_at.isoformat(),
        deep_link_url=f"https://t.me/{quote(bot_username)}?start={quote(token)}",
    )


@router.post("/connectors/telegram/{installation_id}/configure-webhook")
async def configure_telegram_webhook(
    installation_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    installation = await TelegramIdentityService(db).get_installation(user.id, installation_id)
    return await TelegramAdapter(installation).configure_webhook()


@router.get("/connectors/telegram/bindings")
async def list_telegram_bindings(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(TelegramIdentityBinding)
        .where(TelegramIdentityBinding.owner_id == user.id)
        .order_by(TelegramIdentityBinding.created_at.desc())
    )
    return [
        {
            "id": row.id,
            "connector_installation_id": row.connector_installation_id,
            "telegram_username": row.telegram_username,
            "status": row.status,
            "linked_at": row.linked_at,
        }
        for row in result.scalars().all()
    ]


@router.delete("/connectors/telegram/bindings/{binding_id}", status_code=204)
async def unlink_telegram(
    binding_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await TelegramIdentityService(db).revoke(user.id, binding_id)


@router.post("/connectors/slack/link", response_model=LinkResponse)
async def create_slack_link(
    payload: SlackLinkRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> LinkResponse:
    binding, token = await SlackIdentityService(db).create_link(
        user.id,
        payload.connector_installation_id,
        company_id=payload.company_id,
    )
    return LinkResponse(
        binding_id=binding.id,
        expires_at=binding.token_expires_at.isoformat(),
        deep_link_url=f"link {token}",
    )


@router.get("/connectors/slack/bindings")
async def list_slack_bindings(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(SlackIdentityBinding)
        .where(SlackIdentityBinding.owner_id == user.id)
        .order_by(SlackIdentityBinding.created_at.desc())
    )
    return [
        {
            "id": row.id,
            "connector_installation_id": row.connector_installation_id,
            "slack_username": row.slack_username,
            "slack_team_id": row.slack_team_id,
            "status": row.status,
            "linked_at": row.linked_at,
        }
        for row in result.scalars().all()
    ]


@router.delete("/connectors/slack/bindings/{binding_id}", status_code=204)
async def unlink_slack(
    binding_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await SlackIdentityService(db).revoke(user.id, binding_id)


@router.post("/connectors/teams/link", response_model=LinkResponse)
async def create_teams_link(
    payload: TeamsLinkRequest,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> LinkResponse:
    binding, token = await TeamsIdentityService(db).create_link(
        user.id,
        payload.connector_installation_id,
        company_id=payload.company_id,
    )
    return LinkResponse(
        binding_id=binding.id,
        expires_at=binding.token_expires_at.isoformat(),
        deep_link_url=f"link {token}",
    )


@router.get("/connectors/teams/bindings")
async def list_teams_bindings(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[dict[str, Any]]:
    result = await db.execute(
        select(TeamsIdentityBinding)
        .where(TeamsIdentityBinding.owner_id == user.id)
        .order_by(TeamsIdentityBinding.created_at.desc())
    )
    return [
        {
            "id": row.id,
            "connector_installation_id": row.connector_installation_id,
            "teams_username": row.teams_username,
            "teams_tenant_id": row.teams_tenant_id,
            "status": row.status,
            "linked_at": row.linked_at,
        }
        for row in result.scalars().all()
    ]


@router.delete("/connectors/teams/bindings/{binding_id}", status_code=204)
async def unlink_teams(
    binding_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> None:
    await TeamsIdentityService(db).revoke(user.id, binding_id)


@router.get("/trigger-subscriptions", response_model=list[SubscriptionResponse])
async def list_trigger_subscriptions(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> list[SubscriptionResponse]:
    result = await db.execute(
        select(TriggerSubscription)
        .where(TriggerSubscription.owner_id == user.id)
        .order_by(TriggerSubscription.created_at.desc())
    )
    return [
        SubscriptionResponse(
            id=row.id,
            connector_installation_id=row.connector_installation_id,
            workflow_id=row.workflow_id,
            workflow_version_id=row.workflow_version_id,
            node_id=row.node_id,
            provider=row.provider,
            status=row.status,
            expires_at=row.expires_at.isoformat() if row.expires_at else None,
            last_event_at=row.last_event_at.isoformat() if row.last_event_at else None,
            metadata_json=row.metadata_json or {},
        )
        for row in result.scalars().all()
    ]


@router.delete("/trigger-subscriptions/{subscription_id}")
async def disable_trigger_subscription(
    subscription_id: str,
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> SubscriptionResponse:
    try:
        row = await TriggerSubscriptionService(db).disable(user.id, subscription_id)
    except ValueError as exc:
        raise HTTPException(status.HTTP_404_NOT_FOUND, str(exc)) from exc
    return SubscriptionResponse(
        id=row.id,
        connector_installation_id=row.connector_installation_id,
        workflow_id=row.workflow_id,
        workflow_version_id=row.workflow_version_id,
        node_id=row.node_id,
        provider=row.provider,
        status=row.status,
        expires_at=row.expires_at.isoformat() if row.expires_at else None,
        last_event_at=row.last_event_at.isoformat() if row.last_event_at else None,
        metadata_json=row.metadata_json or {},
    )


async def _bounded_json(request: Request) -> dict[str, Any]:
    body = await request.body()
    if len(body) > settings.EXTERNAL_WEBHOOK_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload too large")
    try:
        parsed = await request.json()
    except ValueError as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed JSON") from exc
    if not isinstance(parsed, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Webhook body must be an object")
    return parsed


@router.post("/webhooks/gmail", status_code=202)
async def gmail_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not await verify_pubsub_authentication(authorization):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Pub/Sub authentication")
    payload = await _bounded_json(request)
    try:
        ingested = await ExternalEventService(db).ingest_gmail_push(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    from backend.workers.integrations import process_external_event

    created_events = [event for event, created in ingested if created]
    for event in created_events:
        process_external_event.apply_async(args=[event.id])
    return {
        "status": "accepted" if created_events else "duplicate",
        "event_ids": [event.id for event, _created in ingested],
    }


@router.get("/webhooks/outlook", response_model=None)
async def outlook_webhook_validation(
    validation_token: str = Query(alias="validationToken"),
) -> PlainTextResponse:
    return PlainTextResponse(validation_token)


@router.post("/webhooks/outlook", status_code=202)
async def outlook_webhook(
    request: Request,
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    payload = await _bounded_json(request)
    try:
        ingested = await ExternalEventService(db).ingest_outlook_push(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, str(exc)) from exc
    from backend.workers.integrations import process_external_event

    created_events = [event for event, created in ingested if created]
    for event in created_events:
        process_external_event.apply_async(args=[event.id])
    return {
        "status": "accepted" if created_events else "duplicate",
        "event_ids": [event.id for event, _created in ingested],
    }


@router.post("/webhooks/telegram", status_code=202)
async def telegram_webhook(
    request: Request,
    x_telegram_bot_api_secret_token: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not validate_telegram_webhook_secret(x_telegram_bot_api_secret_token):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Telegram webhook secret")
    payload = await _bounded_json(request)
    try:
        return await TelegramWebhookService(db).handle(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc


@router.post("/webhooks/slack", status_code=202)
async def slack_webhook(
    request: Request,
    x_slack_signature: str | None = Header(default=None),
    x_slack_request_timestamp: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    raw_body = await request.body()
    if len(raw_body) > settings.EXTERNAL_WEBHOOK_MAX_BYTES:
        raise HTTPException(status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "Webhook payload too large")
    if not validate_slack_request_signature(
        body=raw_body,
        timestamp=x_slack_request_timestamp,
        signature=x_slack_signature,
    ):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Slack webhook signature")
    content_type = (request.headers.get("content-type") or "").lower()
    import json as json_module

    if "application/x-www-form-urlencoded" in content_type:
        from urllib.parse import parse_qs

        parsed = parse_qs(raw_body.decode())
        payload_raw = (parsed.get("payload") or [None])[0]
        if not payload_raw:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Missing Slack interactive payload")
        payload = json_module.loads(payload_raw)
    else:
        try:
            payload = json_module.loads(raw_body.decode())
        except ValueError as exc:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, "Malformed JSON") from exc
    if not isinstance(payload, dict):
        raise HTTPException(status.HTTP_422_UNPROCESSABLE_ENTITY, "Webhook body must be an object")
    try:
        result = await SlackWebhookService(db).handle(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
    if payload.get("type") == "url_verification":
        return result
    return result


@router.post("/webhooks/teams", status_code=202)
async def teams_webhook(
    request: Request,
    authorization: str | None = Header(default=None),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    if not await validate_teams_bot_jwt(authorization):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid Teams bot JWT")
    payload = await _bounded_json(request)
    try:
        return await TeamsWebhookService(db).handle(payload)
    except ValueError as exc:
        raise HTTPException(status.HTTP_403_FORBIDDEN, str(exc)) from exc
