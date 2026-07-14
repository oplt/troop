"""Request and background-job context propagation.

Context is intentionally transport-neutral.  HTTP middleware establishes the
request/correlation IDs, authenticated dependencies add the user ID, and
Celery task headers carry the same fields into a worker process.

The values are safe identifiers only.  Do not place tokens, prompts, document
contents, or other sensitive payloads in this context.
"""

from __future__ import annotations

from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from contextvars import ContextVar, Token
from dataclasses import dataclass
from typing import Final, Literal

ContextField = Literal[
    "request_id",
    "correlation_id",
    "trace_id",
    "span_id",
    "user_id",
    "tenant_id",
    "project_id",
    "task_id",
    "run_id",
    "job_id",
    "task_name",
]

CONTEXT_FIELDS: Final[tuple[ContextField, ...]] = (
    "request_id",
    "correlation_id",
    "trace_id",
    "span_id",
    "user_id",
    "tenant_id",
    "project_id",
    "task_id",
    "run_id",
    "job_id",
    "task_name",
)
CONTEXT_HEADER_FIELDS: Final[tuple[ContextField, ...]] = (
    "request_id",
    "correlation_id",
    "trace_id",
    "span_id",
    "user_id",
    "tenant_id",
    "project_id",
    "task_id",
    "run_id",
)
MAX_CONTEXT_VALUE_LENGTH: Final[int] = 128


def _new_context_var(field: ContextField) -> ContextVar[str | None]:
    return ContextVar(f"troop_context_{field}", default=None)


_CONTEXT_VARS: dict[ContextField, ContextVar[str | None]] = {
    field: _new_context_var(field) for field in CONTEXT_FIELDS
}


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: str | None = None
    correlation_id: str | None = None
    trace_id: str | None = None
    span_id: str | None = None
    user_id: str | None = None
    tenant_id: str | None = None
    project_id: str | None = None
    task_id: str | None = None
    run_id: str | None = None
    job_id: str | None = None
    task_name: str | None = None

    def as_log_fields(self) -> dict[str, str]:
        """Return only populated fields suitable for structured log fields."""
        return {
            field: value for field in CONTEXT_FIELDS if (value := getattr(self, field)) is not None
        }

    def as_task_headers(self) -> dict[str, str]:
        """Return safe, non-secret context that may cross a Celery boundary."""
        return {
            field: value
            for field in CONTEXT_HEADER_FIELDS
            if (value := getattr(self, field)) is not None
        }


def sanitize_context_value(value: object | None) -> str | None:
    """Normalize an identifier before it is echoed or placed in logs/headers."""
    if value is None:
        return None
    normalized = "".join(char for char in str(value) if char.isprintable()).strip()
    if not normalized:
        return None
    return normalized[:MAX_CONTEXT_VALUE_LENGTH]


def get_request_context() -> RequestContext:
    return RequestContext(**{field: _CONTEXT_VARS[field].get() for field in CONTEXT_FIELDS})


def set_context(**values: object | None) -> None:
    """Set known context fields in the current async/thread context."""
    for field, value in values.items():
        if field not in _CONTEXT_VARS:
            raise ValueError(f"Unknown request context field: {field}")
        _CONTEXT_VARS[field].set(sanitize_context_value(value))


@contextmanager
def bind_context(**values: object | None) -> Iterator[RequestContext]:
    """Temporarily bind context and always restore the previous values."""
    tokens: list[tuple[ContextVar[str | None], Token[str | None]]] = []
    try:
        for field, value in values.items():
            variable = _CONTEXT_VARS.get(field)
            if variable is None:
                raise ValueError(f"Unknown request context field: {field}")
            tokens.append((variable, variable.set(sanitize_context_value(value))))
        yield get_request_context()
    finally:
        for variable, token in reversed(tokens):
            variable.reset(token)


def context_from_headers(headers: Mapping[str, object] | None) -> dict[str, str]:
    """Extract only the allowlisted, non-secret fields from Celery headers."""
    if not headers:
        return {}
    return {
        field: value
        for field in CONTEXT_HEADER_FIELDS
        if (value := sanitize_context_value(headers.get(field))) is not None
    }


__all__ = [
    "CONTEXT_FIELDS",
    "CONTEXT_HEADER_FIELDS",
    "RequestContext",
    "bind_context",
    "context_from_headers",
    "get_request_context",
    "sanitize_context_value",
    "set_context",
]
