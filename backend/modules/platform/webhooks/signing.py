"""Webhook signing and target validation."""

from __future__ import annotations

import hashlib
import hmac
import ipaddress
from urllib.parse import urlparse

from fastapi import HTTPException

from backend.modules.orchestration.security import decrypt_secret


def webhook_signing_secret(stored: str) -> str:
    """Decrypt at-rest webhook secret; accept legacy plaintext rows."""
    return decrypt_secret(stored) or stored


def sign_webhook_body(raw_body: bytes, signing_secret: str) -> str:
    return hmac.new(signing_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()


def validate_webhook_target(target_url: str) -> None:
    parsed = urlparse(target_url)
    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise HTTPException(status_code=422, detail="Webhook target host is required")
    if host in {"localhost", "metadata.google.internal"} or host.endswith(".internal"):
        raise HTTPException(status_code=422, detail="Webhook target host is not allowed")
    if "." not in host and not host.startswith("["):
        raise HTTPException(status_code=422, detail="Webhook target host is not allowed")
    try:
        ip = ipaddress.ip_address(host.strip("[]"))
    except ValueError:
        return
    if (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_multicast
        or ip.is_reserved
        or ip.is_unspecified
    ):
        raise HTTPException(status_code=422, detail="Webhook target host is not allowed")
