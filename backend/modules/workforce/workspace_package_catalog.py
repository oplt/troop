"""Private workspace package permission manifests, signing, and diffs (MKT-001)."""

from __future__ import annotations

import hashlib
import hmac
import json
from typing import Any

from backend.core.config import settings

PUBLIC_MARKETPLACE_ENABLED = False


def canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def content_hash(payload: dict[str, Any]) -> str:
    return hashlib.sha256(canonical_json(payload).encode("utf-8")).hexdigest()


def sign_workspace_package(*, content_digest: str, signer_user_id: str) -> dict[str, Any]:
    secret = (settings.SECRETS_ENCRYPTION_KEY or settings.JWT_SECRET or "").encode("utf-8")
    message = f"{content_digest}:{signer_user_id}".encode("utf-8")
    signature = hmac.new(secret, message, hashlib.sha256).hexdigest() if secret else ""
    return {
        "content_hash": content_digest,
        "signature_scheme": "workspace_hmac_sha256" if signature else "unsigned",
        "signature": signature or None,
        "trust_level": "workspace_private",
        "review_status": "not_submitted",
        "public_publish_allowed": False,
    }


def verify_workspace_package_signature(
    *, content_digest: str, signer_user_id: str, trust: dict[str, Any]
) -> bool:
    if trust.get("signature_scheme") == "unsigned":
        return False
    expected = sign_workspace_package(content_digest=content_digest, signer_user_id=signer_user_id)
    return hmac.compare_digest(str(trust.get("signature") or ""), str(expected.get("signature") or ""))


def _sorted_unique(values: Any) -> list[str]:
    if not isinstance(values, (list, tuple, set)):
        return []
    seen: list[str] = []
    for item in values:
        text = str(item).strip()
        if text and text not in seen:
            seen.append(text)
    return sorted(seen)


def extract_permission_manifest(payload: dict[str, Any], *, kind: str) -> dict[str, Any]:
    """Derive install-time permissions from a package payload snapshot."""
    manifest: dict[str, Any] = {
        "required_tools": _sorted_unique(payload.get("required_tools")),
        "allowed_tools": _sorted_unique(payload.get("allowed_tools")),
        "connector_slugs": _sorted_unique(payload.get("connector_slugs")),
        "oauth_scopes": _sorted_unique(payload.get("oauth_scopes")),
        "external_writes": _sorted_unique(payload.get("external_writes")),
    }
    if kind == "workflow":
        nodes = payload.get("nodes") if isinstance(payload.get("nodes"), list) else []
        tools: list[str] = []
        connectors: list[str] = []
        writes: list[str] = []
        for node in nodes:
            if not isinstance(node, dict):
                continue
            config = node.get("config") if isinstance(node.get("config"), dict) else {}
            tool_slug = str(config.get("tool_slug") or "").strip()
            if tool_slug:
                tools.append(tool_slug)
            connector_slug = str(config.get("connector_slug") or "").strip()
            if connector_slug:
                connectors.append(connector_slug)
            if config.get("requires_approval") or config.get("approval_required"):
                writes.append(tool_slug or str(node.get("id") or "node"))
        manifest["required_tools"] = _sorted_unique([*manifest["required_tools"], *tools])
        manifest["connector_slugs"] = _sorted_unique([*manifest["connector_slugs"], *connectors])
        manifest["external_writes"] = _sorted_unique([*manifest["external_writes"], *writes])
    return manifest


def diff_permission_manifests(
    previous: dict[str, Any] | None,
    current: dict[str, Any],
) -> dict[str, Any]:
    prev = previous or {}
    added: dict[str, list[str]] = {}
    removed: dict[str, list[str]] = {}
    for key in ("required_tools", "allowed_tools", "connector_slugs", "oauth_scopes", "external_writes"):
        before = set(_sorted_unique(prev.get(key)))
        after = set(_sorted_unique(current.get(key)))
        added_items = sorted(after - before)
        removed_items = sorted(before - after)
        if added_items:
            added[key] = added_items
        if removed_items:
            removed[key] = removed_items
    has_escalation = bool(added.get("required_tools") or added.get("connector_slugs") or added.get("oauth_scopes") or added.get("external_writes"))
    return {
        "added": added,
        "removed": removed,
        "has_escalation": has_escalation,
        "requires_explicit_acceptance": has_escalation,
    }


def marketplace_policy() -> dict[str, Any]:
    return {
        "public_marketplace_enabled": PUBLIC_MARKETPLACE_ENABLED,
        "private_workspace_packages_enabled": True,
        "requires_signed_versions": True,
        "requires_permission_diff_on_upgrade": True,
        "deferred": ["public_publish", "community_reviews", "cross_tenant_install"],
    }
