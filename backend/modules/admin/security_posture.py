"""Deployment and policy security posture checks for operators."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.core.config import Settings, settings
from backend.modules.github.models import GithubConnection
from backend.modules.orchestration.execution.cpu_executor import docker_available
from backend.modules.orchestration.external_effect_inventory import (
    get_external_effect_contract,
    list_external_effect_contracts,
)
from backend.modules.platform.models import WebhookEndpoint
from backend.modules.workforce.action_metadata import SideEffect
from backend.modules.workforce.models import ActionPolicy, ConnectorDefinition, ConnectorInstallation, ToolDefinition
from backend.modules.workforce.services.action_policy import DECISION_AUTONOMOUS

SEVERITY_ORDER = ("critical", "high", "medium", "low", "info")

HIGH_PRIVILEGE_GMAIL_SCOPES = frozenset(
    {
        "https://mail.google.com/",
        "https://www.googleapis.com/auth/gmail.send",
    }
)

REMEDIATION_LINKS: dict[str, str] = {
    "storage": "/admin/settings?tab=database",
    "secrets": "/admin/settings?tab=database",
    "sandbox": "/admin/settings?tab=database",
    "connectors": "/admin/settings?tab=github_sync",
    "policies": "/policies",
    "webhooks": "/admin/settings?tab=platform",
    "github": "/admin/settings?tab=github_sync",
}


@dataclass(slots=True)
class SecurityFinding:
    check_id: str
    severity: str
    title: str
    summary: str
    remediation: str
    remediation_url: str | None = None
    resource_type: str | None = None
    resource_id: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "check_id": self.check_id,
            "severity": self.severity,
            "title": self.title,
            "summary": self.summary,
            "remediation": self.remediation,
            "remediation_url": self.remediation_url,
            "resource_type": self.resource_type,
            "resource_id": self.resource_id,
            "metadata": self.metadata,
        }


@dataclass(slots=True)
class SecurityPostureReport:
    generated_at: datetime
    environment: str
    summary: dict[str, int]
    findings: list[SecurityFinding]

    def to_dict(self) -> dict[str, Any]:
        return {
            "generated_at": self.generated_at.isoformat(),
            "environment": self.environment,
            "summary": self.summary,
            "findings": [item.to_dict() for item in self.findings],
        }


def _summarize(findings: list[SecurityFinding]) -> dict[str, int]:
    counts = {severity: 0 for severity in SEVERITY_ORDER}
    for item in findings:
        counts[item.severity] = counts.get(item.severity, 0) + 1
    counts["total"] = len(findings)
    return counts


def run_config_checks(cfg: Settings | None = None) -> list[SecurityFinding]:
    """Environment-level checks that do not require database access."""
    cfg = cfg or settings
    findings: list[SecurityFinding] = []

    if cfg.is_production and cfg.STORAGE_BUCKET and cfg.STORAGE_PUBLIC_READ:
        findings.append(
            SecurityFinding(
                check_id="storage_public_read",
                severity="critical",
                title="Primary artifact bucket allows public reads",
                summary=(
                    "STORAGE_PUBLIC_READ is enabled for the primary artifact bucket in production. "
                    "Private run artifacts and documents may be world-readable."
                ),
                remediation=(
                    "Set STORAGE_PUBLIC_READ=false on the primary bucket. "
                    "Use STORAGE_PUBLIC_ASSET_BUCKET only for intentionally public assets."
                ),
                remediation_url=REMEDIATION_LINKS["storage"],
                resource_type="setting",
                resource_id="STORAGE_PUBLIC_READ",
            )
        )

    if (
        cfg.is_production
        and cfg.STORAGE_PUBLIC_BASE_URL
        and cfg.STORAGE_BUCKET
        and not cfg.STORAGE_PUBLIC_ASSET_BUCKET
    ):
        findings.append(
            SecurityFinding(
                check_id="storage_public_base_misconfigured",
                severity="high",
                title="Public storage base URL points at private bucket",
                summary=(
                    "STORAGE_PUBLIC_BASE_URL is set without a separate STORAGE_PUBLIC_ASSET_BUCKET. "
                    "Presigned private object URLs may be replaced with permanent public URLs."
                ),
                remediation=(
                    "Clear STORAGE_PUBLIC_BASE_URL or configure STORAGE_PUBLIC_ASSET_BUCKET "
                    "for assets that must be permanently public."
                ),
                remediation_url=REMEDIATION_LINKS["storage"],
                resource_type="setting",
                resource_id="STORAGE_PUBLIC_BASE_URL",
            )
        )

    if cfg.is_production and not (cfg.SECRETS_ENCRYPTION_KEY or "").strip():
        findings.append(
            SecurityFinding(
                check_id="missing_secrets_encryption_key",
                severity="critical",
                title="Secrets encryption key is not configured",
                summary="SECRETS_ENCRYPTION_KEY is required in production for connector and webhook secrets.",
                remediation=(
                    "Generate a dedicated Fernet key, set SECRETS_ENCRYPTION_KEY, "
                    "and run backend/tools/rotate_secrets_encryption.py after rotation."
                ),
                remediation_url=REMEDIATION_LINKS["secrets"],
                resource_type="setting",
                resource_id="SECRETS_ENCRYPTION_KEY",
            )
        )

    docker_required = cfg.orchestration_cpu_require_docker
    if cfg.is_production and cfg.ORCHESTRATION_CPU_REQUIRE_DOCKER is False:
        findings.append(
            SecurityFinding(
                check_id="host_code_sandbox_override",
                severity="critical",
                title="Production allows host code execution fallback",
                summary=(
                    "ORCHESTRATION_CPU_REQUIRE_DOCKER=false disables Docker sandboxing for CPU code jobs."
                ),
                remediation="Remove the override or set ORCHESTRATION_CPU_REQUIRE_DOCKER=true in production.",
                remediation_url=REMEDIATION_LINKS["sandbox"],
                resource_type="setting",
                resource_id="ORCHESTRATION_CPU_REQUIRE_DOCKER",
            )
        )
    elif docker_required and not docker_available():
        findings.append(
            SecurityFinding(
                check_id="docker_sandbox_unavailable",
                severity="high" if cfg.is_production else "medium",
                title="Docker sandbox required but unavailable",
                summary=(
                    "Code execution requires Docker but `docker info` failed. "
                    "Jobs may fail or fall back to host execution in non-production."
                ),
                remediation="Install and start Docker on worker nodes or adjust ORCHESTRATION_CPU_REQUIRE_DOCKER for dev only.",
                remediation_url=REMEDIATION_LINKS["sandbox"],
                resource_type="runtime",
                resource_id="docker",
            )
        )

    if cfg.TELEGRAM_WEBHOOK_BASE_URL and not cfg.TELEGRAM_WEBHOOK_SECRET:
        findings.append(
            SecurityFinding(
                check_id="telegram_webhook_unsigned",
                severity="high",
                title="Telegram webhook URL configured without secret token",
                summary="TELEGRAM_WEBHOOK_BASE_URL is set but TELEGRAM_WEBHOOK_SECRET is empty.",
                remediation="Set TELEGRAM_WEBHOOK_SECRET to a high-entropy value and redeploy webhook registration.",
                remediation_url=REMEDIATION_LINKS["webhooks"],
                resource_type="setting",
                resource_id="TELEGRAM_WEBHOOK_SECRET",
            )
        )

    return findings


def _installation_has_auth(installation: ConnectorInstallation) -> bool:
    config = installation.config_json or {}
    if installation.secrets_ref:
        return True
    return bool(config.get("auth_token") or config.get("api_key"))


def _parse_expires_at(raw: Any) -> datetime | None:
    if not raw:
        return None
    try:
        parsed = datetime.fromisoformat(str(raw))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


async def run_database_checks(db: AsyncSession, cfg: Settings | None = None) -> list[SecurityFinding]:
    """Workspace and connector policy checks requiring database access."""
    cfg = cfg or settings
    findings: list[SecurityFinding] = []
    now = datetime.now(UTC)

    connector_pairs = list(
        (
            await db.execute(
                select(ConnectorInstallation, ConnectorDefinition).join(
                    ConnectorDefinition,
                    ConnectorDefinition.id == ConnectorInstallation.connector_definition_id,
                )
            )
        ).all()
    )
    for installation, definition in connector_pairs:
        if installation.status == "reauthorization_required":
            findings.append(
                SecurityFinding(
                    check_id="stale_credentials",
                    severity="high",
                    title="Connector requires reauthorization",
                    summary=f"{definition.slug} installation '{installation.name}' is marked reauthorization_required.",
                    remediation="Reconnect the integration from Connectors and verify OAuth scopes.",
                    remediation_url=REMEDIATION_LINKS["connectors"],
                    resource_type="connector_installation",
                    resource_id=installation.id,
                    metadata={"connector_slug": definition.slug},
                )
            )
            continue

        if installation.status != "active":
            continue

        expires_at = _parse_expires_at((installation.config_json or {}).get("token_expires_at"))
        if expires_at and expires_at <= now:
            findings.append(
                SecurityFinding(
                    check_id="stale_credentials",
                    severity="high",
                    title="Connector OAuth token expired",
                    summary=f"{definition.slug} installation '{installation.name}' has an expired access token.",
                    remediation="Reconnect or trigger token refresh for the connector installation.",
                    remediation_url=REMEDIATION_LINKS["connectors"],
                    resource_type="connector_installation",
                    resource_id=installation.id,
                    metadata={"connector_slug": definition.slug, "token_expires_at": expires_at.isoformat()},
                )
            )

        if definition.slug == "gmail":
            granted = set((installation.config_json or {}).get("granted_scopes") or [])
            broad = sorted(granted.intersection(HIGH_PRIVILEGE_GMAIL_SCOPES))
            if broad:
                findings.append(
                    SecurityFinding(
                        check_id="broad_oauth_scopes",
                        severity="medium",
                        title="Gmail connector granted high-privilege scopes",
                        summary=(
                            f"Installation '{installation.name}' includes send/full-mailbox scopes: {', '.join(broad)}."
                        ),
                        remediation=(
                            "Reconnect Gmail requesting least-privilege scopes for the workflows in use "
                            "(readonly/modify/compose before send)."
                        ),
                        remediation_url=REMEDIATION_LINKS["connectors"],
                        resource_type="connector_installation",
                        resource_id=installation.id,
                        metadata={"granted_scopes": broad},
                    )
                )

        if definition.provider_type == "mcp":
            config = installation.config_json or {}
            base_url = str(config.get("base_url") or config.get("url") or "").strip()
            parsed = urlparse(base_url) if base_url else None
            if parsed and parsed.scheme == "http":
                findings.append(
                    SecurityFinding(
                        check_id="exposed_mcp_tools",
                        severity="high",
                        title="MCP connector uses cleartext HTTP",
                        summary=f"MCP installation '{installation.name}' targets {base_url}.",
                        remediation="Use HTTPS for MCP server endpoints or restrict to private network tunnels.",
                        remediation_url=REMEDIATION_LINKS["connectors"],
                        resource_type="connector_installation",
                        resource_id=installation.id,
                        metadata={"base_url": base_url},
                    )
                )
            if base_url and not _installation_has_auth(installation):
                findings.append(
                    SecurityFinding(
                        check_id="exposed_mcp_tools",
                        severity="high",
                        title="MCP connector has no authentication configured",
                        summary=f"MCP installation '{installation.name}' exposes tools without auth_token/api_key.",
                        remediation="Configure bearer auth or mTLS before enabling MCP tools in production workflows.",
                        remediation_url=REMEDIATION_LINKS["connectors"],
                        resource_type="connector_installation",
                        resource_id=installation.id,
                        metadata={"base_url": base_url or None},
                    )
                )

    policy_rows = await db.execute(
        select(ActionPolicy).where(ActionPolicy.decision == DECISION_AUTONOMOUS)
    )
    high_risk_keys = {
        contract.action_key
        for contract in list_external_effect_contracts()
        if contract.side_effect == SideEffect.EXTERNAL_MUTATING
        or contract.risk_level in {"high", "critical"}
    }
    for policy in policy_rows.scalars().all():
        action_key = policy.action_key
        if action_key not in high_risk_keys and policy.risk_level not in {"high", "critical"}:
            continue
        contract = get_external_effect_contract(action_key)
        if contract and "approval_required" not in contract.approval_rule.lower():
            continue
        findings.append(
            SecurityFinding(
                check_id="high_risk_autonomous_policy",
                severity="high",
                title="High-risk action allowed autonomously",
                summary=(
                    f"Action policy grants autonomous execution for '{action_key}' "
                    f"at {policy.scope_type} scope."
                ),
                remediation="Change the action policy to approval_required or prohibit the action.",
                remediation_url=REMEDIATION_LINKS["policies"],
                resource_type="action_policy",
                resource_id=policy.id,
                metadata={"action_key": action_key, "scope_type": policy.scope_type},
            )
        )

    tool_rows = await db.execute(
        select(ToolDefinition).where(
            ToolDefinition.is_active.is_(True),
            ToolDefinition.requires_approval.is_(False),
        )
    )
    for tool in tool_rows.scalars().all():
        contract = get_external_effect_contract(tool.slug)
        if not contract:
            continue
        if contract.side_effect != SideEffect.EXTERNAL_MUTATING and tool.risk_level not in {
            "high",
            "critical",
        }:
            continue
        if "approval_required" not in contract.approval_rule.lower():
            continue
        findings.append(
            SecurityFinding(
                check_id="high_risk_tool_without_approval",
                severity="high",
                title="High-risk tool missing approval requirement",
                summary=(
                    f"Tool '{tool.slug}' is active with requires_approval=false "
                    f"but the external-effect contract expects human approval."
                ),
                remediation="Enable requires_approval on the tool definition or add an approval_required policy.",
                remediation_url=REMEDIATION_LINKS["policies"],
                resource_type="tool_definition",
                resource_id=tool.id,
                metadata={"tool_slug": tool.slug, "risk_level": tool.risk_level},
            )
        )

    webhook_rows = await db.execute(select(WebhookEndpoint).where(WebhookEndpoint.is_active.is_(True)))
    for webhook in webhook_rows.scalars().all():
        parsed = urlparse(webhook.target_url or "")
        if cfg.is_production and parsed.scheme == "http":
            findings.append(
                SecurityFinding(
                    check_id="unsafe_webhook_config",
                    severity="medium",
                    title="Outbound webhook uses cleartext HTTP",
                    summary=f"Webhook {webhook.id} delivers events to {webhook.target_url}.",
                    remediation="Use HTTPS targets for outbound webhook delivery in production.",
                    remediation_url=REMEDIATION_LINKS["webhooks"],
                    resource_type="webhook_endpoint",
                    resource_id=webhook.id,
                )
            )
        if not (webhook.secret or "").strip():
            findings.append(
                SecurityFinding(
                    check_id="unsafe_webhook_config",
                    severity="high",
                    title="Outbound webhook missing signing secret",
                    summary=f"Webhook {webhook.id} has no stored signing secret.",
                    remediation="Rotate the webhook endpoint and store an encrypted signing secret.",
                    remediation_url=REMEDIATION_LINKS["webhooks"],
                    resource_type="webhook_endpoint",
                    resource_id=webhook.id,
                )
            )

    github_rows = await db.execute(
        select(GithubConnection).where(GithubConnection.is_active.is_(True))
    )
    active_github = list(github_rows.scalars().all())
    if active_github and cfg.is_production and not (cfg.GITHUB_APP_WEBHOOK_SECRET or "").strip():
        findings.append(
            SecurityFinding(
                check_id="unsafe_webhook_config",
                severity="high",
                title="GitHub App webhook secret is not configured",
                summary=(
                    f"{len(active_github)} active GitHub connection(s) exist but "
                    "GITHUB_APP_WEBHOOK_SECRET is empty."
                ),
                remediation="Configure GITHUB_APP_WEBHOOK_SECRET to validate inbound GitHub webhook signatures.",
                remediation_url=REMEDIATION_LINKS["github"],
                resource_type="setting",
                resource_id="GITHUB_APP_WEBHOOK_SECRET",
            )
        )

    telegram_installations = [
        installation
        for installation, definition in connector_pairs
        if definition.slug == "telegram" and installation.status == "active"
    ]
    if telegram_installations and not cfg.TELEGRAM_WEBHOOK_SECRET:
        findings.append(
            SecurityFinding(
                check_id="unsafe_webhook_config",
                severity="medium",
                title="Active Telegram connector without webhook secret",
                summary=(
                    f"{len(telegram_installations)} active Telegram installation(s) "
                    "but TELEGRAM_WEBHOOK_SECRET is unset."
                ),
                remediation="Configure TELEGRAM_WEBHOOK_SECRET before accepting Telegram webhook callbacks.",
                remediation_url=REMEDIATION_LINKS["webhooks"],
                resource_type="setting",
                resource_id="TELEGRAM_WEBHOOK_SECRET",
            )
        )

    return findings


async def run_security_posture_audit(
    db: AsyncSession | None = None,
    *,
    cfg: Settings | None = None,
) -> SecurityPostureReport:
    cfg = cfg or settings
    findings = run_config_checks(cfg)
    if db is not None:
        findings.extend(await run_database_checks(db, cfg))
    findings.sort(
        key=lambda item: (
            SEVERITY_ORDER.index(item.severity) if item.severity in SEVERITY_ORDER else 99,
            item.check_id,
            item.title,
        )
    )
    return SecurityPostureReport(
        generated_at=datetime.now(UTC),
        environment=cfg.APP_ENV,
        summary=_summarize(findings),
        findings=findings,
    )
