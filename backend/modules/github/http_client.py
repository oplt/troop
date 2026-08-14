"""GitHub REST HTTP client helpers (auth + request transport)."""

from __future__ import annotations

import time
from typing import Any

import httpx
import jwt
from fastapi import HTTPException

from backend.core.config import settings
from backend.core.external_http import external_headers
from backend.core.http_clients import managed_http_client
from backend.modules.github.models import GithubConnection
from backend.modules.orchestration.security import decrypt_secret


def connection_mode(connection: GithubConnection) -> str:
    return str((connection.metadata_json or {}).get("connection_mode") or "token")


def app_jwt() -> str:
    if not settings.GITHUB_APP_ID or not settings.GITHUB_APP_PRIVATE_KEY:
        raise HTTPException(status_code=503, detail="GitHub App credentials are not configured")
    now = int(time.time())
    return jwt.encode(
        {"iat": now - 60, "exp": now + 540, "iss": settings.GITHUB_APP_ID},
        settings.GITHUB_APP_PRIVATE_KEY,
        algorithm="RS256",
    )


async def app_get_installation(
    installation_id: int,
    *,
    api_url: str = "https://api.github.com",
) -> dict[str, Any]:
    async with managed_http_client(
        "github",
        timeout_seconds=30.0,
        base_url=api_url,
    ) as client:
        response = await client.get(
            f"/app/installations/{installation_id}",
            headers=external_headers(
                {
                    "Authorization": f"Bearer {app_jwt()}",
                    "Accept": "application/vnd.github+json",
                }
            ),
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Failed to read GitHub App installation")
    return response.json()


async def installation_token(connection: GithubConnection) -> str:
    installation_id = int((connection.metadata_json or {}).get("installation_id") or 0)
    if installation_id <= 0:
        raise HTTPException(
            status_code=422, detail="GitHub App connection is missing installation_id"
        )
    async with managed_http_client(
        "github",
        timeout_seconds=30.0,
        base_url=connection.api_url,
    ) as client:
        response = await client.post(
            f"/app/installations/{installation_id}/access_tokens",
            headers=external_headers(
                {
                    "Authorization": f"Bearer {app_jwt()}",
                    "Accept": "application/vnd.github+json",
                }
            ),
        )
    if response.status_code >= 400:
        raise HTTPException(status_code=502, detail="Failed to mint GitHub installation token")
    return str(response.json()["token"])


async def auth_headers(connection: GithubConnection) -> dict[str, str]:
    token = (
        await installation_token(connection)
        if connection_mode(connection) == "github_app"
        else decrypt_secret(connection.encrypted_token)
    )
    return {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }


async def github_request(
    connection: GithubConnection,
    method: str,
    path: str,
    *,
    params: dict[str, Any] | None = None,
    json_body: dict[str, Any] | None = None,
) -> httpx.Response:
    headers = await auth_headers(connection)
    async with managed_http_client(
        "github",
        timeout_seconds=30.0,
        base_url=connection.api_url,
    ) as client:
        return await client.request(
            method,
            path,
            headers=external_headers(headers),
            params=params,
            json=json_body,
        )
