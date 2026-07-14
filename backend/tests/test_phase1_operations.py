from __future__ import annotations

import logging

from backend.core.external_http import external_retry_policy, external_timeout, outbound_headers
from backend.core.logging import _RedactSensitiveValues
from backend.core.request_context import bind_context
from backend.modules.rag.observability import log_rag_event


def test_external_timeout_sets_every_http_phase() -> None:
    timeout = external_timeout(12)

    assert timeout.connect == 10
    assert timeout.read == 12
    assert timeout.write == 12
    assert timeout.pool == 10


def test_outbound_headers_propagate_safe_context_only() -> None:
    with bind_context(request_id="req-123", correlation_id="corr-456", user_id="user-secret"):
        headers = outbound_headers({"User-Agent": "troop-test"})

    assert headers["X-Request-ID"] == "req-123"
    assert headers["X-Correlation-ID"] == "corr-456"
    assert headers["User-Agent"] == "troop-test"
    assert "user-secret" not in headers.values()


def test_retry_policy_does_not_retry_non_idempotent_writes() -> None:
    write_policy = external_retry_policy("POST")
    keyed_policy = external_retry_policy("POST", idempotency_key=True)

    assert write_policy.max_attempts == 1
    assert write_policy.retry_timeouts is False
    assert keyed_policy.max_attempts == 2
    assert 503 in keyed_policy.retry_statuses


def test_log_filter_redacts_credentials_and_bearer_tokens() -> None:
    record = logging.LogRecord(
        name="test",
        level=logging.ERROR,
        pathname=__file__,
        lineno=1,
        msg="api_key=%s Authorization: Bearer secret-token",
        args=("secret-key",),
        exc_info=None,
    )

    assert _RedactSensitiveValues().filter(record) is True
    message = record.getMessage()
    assert "secret-key" not in message
    assert "secret-token" not in message
    assert "[REDACTED]" in message


def test_rag_content_preview_is_not_logged_by_default(caplog) -> None:
    with caplog.at_level(logging.INFO, logger="backend.modules.rag.observability"):
        log_rag_event("search", content_preview="private document content")

    assert "private document content" not in caplog.text
