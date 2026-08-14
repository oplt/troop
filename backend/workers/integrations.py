"""Celery tasks for external-event inbox processing and subscription renewal."""

from __future__ import annotations

import asyncio

from backend.core.logging import get_logger
from backend.modules.workforce.integrations.gmail import GmailAPIError
from backend.modules.workforce.integrations.outlook import OutlookAPIError
from backend.workers.celery_app import celery_app

logger = get_logger(__name__)


async def _process_external_event(event_id: str) -> None:
    from backend.db.session import SessionLocal
    from backend.modules.workforce.integrations.events import ExternalEventService

    async with SessionLocal() as db:
        await ExternalEventService(db).process(event_id)


@celery_app.task(
    name="backend.workers.integrations.process_external_event",
    bind=True,
    autoretry_for=(GmailAPIError, OutlookAPIError),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=5,
)
def process_external_event(self, event_id: str) -> None:
    _ = self
    asyncio.run(_process_external_event(event_id))


async def _renew_gmail_watches() -> int:
    from backend.db.session import SessionLocal
    from backend.modules.workforce.integrations.events import TriggerSubscriptionService

    async with SessionLocal() as db:
        return await TriggerSubscriptionService(db).renew_due_gmail_watches()


@celery_app.task(name="backend.workers.integrations.renew_gmail_watches")
def renew_gmail_watches() -> int:
    return asyncio.run(_renew_gmail_watches())


async def _renew_outlook_subscriptions() -> int:
    from backend.db.session import SessionLocal
    from backend.modules.workforce.integrations.events import TriggerSubscriptionService

    async with SessionLocal() as db:
        return await TriggerSubscriptionService(db).renew_due_outlook_subscriptions()


@celery_app.task(name="backend.workers.integrations.renew_outlook_subscriptions")
def renew_outlook_subscriptions() -> int:
    return asyncio.run(_renew_outlook_subscriptions())
