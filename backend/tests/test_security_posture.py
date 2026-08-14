"""Tests for SEC-004 security posture audit."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

from backend.core.config import settings
from backend.modules.admin.security_posture import (
    run_config_checks,
    run_database_checks,
    run_security_posture_audit,
)
from backend.modules.workforce.services.action_policy import DECISION_AUTONOMOUS


def _prod_settings(**updates):
    base = {
        "APP_ENV": "production",
        "STORAGE_BUCKET": "private-artifacts",
        "STORAGE_PUBLIC_READ": False,
        "SECRETS_ENCRYPTION_KEY": "dedicated-fernet-key",
        "ORCHESTRATION_CPU_REQUIRE_DOCKER": True,
        "GITHUB_APP_WEBHOOK_SECRET": "github-secret",
        "TELEGRAM_WEBHOOK_SECRET": "",
        "TELEGRAM_WEBHOOK_BASE_URL": "",
        "STORAGE_PUBLIC_BASE_URL": "",
        "STORAGE_PUBLIC_ASSET_BUCKET": "",
    }
    base.update(updates)
    return settings.model_copy(update=base)


def test_config_checks_flag_public_storage_and_missing_key() -> None:
    cfg = _prod_settings(STORAGE_PUBLIC_READ=True, SECRETS_ENCRYPTION_KEY="")
    findings = run_config_checks(cfg)
    check_ids = {item.check_id for item in findings}
    assert "storage_public_read" in check_ids
    assert "missing_secrets_encryption_key" in check_ids


def test_config_checks_flag_host_sandbox_override() -> None:
    cfg = _prod_settings(ORCHESTRATION_CPU_REQUIRE_DOCKER=False)
    findings = run_config_checks(cfg)
    assert any(item.check_id == "host_code_sandbox_override" for item in findings)


def test_config_checks_flag_unsigned_telegram_webhook() -> None:
    cfg = _prod_settings(
        TELEGRAM_WEBHOOK_BASE_URL="https://example.com/api/v1/workforce/integrations/telegram/webhook",
        TELEGRAM_WEBHOOK_SECRET="",
    )
    findings = run_config_checks(cfg)
    assert any(item.check_id == "telegram_webhook_unsigned" for item in findings)


def _scalar_result(rows):
    result = MagicMock()
    result.all.return_value = rows
    result.scalars.return_value = MagicMock(all=lambda: [row for row in rows if not isinstance(row, tuple)])
    return result


@pytest.mark.asyncio
async def test_database_checks_detect_connector_and_policy_risks() -> None:
    expired = (datetime.now(UTC) - timedelta(hours=1)).isoformat()
    gmail_installation = SimpleNamespace(
        id="conn-gmail",
        name="Primary Gmail",
        status="active",
        secrets_ref="enc",
        config_json={"granted_scopes": ["https://www.googleapis.com/auth/gmail.send"], "token_expires_at": expired},
    )
    gmail_definition = SimpleNamespace(slug="gmail", provider_type="native")
    mcp_installation = SimpleNamespace(
        id="conn-mcp",
        name="Public MCP",
        status="active",
        secrets_ref=None,
        config_json={"base_url": "http://mcp.internal/tools"},
    )
    mcp_definition = SimpleNamespace(slug="custom-mcp", provider_type="mcp")
    autonomous_policy = SimpleNamespace(
        id="policy-1",
        action_key="gmail.send_draft",
        scope_type="organization",
        decision=DECISION_AUTONOMOUS,
        risk_level="high",
    )
    risky_tool = SimpleNamespace(
        id="tool-1",
        slug="gmail.send_draft",
        requires_approval=False,
        risk_level="high",
        is_active=True,
    )

    db = AsyncMock()

    async def execute(stmt):
        sql = str(stmt)
        if "connector_installations" in sql:
            return _scalar_result([(gmail_installation, gmail_definition), (mcp_installation, mcp_definition)])
        if "action_policies" in sql:
            return _scalar_result([autonomous_policy])
        if "tool_definitions" in sql:
            result = MagicMock()
            result.scalars.return_value = MagicMock(all=lambda: [risky_tool])
            return result
        if "webhook_endpoints" in sql:
            return _scalar_result([])
        if "github_connections" in sql:
            result = MagicMock()
            result.scalars.return_value = MagicMock(all=lambda: [])
            return result
        return _scalar_result([])

    db.execute = execute

    findings = await run_database_checks(db, _prod_settings())
    check_ids = {item.check_id for item in findings}
    assert "stale_credentials" in check_ids
    assert "broad_oauth_scopes" in check_ids
    assert "exposed_mcp_tools" in check_ids
    assert "high_risk_autonomous_policy" in check_ids
    assert "high_risk_tool_without_approval" in check_ids


@pytest.mark.asyncio
async def test_run_security_posture_audit_sorts_by_severity() -> None:
    db = AsyncMock()
    db.execute = AsyncMock(return_value=_scalar_result([]))
    cfg = _prod_settings(STORAGE_PUBLIC_READ=True, SECRETS_ENCRYPTION_KEY="")
    report = await run_security_posture_audit(db, cfg=cfg)
    assert report.summary["critical"] >= 2
    assert report.findings[0].severity == "critical"
