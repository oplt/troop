"""Tests for OIDC SSO helpers (ENT-001)."""

from __future__ import annotations

import pytest

from backend.modules.identity_access.sso_service import SsoService, _email_domain


def test_email_domain_extraction() -> None:
    assert _email_domain("user@Example.COM") == "example.com"


def test_callback_url_uses_public_api_base(monkeypatch) -> None:
    from backend.core.config import settings

    monkeypatch.setattr(settings, "PUBLIC_API_BASE", "https://api.example.com/api/v1")
    assert SsoService.callback_url() == "https://api.example.com/api/v1/auth/sso/callback"
