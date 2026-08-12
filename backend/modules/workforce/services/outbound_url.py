"""SSRF-safe URL validation for outbound connector HTTP."""

from __future__ import annotations

import ipaddress
import os
import socket
from urllib.parse import urlparse

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
    """Validate connector base_url before server-side HTTP.

    Production default: HTTPS only.
    HTTP is allowed only when TROOP_ALLOW_PRIVATE_CONNECTOR_URLS=1 (local/dev).
    Passing allow_http=True alone is insufficient — private/dev mode must also be on.
    """
    raw = (url or "").strip()
    if not raw:
        raise UnsafeURLError("URL is required")
    parsed = urlparse(raw)
    scheme = (parsed.scheme or "").lower()
    private_ok = _allow_private()
    # HTTPS default; HTTP only when private connectors are explicitly enabled.
    # allow_http=False always forbids HTTP; allow_http=True still requires private_ok.
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

    # Literal IP host check before DNS
    try:
        literal_ip = ipaddress.ip_address(host)
        if any(literal_ip in net for net in _BLOCKED_NETWORKS) and not private_ok:
            raise UnsafeURLError(f"Address {literal_ip} is not allowed")
    except ValueError:
        literal_ip = None

    # Resolve DNS and check every address (guards common rebinding targets at validation time)
    try:
        infos = socket.getaddrinfo(host, parsed.port or (443 if scheme == "https" else 80))
    except socket.gaierror as exc:
        raise UnsafeURLError(f"Unable to resolve host '{host}'") from exc

    for info in infos:
        sockaddr = info[4]
        ip_str = sockaddr[0]
        try:
            ip = ipaddress.ip_address(ip_str)
        except ValueError:
            continue
        if any(ip in net for net in _BLOCKED_NETWORKS) and not private_ok:
            raise UnsafeURLError(f"Resolved address {ip} is not allowed")
    return raw
