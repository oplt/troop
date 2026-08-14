"""Manifest discovery API for schema-driven connector UI."""

from __future__ import annotations

import pytest
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_list_connector_manifests_returns_builtin_providers(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/workforce/connectors/manifests")
    assert response.status_code == 200
    slugs = {item["provider_slug"] for item in response.json()}
    assert slugs >= {"gmail", "outlook", "google_calendar", "microsoft_calendar", "telegram", "slack", "teams"}


@pytest.mark.asyncio
async def test_get_connector_manifest_includes_scope_labels(auth_client: AsyncClient) -> None:
    response = await auth_client.get("/api/v1/workforce/connectors/manifests/gmail")
    assert response.status_code == 200
    body = response.json()
    assert body["auth"]["pkce_required"] is True
    assert any(scope.get("label") == "Read mail" for scope in body["auth"]["scopes"])
    assert any(action["slug"] == "gmail.send_draft" for action in body["actions"])
