"""HTTP golden-signal middleware."""

from __future__ import annotations

from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.modules.observability.metrics import (
    HTTP_ACTIVE,
    bounded_route,
    metrics_registry,
    record_http_request,
)


class ObservabilityMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started = perf_counter()
        metrics_registry.increment_gauge(
            HTTP_ACTIVE,
            help_text="Currently active HTTP requests.",
            labels={},
        )
        status_code = 500
        try:
            response = await call_next(request)
            status_code = response.status_code
            return response
        finally:
            route = getattr(request.scope.get("route"), "path", None) or request.url.path
            record_http_request(
                request.method,
                bounded_route(route),
                status_code,
                perf_counter() - started,
            )
            metrics_registry.increment_gauge(
                HTTP_ACTIVE,
                help_text="Currently active HTTP requests.",
                labels={},
                delta=-1,
            )


__all__ = ["ObservabilityMiddleware"]
