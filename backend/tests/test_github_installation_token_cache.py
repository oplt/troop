"""PERF-004: GitHub App installation token caching."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from backend.modules.github.http_client import auth_headers, github_request, installation_token
from backend.modules.github.installation_token_cache import (
    clear_installation_token_cache,
    get_cached_installation_token,
    parse_installation_token_expiry,
)
from backend.modules.github.models import GithubConnection


@pytest.fixture(autouse=True)
def _github_app_credentials(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("backend.modules.github.http_client.settings.GITHUB_APP_ID", "123")
    monkeypatch.setattr(
        "backend.modules.github.http_client.settings.GITHUB_APP_PRIVATE_KEY",
        "test-key",
    )
    monkeypatch.setattr(
        "backend.modules.github.http_client.app_jwt",
        lambda: "app-jwt-token",
    )


@pytest.fixture(autouse=True)
def _clear_token_cache() -> None:
    clear_installation_token_cache()
    yield
    clear_installation_token_cache()


def _app_connection(**overrides) -> GithubConnection:
    metadata = {"connection_mode": "github_app", "installation_id": 4242}
    metadata.update(overrides.pop("metadata_json", {}) or {})
    return GithubConnection(
        id=overrides.pop("id", "conn-1"),
        owner_id="owner-1",
        name="github-app",
        encrypted_token="enc:unused",
        api_url="https://api.github.com",
        metadata_json=metadata,
        **overrides,
    )


def _token_response(token: str = "ghs_cached_token", *, expires_at: str | None = None) -> MagicMock:
    if expires_at is None:
        expires_at = (datetime.now(UTC) + timedelta(hours=1)).isoformat().replace("+00:00", "Z")
    response = MagicMock(status_code=201)
    response.json.return_value = {"token": token, "expires_at": expires_at}
    return response


@pytest.mark.asyncio
async def test_installation_token_mints_once_for_ten_concurrent_calls() -> None:
    connection = _app_connection()
    client = AsyncMock()
    client.post = AsyncMock(return_value=_token_response())

    with patch("backend.modules.github.http_client.managed_http_client") as managed:
        managed.return_value.__aenter__.return_value = client
        tokens = await asyncio.gather(
            *[installation_token(connection) for _ in range(10)]
        )

    assert tokens == ["ghs_cached_token"] * 10
    assert client.post.await_count == 1


@pytest.mark.asyncio
async def test_installation_token_not_logged(caplog: pytest.LogCaptureFixture) -> None:
    connection = _app_connection()
    client = AsyncMock()
    client.post = AsyncMock(return_value=_token_response("ghs_do_not_log_me"))

    with patch("backend.modules.github.http_client.managed_http_client") as managed:
        managed.return_value.__aenter__.return_value = client
        await installation_token(connection)

    assert "ghs_do_not_log_me" not in caplog.text


@pytest.mark.asyncio
async def test_installation_token_refreshes_after_expiry_margin(monkeypatch) -> None:
    connection = _app_connection()
    client = AsyncMock()

    now = datetime(2026, 1, 1, tzinfo=UTC).timestamp()
    expires_at = datetime.fromtimestamp(now + 3600, tz=UTC).isoformat().replace("+00:00", "Z")
    monkeypatch.setattr(
        "backend.modules.github.installation_token_cache.time.time",
        lambda: now,
    )

    with patch("backend.modules.github.http_client.managed_http_client") as managed:
        managed.return_value.__aenter__.return_value = client
        client.post = AsyncMock(
            side_effect=[
                _token_response("first", expires_at=expires_at),
                _token_response("second", expires_at=expires_at),
            ]
        )
        first = await installation_token(connection)
        assert first == "first"

        inside_margin = now + 3600 - 120
        monkeypatch.setattr(
            "backend.modules.github.installation_token_cache.time.time",
            lambda: inside_margin,
        )
        assert get_cached_installation_token(connection) is None

        second = await installation_token(connection)

    assert second == "second"
    assert client.post.await_count == 2


@pytest.mark.asyncio
async def test_github_request_invalidates_cache_on_401_and_retries_once() -> None:
    connection = _app_connection()
    client = AsyncMock()
    unauthorized = MagicMock(status_code=401)
    ok = MagicMock(status_code=200)
    client.post = AsyncMock(return_value=_token_response("fresh-token"))
    client.request = AsyncMock(side_effect=[unauthorized, ok])

    with patch("backend.modules.github.http_client.managed_http_client") as managed:
        managed.return_value.__aenter__.return_value = client
        response = await github_request(connection, "GET", "/repos/acme/app/issues/1")

    assert response.status_code == 200
    assert client.post.await_count == 2
    assert client.request.await_count == 2


def test_parse_installation_token_expiry_accepts_github_timestamp() -> None:
    payload = {"expires_at": "2026-08-14T12:00:00Z"}
    parsed = parse_installation_token_expiry(payload)
    assert parsed == datetime(2026, 8, 14, 12, 0, tzinfo=UTC).timestamp()


@pytest.mark.asyncio
async def test_auth_headers_reuses_cached_installation_token() -> None:
    connection = _app_connection()
    client = AsyncMock()
    client.post = AsyncMock(return_value=_token_response())

    with patch("backend.modules.github.http_client.managed_http_client") as managed:
        managed.return_value.__aenter__.return_value = client
        await auth_headers(connection)
        await auth_headers(connection)

    assert client.post.await_count == 1
