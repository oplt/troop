"""Low-friction instrumentation decorators for async provider operations."""

from __future__ import annotations

from collections.abc import AsyncIterator, Awaitable, Callable
from functools import wraps
from time import perf_counter
from typing import Any, TypeVar

from backend.modules.observability.metrics import record_provider_call

T = TypeVar("T")


def observe_provider_call(
    operation: str,
) -> Callable[[Callable[..., Awaitable[T]]], Callable[..., Awaitable[T]]]:
    def decorator(function: Callable[..., Awaitable[T]]) -> Callable[..., Awaitable[T]]:
        @wraps(function)
        async def wrapped(*args: Any, **kwargs: Any) -> T:
            provider = args[0] if args else None
            provider_name = getattr(provider, "provider_type", None) or getattr(
                provider, "key", "unknown"
            )
            started = perf_counter()
            outcome = "success"
            try:
                return await function(*args, **kwargs)
            except Exception:
                outcome = "error"
                raise
            finally:
                record_provider_call(provider_name, operation, outcome, perf_counter() - started)

        return wrapped

    return decorator


def observe_provider_stream(operation: str) -> Callable[..., Any]:
    def decorator(function: Callable[..., AsyncIterator[Any]]) -> Callable[..., AsyncIterator[Any]]:
        @wraps(function)
        async def wrapped(*args: Any, **kwargs: Any) -> AsyncIterator[Any]:
            provider = args[0] if args else None
            provider_name = getattr(provider, "provider_type", None) or getattr(
                provider, "key", "unknown"
            )
            started = perf_counter()
            outcome = "success"
            try:
                async for item in function(*args, **kwargs):
                    yield item
            except Exception:
                outcome = "error"
                raise
            finally:
                record_provider_call(provider_name, operation, outcome, perf_counter() - started)

        return wrapped

    return decorator


__all__ = ["observe_provider_call", "observe_provider_stream"]
