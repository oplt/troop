"""Native Gmail/Telegram connector and external-event endpoints."""

from __future__ import annotations

from contextlib import suppress
from typing import Any
from urllib.parse import quote, urlencode

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.api.deps.auth import get_authenticated_user
from backend.core.config import settings
from backend.core.schemas import RequestModel
from backend.db.session import get_db
from backend.modules.identity_access.models import User
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
    TelegramIdentityBinding,
    TriggerSubscription,
)
from backend.modules.workforce.services.connector_service import ConnectorService

router = APIRouter()


class GmailAuthorizeRequest(RequestModel):
    company_id: str | None = None
    scopes: list[str] | None = None
    redirect_after: str | None = None


class TelegramLinkRequest(RequestModel):
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
    display_status = installation.status
    if provider == "telegram" and installation.status == "active":
        display_status = "linked" if binding else "connected"
    return {
        "provider": provider,
        "status": display_status,
        "installation_id": installation.id,
        "account_label": (
            metadata.get("email_address")
            or (binding.telegram_username if binding else None)
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
        },
    }


@router.get("/connectors/gmail/status")
async def gmail_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="gmail")


@router.get("/connectors/telegram/status")
async def telegram_status(
    user: User = Depends(get_authenticated_user),
    db: AsyncSession = Depends(get_db),
) -> dict[str, Any]:
    return await _provider_installation_status(db, owner_id=user.id, provider="telegram")


@router.get("/connectors/gmail/callback")
async def gmail_oauth_callback(
    code: str,
    state: str,
    db: AsyncSession = Depends(get_db),
) -> RedirectResponse:
    installation, redirect_after = await GmailOAuthService(db).complete(code=code, state=state)
    target_path = (
        redirect_after
        if redirect_after and redirect_after.startswith("/")
        else "/integrations"
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
        query = query.where(
            ConnectorOperation.connector_definition_id == connector_definition_id
        )
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
