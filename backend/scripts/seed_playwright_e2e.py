#!/usr/bin/env python3
"""Seed PostgreSQL fixtures for Playwright E2E tests.

Usage (from repo root, with DATABASE_URL set):
  PYTHONPATH=. python backend/scripts/seed_playwright_e2e.py credentials --output frontend/e2e/.auth/credentials.json
  PYTHONPATH=. python backend/scripts/seed_playwright_e2e.py stale-approval --user-id <uuid> --output /tmp/stale.json
  PYTHONPATH=. python backend/scripts/seed_playwright_e2e.py reauth-connector --user-id <uuid> --output /tmp/reauth.json
  PYTHONPATH=. python backend/scripts/seed_playwright_e2e.py critical-flow --user-id <uuid> --output /tmp/critical.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from backend.core.security import hash_password
from backend.db.session import SessionLocal
from backend.modules.identity_access.models import User
from backend.modules.orchestration.execution.hitl.exact_effect import (
    apply_proposed_effect_to_approval,
    build_proposed_effect,
)
from backend.modules.orchestration.models import ApprovalRequest
from backend.modules.orchestration.security import encrypt_secret
from backend.modules.workforce.models import WorkflowDefinition
from backend.modules.workforce.services.connector_service import ConnectorService
from backend.modules.workforce.services.tool_registry import ToolRegistryService
from backend.modules.workforce.services.workflow_version_service import WorkflowVersionService


async def _create_verified_user() -> dict[str, str]:
    password = "PlaywrightE2EPass123!"
    email = f"playwright-{uuid.uuid4().hex[:10]}@example.com"
    async with SessionLocal() as db:
        user = User(
            email=email,
            password_hash=hash_password(password),
            full_name="Playwright E2E User",
            is_active=True,
            is_verified=True,
            is_admin=False,
            mfa_enabled=False,
        )
        db.add(user)
        await db.commit()
        await db.refresh(user)
        return {"email": email, "password": password, "userId": user.id}


async def _seed_stale_approval(user_id: str) -> dict[str, str]:
    effect = build_proposed_effect(
        action_key="tool:fs_write",
        raw_arguments={"path": "stale-playwright.txt", "content": "stale"},
        expires_at=datetime.now(UTC) - timedelta(minutes=5),
    )
    approval = ApprovalRequest(
        requested_by_user_id=user_id,
        approval_type="tool:fs_write",
        status="pending",
        payload_json={
            "owner_id": user_id,
            "draft_arguments": {"path": "stale-playwright.txt", "content": "stale"},
            "action_key": "tool:fs_write",
        },
    )
    apply_proposed_effect_to_approval(approval, effect)
    async with SessionLocal() as db:
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return {"approvalId": approval.id}


async def _seed_reauth_connector(user_id: str) -> dict[str, str]:
    async with SessionLocal() as db:
        service = ConnectorService(db)
        await service.seed_definitions()
        installation = await service.install(
            user_id,
            connector_slug="gmail",
            name="E2E Gmail Fixture",
            config_json={
                "token_expires_at": (datetime.now(UTC) - timedelta(hours=1)).isoformat(),
                "granted_scopes": ["https://www.googleapis.com/auth/gmail.send"],
            },
        )
        installation.status = "reauthorization_required"
        metadata = dict(installation.metadata_json or {})
        metadata["last_error"] = "OAuth token expired — reconnect Gmail to continue."
        metadata["email_address"] = "fixture@gmail.com"
        installation.metadata_json = metadata
        installation.secrets_ref = encrypt_secret(
            json.dumps({"access_token": "expired", "refresh_token": "refresh-fixture"})
        )
        await db.commit()
        await db.refresh(installation)
        return {"installationId": installation.id, "provider": "gmail"}


async def _seed_critical_flow(user_id: str) -> dict[str, Any]:
    suffix = uuid.uuid4().hex[:8]
    async with SessionLocal() as db:
        registry = ToolRegistryService(db)
        await registry.seed_tool_definitions()

        connector_service = ConnectorService(db)
        await connector_service.seed_definitions()
        telegram = await connector_service.install(
            user_id,
            connector_slug="telegram",
            name="E2E Telegram Fixture",
            config_json={"bot_token": "123456789:E2E-fixture-token-not-real"},
        )

        nodes = [
            {
                "id": "write-1",
                "type": "tool",
                "config": {
                    "tool_slug": "fs_write",
                    "params": {
                        "path": f"playwright-e2e-{suffix}.txt",
                        "content": "Playwright critical-flow receipt",
                    },
                },
            }
        ]
        workflow = WorkflowDefinition(
            owner_id=user_id,
            slug=f"e2e-critical-{suffix}",
            name=f"E2E Critical Flow {suffix}",
            description="Playwright approval + resume path",
            category="integration",
            is_template=False,
        )
        db.add(workflow)
        await db.flush()
        version_service = WorkflowVersionService(db)
        await version_service.ensure_draft(
            workflow,
            nodes=nodes,
            edges=[],
            entry_node_id="write-1",
            created_by=user_id,
        )
        await db.commit()
        await db.refresh(workflow)

        return {
            "workflowId": workflow.id,
            "workflowName": workflow.name,
            "workflowSlug": workflow.slug,
            "connectorInstallationId": telegram.id,
            "fixtureInput": {"connector_installation_id": telegram.id, "note": "e2e fixture"},
        }


async def _seed_email_approval(user_id: str) -> dict[str, str]:
    effect = build_proposed_effect(
        action_key="tool:gmail.send_draft",
        raw_arguments={
            "subject": "Re: Question",
            "body_text": "Original draft body",
            "to": ["customer@example.com"],
        },
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    approval = ApprovalRequest(
        requested_by_user_id=user_id,
        approval_type="tool:gmail.send_draft",
        status="pending",
        payload_json={
            "owner_id": user_id,
            "action_key": "tool:gmail.send_draft",
            "email": {
                "from": {"email": "customer@example.com"},
                "subject": "Question",
                "text_body": "Can you help?",
            },
            "draft_arguments": {
                "subject": "Re: Question",
                "body_text": "Original draft body",
                "to": ["customer@example.com"],
            },
        },
    )
    apply_proposed_effect_to_approval(approval, effect)
    async with SessionLocal() as db:
        db.add(approval)
        await db.commit()
        await db.refresh(approval)
        return {"approvalId": approval.id}


async def _run(mode: str, *, user_id: str | None) -> dict[str, Any]:
    if mode == "credentials":
        return await _create_verified_user()
    if not user_id:
        raise SystemExit("--user-id is required for this mode")
    if mode == "stale-approval":
        return await _seed_stale_approval(user_id)
    if mode == "email-approval":
        return await _seed_email_approval(user_id)
    if mode == "reauth-connector":
        return await _seed_reauth_connector(user_id)
    if mode == "critical-flow":
        return await _seed_critical_flow(user_id)
    raise SystemExit(f"Unknown mode: {mode}")


def main() -> None:
    parser = argparse.ArgumentParser(description="Seed Playwright E2E fixtures")
    parser.add_argument(
        "mode",
        choices=("credentials", "stale-approval", "email-approval", "reauth-connector", "critical-flow"),
    )
    parser.add_argument("--user-id", dest="user_id", default=None)
    parser.add_argument("--output", dest="output", default=None)
    args = parser.parse_args()

    payload = asyncio.run(_run(args.mode, user_id=args.user_id))
    encoded = json.dumps(payload, indent=2)
    if args.output:
        path = Path(args.output)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(encoded + "\n", encoding="utf-8")
    else:
        sys.stdout.write(encoded + "\n")


if __name__ == "__main__":
    main()
