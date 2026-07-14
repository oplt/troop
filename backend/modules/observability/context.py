"""Compatibility context API for logs, traces, and background jobs."""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager

from backend.core.request_context import RequestContext, bind_context, get_request_context


@contextmanager
def bind_observability_context(**values: object | None) -> Iterator[RequestContext]:
    with bind_context(**values) as context:
        yield context


def current_context() -> RequestContext:
    return get_request_context()


__all__ = ["bind_observability_context", "current_context"]
