# Phase 1 operations policy

## Logging

Runtime application packages use `backend.core.logging.get_logger`. The
shared handler filters redact values following `api_key`, `access_token`,
`password`, `secret`, or `private_key`, plus bearer tokens. Exceptions should
continue to be emitted with `logger.exception(...)` when a stack trace is
needed. CLI and baseline tools may print their user-facing JSON or reports;
`backend/tools/check_logging_policy.py` keeps that exception scoped.

RAG content previews are disabled unless `RAG_LOG_CONTENT_IN_DEV=true` and the
application is not in production. Identifiers and timing data may be logged;
prompts, documents, tokens, and credentials must not be placed in log fields.

## External calls

All runtime `httpx.AsyncClient` integrations use
`backend.core.external_http.external_timeout`. The helper sets explicit
connect, read, write, and pool deadlines. Provider and tool operations may
override the total timeout for their workload without removing phase
deadlines. Request, correlation, and trace IDs are attached through
`outbound_headers`; user IDs and secrets are never propagated as headers.

Retry policy is deliberately conservative:

| Operation | Default retry behavior |
| --- | --- |
| GET/HEAD/OPTIONS | Up to two attempts for timeout, connection, 408/425/429/5xx failures when the caller opts into an executor. |
| POST/PATCH/DELETE | One attempt unless the operation has an idempotency key. |
| GitHub writes and webhook delivery | One attempt; the persisted sync/event state or caller may retry explicitly. |
| Provider generation and embeddings | One attempt at this boundary; orchestration/provider failover owns policy. |
| SMTP | One bounded attempt with `SMTP_TIMEOUT_SECONDS`; Celery retry policy handles transient worker failures. |
| S3-compatible storage | Boto standard retry mode with bounded connect/read timeouts and `STORAGE_MAX_ATTEMPTS`. |
| Redis and PostgreSQL | Redis socket connect/read and SQLAlchemy pool acquisition/query timeouts remain configured in `backend/core/cache.py` and `backend/db/session.py`. |

This avoids duplicate GitHub comments, pull requests, webhook deliveries, or
LLM charges. Any future automatic retry must preserve idempotency and emit an
attempt count, outcome, and bounded error classification.
