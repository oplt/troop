"""Tests for webhook signing helpers."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from backend.modules.platform.webhooks.signing import sign_webhook_body, validate_webhook_target


def test_sign_webhook_body_is_deterministic():
    body = b'{"event":"platform.test"}'
    assert sign_webhook_body(body, "secret") == sign_webhook_body(body, "secret")
    assert sign_webhook_body(body, "secret") != sign_webhook_body(body, "other")


def test_validate_webhook_target_rejects_localhost():
    with pytest.raises(HTTPException) as exc:
        validate_webhook_target("http://localhost/hook")
    assert exc.value.status_code == 422
