"""P5.3 structured client errors and security audit regressions."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI, HTTPException
from httpx import ASGITransport, AsyncClient
from starlette.requests import Request

from backend.core.error_handler import register_exception_handlers
from backend.core.error_payloads import error_payload
from backend.core.request_context import bind_context
from backend.modules.audit.repository import AuditRepository


def _make_request(*, request_id: str = "req-1", correlation_id: str = "corr-1") -> Request:
    scope = {
        "type": "http",
        "method": "POST",
        "path": "/api/v1/test",
        "headers": [],
    }
    request = Request(scope)
    request.state.request_id = request_id
    request.state.correlation_id = correlation_id
    return request


def test_error_payload_includes_stable_code_and_request_id():
    payload = error_payload(
        code="INVALID_REQUEST",
        message="Invalid request",
        correlation_id="corr-1",
        request_id="req-1",
    )
    assert payload["error"]["code"] == "INVALID_REQUEST"
    assert payload["request_id"] == "req-1"
    assert payload["correlation_id"] == "corr-1"
    assert payload["detail"] == "Invalid request"


@pytest.mark.asyncio
async def test_value_error_handler_scrubs_internal_message():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/boom")
    async def boom():
        raise ValueError("secret tenant leak detail")

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/boom")

    body = response.json()
    assert response.status_code == 400
    assert body["error"]["code"] == "INVALID_REQUEST"
    assert body["error"]["message"] == "Invalid request"
    assert "secret tenant leak" not in json.dumps(body)


@pytest.mark.asyncio
async def test_http_exception_preserves_structured_detail():
    app = FastAPI()
    register_exception_handlers(app)

    @app.get("/deny")
    async def deny():
        raise HTTPException(
            status_code=403,
            detail=error_payload(
                code="FORBIDDEN",
                message="Forbidden",
            ),
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get("/deny")

    body = response.json()
    assert response.status_code == 403
    assert body["error"]["code"] == "FORBIDDEN"


def test_audit_repository_merges_request_context_into_metadata():
    merged = AuditRepository._merge_request_context({"approval_type": "github_comment"})
    assert merged["approval_type"] == "github_comment"


@pytest.mark.asyncio
async def test_audit_repository_log_persists_request_context():
    db = AsyncMock()
    db.add = MagicMock()
    db.flush = AsyncMock()

    with bind_context(request_id="req-audit", correlation_id="corr-audit"):
        entry = await AuditRepository(db).log(
            action="orchestration.approval.approved",
            user_id="user-1",
            resource_type="approval_request",
            resource_id="appr-1",
            metadata={"approval_type": "task_mark_complete"},
        )

    stored = json.loads(entry.metadata_json)
    assert stored["request_id"] == "req-audit"
    assert stored["correlation_id"] == "corr-audit"
    assert stored["approval_type"] == "task_mark_complete"


@pytest.mark.asyncio
async def test_incident_webhook_rejection_writes_security_audit():
    from backend.modules.orchestration import router as orch_router

    body = b'{"alert":"disk"}'
    request = MagicMock(spec=Request)
    request.body = AsyncMock(return_value=body)
    request.headers = {"X-Troop-Signature": "sha256=deadbeef"}
    db = AsyncMock()
    db.commit = AsyncMock()
    audit = AsyncMock()
    audit.log = AsyncMock()

    with (
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_SECRET", "whsec-test"),
        patch.object(orch_router.settings, "INCIDENT_WEBHOOK_OWNER_USER_ID", "user-1"),
        patch.object(orch_router, "AuditRepository", return_value=audit),
    ):
        response = await orch_router.incident_webhook(request, db)

    assert response.status_code == 401
    audit.log.assert_awaited_once()
    assert audit.log.await_args.kwargs["action"] == "security.incident_webhook.rejected"
    db.commit.assert_awaited_once()
