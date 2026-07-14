import uuid

from starlette.middleware.base import BaseHTTPMiddleware
from starlette.requests import Request
from starlette.responses import Response

from backend.core.request_context import bind_context, sanitize_context_value

CORRELATION_ID_HEADER = "X-Correlation-ID"
REQUEST_ID_HEADER = "X-Request-ID"


class CorrelationIdMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        correlation_id = sanitize_context_value(request.headers.get(CORRELATION_ID_HEADER)) or str(
            uuid.uuid4()
        )
        request_id = (
            sanitize_context_value(request.headers.get(REQUEST_ID_HEADER)) or correlation_id
        )
        request.state.correlation_id = correlation_id
        request.state.request_id = request_id
        with bind_context(request_id=request_id, correlation_id=correlation_id):
            response = await call_next(request)
        response.headers[CORRELATION_ID_HEADER] = correlation_id
        response.headers[REQUEST_ID_HEADER] = request_id
        return response
