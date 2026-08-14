"""Tests for private workspace package catalog (MKT-001)."""

from __future__ import annotations

import pytest

from backend.modules.workforce.routers import marketplace as marketplace_router
from backend.modules.workforce.workspace_package_catalog import (
    diff_permission_manifests,
    extract_permission_manifest,
    marketplace_policy,
    sign_workspace_package,
    verify_workspace_package_signature,
)


def test_marketplace_policy_defers_public_publishing():
    policy = marketplace_policy()
    assert policy["public_marketplace_enabled"] is False
    assert policy["private_workspace_packages_enabled"] is True
    assert policy["requires_permission_diff_on_upgrade"] is True


def test_permission_diff_detects_new_tools():
    previous = {"required_tools": ["knowledge_search"], "connector_slugs": [], "oauth_scopes": []}
    current = {
        "required_tools": ["knowledge_search", "gmail.send_draft"],
        "connector_slugs": ["gmail"],
        "oauth_scopes": ["https://mail.google.com/"],
    }
    diff = diff_permission_manifests(previous, current)
    assert diff["has_escalation"] is True
    assert "gmail.send_draft" in diff["added"]["required_tools"]
    assert "gmail" in diff["added"]["connector_slugs"]


def test_permission_diff_allows_no_escalation():
    manifest = extract_permission_manifest(
        {"required_tools": ["repo_search"], "nodes": []},
        kind="skill",
    )
    diff = diff_permission_manifests(manifest, manifest)
    assert diff["has_escalation"] is False
    assert diff["requires_explicit_acceptance"] is False


def test_workflow_manifest_extracts_tool_nodes():
    manifest = extract_permission_manifest(
        {
            "nodes": [
                {
                    "id": "send",
                    "config": {"tool_slug": "gmail.send_draft", "requires_approval": True},
                },
            ]
        },
        kind="workflow",
    )
    assert "gmail.send_draft" in manifest["required_tools"]
    assert "gmail.send_draft" in manifest["external_writes"] or "send" in manifest["external_writes"]


def test_workspace_package_signature_roundtrip():
    digest = "abc123"
    trust = sign_workspace_package(content_digest=digest, signer_user_id="user-1")
    assert verify_workspace_package_signature(
        content_digest=digest,
        signer_user_id="user-1",
        trust=trust,
    )


def test_workspace_package_routes_registered():
    from fastapi.routing import APIRoute

    paths = {
        item.path
        for item in marketplace_router.router.routes
        if isinstance(item, APIRoute)
    }
    workspace_paths = {p for p in paths if "workspace-packages" in p}
    assert "/marketplace/workspace-packages" in workspace_paths
    assert "/marketplace/workspace-packages/import" in workspace_paths
    assert "/marketplace/workspace-packages/{package_id}/install" in workspace_paths
    assert "/marketplace/policy" in paths
