"""Celery autoretry exception allowlist — retry transient infra failures only."""

from __future__ import annotations

import httpx
from sqlalchemy.exc import DBAPIError, OperationalError

# Used as Celery ``autoretry_for`` on worker tasks.
CELERY_TRANSIENT_EXCEPTIONS: tuple[type[BaseException], ...] = (
    TimeoutError,
    ConnectionError,
    ConnectionResetError,
    BrokenPipeError,
    OSError,
    httpx.TimeoutException,
    httpx.NetworkError,
    httpx.ConnectError,
    httpx.ReadError,
    httpx.WriteError,
    OperationalError,
    DBAPIError,
)


def is_transient_worker_error(exc: BaseException) -> bool:
    return isinstance(exc, CELERY_TRANSIENT_EXCEPTIONS)
