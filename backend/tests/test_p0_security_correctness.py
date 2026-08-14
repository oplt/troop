"""P0 security/correctness regression tests."""

from __future__ import annotations

import hashlib
import hmac
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from cryptography.fernet import Fernet
from fastapi import Request
from starlette.responses import JSONResponse

from backend.modules.orchestration.security import (
    clear_secrets_fernet_cache,
    decrypt_secret,
    encrypt_secret,
)


def _sign(body: bytes, secret: str) -> str:
    digest = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    return f"sha256={digest}"


@pytest.mark.asyncio
async def test_incident_webhook_rejects_when_unconfigured():
    from backend.modules.orchestration import router as orch_router

    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=b'{"alert":"x"}')
    request.headers = {}
    db = AsyncMock()

    with (
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_SECRET", ""),
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_OWNER_USER_ID", ""),
    ):
        response = await orch_router.incident_webhook(request, db)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 503


@pytest.mark.asyncio
async def test_incident_webhook_rejects_invalid_signature():
    from backend.modules.orchestration import router as orch_router

    body = b'{"alert":"disk"}'
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=body)
    request.headers = {"X-Troop-Signature": "sha256=deadbeef"}
    db = AsyncMock()

    with (
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_SECRET", "whsec-test"),
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_OWNER_USER_ID", "user-1"),
    ):
        response = await orch_router.incident_webhook(request, db)

    assert isinstance(response, JSONResponse)
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_incident_webhook_ignores_body_user_id():
    from backend.modules.orchestration import router as orch_router

    body = json.dumps({"alert": "disk", "user_id": "attacker"}).encode("utf-8")
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=body)
    request.headers = {"X-Troop-Signature": _sign(body, "whsec-test")}
    owner = MagicMock(id="owner-fixed")
    db = AsyncMock()
    db.get = AsyncMock(return_value=owner)
    service = MagicMock()
    service.ingest_incident_alert = AsyncMock(return_value=MagicMock(id="task-1"))

    with (
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_SECRET", "whsec-test"),
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_OWNER_USER_ID", "owner-fixed"),
        patch.object(orch_router, "OrchestrationService", return_value=service),
    ):
        result = await orch_router.incident_webhook(request, db)

    assert result == {"accepted": True, "task_id": "task-1"}
    db.get.assert_awaited_once()
    assert db.get.await_args.args[1] == "owner-fixed"
    payload = service.ingest_incident_alert.await_args.args[1]
    assert "user_id" not in payload


def test_secrets_dedicated_key_encrypts_and_legacy_still_decrypts():
    clear_secrets_fernet_cache()
    dedicated = Fernet.generate_key().decode()
    with (
        patch("backend.modules.orchestration.security.settings.JWT_SECRET", "x" * 40),
        patch("backend.modules.orchestration.security.settings.SECRETS_ENCRYPTION_KEY", ""),
    ):
        clear_secrets_fernet_cache()
        legacy_cipher = encrypt_secret("legacy-token")

    with (
        patch("backend.modules.orchestration.security.settings.JWT_SECRET", "x" * 40),
        patch("backend.modules.orchestration.security.settings.SECRETS_ENCRYPTION_KEY", dedicated),
    ):
        clear_secrets_fernet_cache()
        assert decrypt_secret(legacy_cipher) == "legacy-token"
        fresh = encrypt_secret("fresh-token")
        assert decrypt_secret(fresh) == "fresh-token"

    clear_secrets_fernet_cache()


@pytest.mark.asyncio
async def test_public_rate_limit_applies_to_webhooks_path():
    from backend.api.middleware.public_rate_limit import PublicRateLimitMiddleware

    middleware = PublicRateLimitMiddleware(app=MagicMock())
    request = MagicMock()
    request.url.path = "/webhooks/github"
    request.cookies = {}
    request.headers = {}
    request.client = MagicMock(host="1.2.3.4")

    redis = MagicMock()
    redis.incr = AsyncMock(return_value=999)
    redis.expire = AsyncMock()
    redis.ttl = AsyncMock(return_value=30)

    async def call_next(_request):
        return JSONResponse({"ok": True})

    with (
        patch("backend.api.middleware.public_rate_limit.settings.PUBLIC_RATE_LIMIT_REQUESTS", 10),
        patch("backend.api.middleware.public_rate_limit.redis_client", redis),
    ):
        response = await middleware.dispatch(request, call_next)

    assert response.status_code == 429


def test_approval_owner_clause_requires_requester_for_null_project():
    from backend.modules.orchestration import repository as repo_mod

    # Locate the mixin/class that owns the ACL helper.
    owner = None
    for name in dir(repo_mod):
        obj = getattr(repo_mod, name)
        if isinstance(obj, type) and hasattr(obj, "_approval_owner_clause"):
            owner = obj
            break
    assert owner is not None
    clause = owner._approval_owner_clause("owner-a")
    compiled = str(clause.compile(compile_kwargs={"literal_binds": True}))
    assert "owner-a" in compiled
    assert "requested_by_user_id" in compiled
    assert "project_id IS NULL" in compiled
