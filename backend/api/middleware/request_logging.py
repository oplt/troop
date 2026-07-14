from time import perf_counter

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.logging import get_logger
from backend.core.request_context import get_request_context

logger = get_logger("backend.request")


class RequestLoggingMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        started_at = perf_counter()
        try:
            response = await call_next(request)
        except Exception:
            duration_ms = (perf_counter() - started_at) * 1000
            context = get_request_context()
            request_id = context.request_id or getattr(request.state, "request_id", "n/a")
            correlation_id = context.correlation_id or getattr(
                request.state, "correlation_id", "n/a"
            )
            user_id = context.user_id or getattr(request.state, "user_id", "n/a")
            logger.exception(
                "request_failed method=%s path=%s duration_ms=%.2f "
                "request_id=%s correlation_id=%s user_id=%s",
                request.method,
                request.url.path,
                duration_ms,
                request_id,
                correlation_id,
                user_id,
            )
            raise

        duration_ms = (perf_counter() - started_at) * 1000
        context = get_request_context()
        request_id = context.request_id or getattr(request.state, "request_id", "n/a")
        correlation_id = context.correlation_id or getattr(request.state, "correlation_id", "n/a")
        user_id = context.user_id or getattr(request.state, "user_id", "n/a")
        logger.info(
            "request_complete method=%s path=%s status=%s duration_ms=%.2f "
            "request_id=%s correlation_id=%s user_id=%s",
            request.method,
            request.url.path,
            response.status_code,
            duration_ms,
            request_id,
            correlation_id,
            user_id,
        )
        return response
