"""SSRF-safe URL validation and outbound HTTP helpers."""

from __future__ import annotations

import ipaddress
import os
import socket
from typing import Any
from urllib.parse import urljoin, urlparse

import httpx

_BLOCKED_HOSTS = {
    "localhost",
    "localhost.localdomain",
    "metadata.google.internal",
    "metadata",
    "instance-data",
}

_BLOCKED_NETWORKS = [
    ipaddress.ip_network("0.0.0.0/8"),
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("::1/128"),
    ipaddress.ip_network("fc00::/7"),
    ipaddress.ip_network("fe80::/10"),
]


class UnsafeURLError(ValueError):
    pass


def _allow_private() -> bool:
    return os.getenv("TROOP_ALLOW_PRIVATE_CONNECTOR_URLS", "").lower() in {
        "1",
        "true",
        "yes",
    }


def validate_outbound_url(url: str, *, allow_http: bool | None = None) -> str:
    """Validate arbitrary outbound URL before server-side HTTP.

    Production default: HTTPS only; private/link-local/metadata blocked.
    """
    raw = (url or "").strip()
    if not raw:
        raise UnsafeURLError("URL is required")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    private_ok = _allow_private()
    http_ok = False if allow_http is False else private_ok
    allowed_schemes = {"https", "http"} if http_ok else {"https"}
    if scheme not in allowed_schemes:
        if scheme == "http":
            raise UnsafeURLError(
                "Only https URLs are allowed "
                "(set TROOP_ALLOW_PRIVATE_CONNECTOR_URLS=1 for local http)"
            )
        raise UnsafeURLError(f"URL scheme must be one of: {', '.join(sorted(allowed_schemes))}")

    host = (parsed.hostname or "").strip().lower()
    if not host:
        raise UnsafeURLError("URL host is required")
    if host in _BLOCKED_HOSTS and not private_ok:
        raise UnsafeURLError(f"Host '{host}' is not allowed")
    if host.endswith(".internal") and not private_ok:
        raise UnsafeURLError("Internal hosts are not allowed")

    try:
        literal_ip = ipaddress.ip_address(host)
        if any(literal_ip in net for net in _BLOCKED_NETWORKS) and not private_ok:
            raise UnsafeURLError(f"Address {literal_ip} is not allowed")
    except ValueError:
        pass

    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Unable to resolve host '{host}'") from exc

    for info in infos:
        ip_str = info[4][0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if any(ip in net for net in _BLOCKED_NETWORKS) and not private_ok:
            raise UnsafeURLError(f"Resolved address {ip} is not allowed")
    return raw


async def safe_outbound_request(
    method: str,
    url: str,
    *,
    client: httpx.AsyncClient,
    headers: dict[str, str] | None = None,
    params: dict[str, Any] | None = None,
    allow_http: bool | None = None,
    max_redirects: int = 5,
) -> httpx.Response:
    """Perform HTTP with SSRF checks on the initial URL and every redirect target."""
    current = validate_outbound_url(url, allow_http=allow_http)
    redirects = 0
    while True:
        # Re-resolve at request time to reduce DNS-rebinding windows.
        validate_outbound_url(current, allow_http=allow_http)
        response = await client.request(
            method,
            current,
            headers=headers,
            params=params,
            follow_redirects=False,
        )
        if response.is_redirect and redirects < max_redirects:
            location = response.headers.get("location")
            if not location:
                return response
            next_url = urljoin(current, location)
            current = validate_outbound_url(next_url, allow_http=allow_http)
            redirects += 1
            continue
        return response
