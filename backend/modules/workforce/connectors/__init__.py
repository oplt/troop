"""Connector manifest SDK — schema, provider contract, and registry."""

from backend.modules.workforce.connectors.builtins import (
    build_gmail_manifest,
    build_telegram_manifest,
    register_builtin_manifests,
    register_builtin_providers,
)
from backend.modules.workforce.connectors.manifest import (
    AuthStrategyType,
    ConnectorAuthManifest,
    ConnectorManifest,
    ConnectorOperationManifest,
    ConnectorScopeManifest,
    HealthProbeManifest,
    OperationKind,
    RateLimitManifest,
    ReauthorizationBehavior,
    WebhookManifest,
    WebhookVerificationStrategy,
)
from backend.modules.workforce.connectors.provider import (
    ConnectorActionResult,
    ConnectorAuthContext,
    ConnectorAuthResult,
    ConnectorHealthResult,
    ConnectorNormalizedEvent,
    ConnectorProvider,
    ConnectorTriggerRegistration,
    provider_implements_contract,
)
from backend.modules.workforce.connectors.registry import ConnectorManifestRegistry

__all__ = [
    "AuthStrategyType",
    "ConnectorActionResult",
    "ConnectorAuthContext",
    "ConnectorAuthManifest",
    "ConnectorAuthResult",
    "ConnectorHealthResult",
    "ConnectorManifest",
    "ConnectorManifestRegistry",
    "ConnectorNormalizedEvent",
    "ConnectorOperationManifest",
    "ConnectorProvider",
    "ConnectorScopeManifest",
    "ConnectorTriggerRegistration",
    "HealthProbeManifest",
    "OperationKind",
    "RateLimitManifest",
    "ReauthorizationBehavior",
    "WebhookManifest",
    "WebhookVerificationStrategy",
    "build_gmail_manifest",
    "build_telegram_manifest",
    "provider_implements_contract",
    "register_builtin_manifests",
    "register_builtin_providers",
]

register_builtin_manifests()
register_builtin_providers()
