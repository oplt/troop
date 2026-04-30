from fastapi import Response

from backend.core.config import settings
from backend.modules.identity_access.router import (
    _clear_auth_cookies,
    _set_access_cookie,
    _set_refresh_cookie,
)


def _set_cookie_headers(response: Response) -> list[str]:
    return [
        value.decode("latin-1")
        for key, value in response.raw_headers
        if key.decode("latin-1").lower() == "set-cookie"
    ]


def _has_cookie_header(
    headers: list[str],
    key: str,
    path: str,
    *,
    value: str | None = None,
    deleted: bool = False,
) -> bool:
    prefix = f"{key}={value}" if value is not None else f"{key}="
    return any(
        header.startswith(prefix)
        and f"Path={path};" in header
        and (not deleted or "Max-Age=0" in header)
        for header in headers
    )


def test_setting_refresh_cookie_expires_legacy_path_variants() -> None:
    response = Response()

    _set_refresh_cookie(response, "new-refresh-token")

    headers = _set_cookie_headers(response)
    assert _has_cookie_header(
        headers, settings.REFRESH_COOKIE_NAME, "/", deleted=True
    )
    assert _has_cookie_header(
        headers, settings.REFRESH_COOKIE_NAME, "/api/v1", deleted=True
    )
    assert _has_cookie_header(
        headers,
        settings.REFRESH_COOKIE_NAME,
        "/api/v1/auth",
        value="new-refresh-token",
    )


def test_setting_access_cookie_expires_legacy_path_variants() -> None:
    response = Response()

    _set_access_cookie(response, "new-access-token")

    headers = _set_cookie_headers(response)
    assert _has_cookie_header(
        headers, settings.ACCESS_COOKIE_NAME, "/api/v1", deleted=True
    )
    assert _has_cookie_header(
        headers, settings.ACCESS_COOKIE_NAME, "/api/v1/auth", deleted=True
    )
    assert _has_cookie_header(
        headers, settings.ACCESS_COOKIE_NAME, "/", value="new-access-token"
    )


def test_clear_auth_cookies_expires_current_and_legacy_path_variants() -> None:
    response = Response()

    _clear_auth_cookies(response)

    headers = _set_cookie_headers(response)
    for key in (
        settings.ACCESS_COOKIE_NAME,
        settings.REFRESH_COOKIE_NAME,
        settings.CSRF_COOKIE_NAME,
    ):
        for path in ("/", "/api/v1", "/api/v1/auth"):
            assert _has_cookie_header(headers, key, path, deleted=True)
