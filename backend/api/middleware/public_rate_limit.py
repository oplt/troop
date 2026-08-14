from fastapi import Request
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse, Response

from backend.core.cache import redis_client
from backend.core.config import settings
from backend.core.logging import get_logger

logger = get_logger("backend.request")


def _request_has_session_credentials(request: Request) -> bool:
    """Reserve public rate limiting for anonymous SPA/API traffic."""
    if request.cookies.get(settings.ACCESS_COOKIE_NAME) or request.cookies.get(
        settings.REFRESH_COOKIE_NAME
    ):
        return True
    auth = request.headers.get("Authorization")
    return bool(auth and auth.startswith("Bearer "))


class PublicRateLimitMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next) -> Response:
        if settings.PUBLIC_RATE_LIMIT_REQUESTS <= 0:
            return await call_next(request)

        path = request.url.path
        if not (
            path.startswith("/api/")
            or path.startswith("/health/")
            or path.startswith("/webhooks/")
        ):
            return await call_next(request)

        # Health probes must not be blocked by the Redis-backed public limiter;
        # readiness performs its own bounded dependency checks.
        if request.url.path in {"/health/live", "/health/ready"}:
            return await call_next(request)

        if _request_has_session_credentials(request):
            return await call_next(request)

        client_ip = request.client.host if request.client else "unknown"
        key = f"rate_limit:public:{client_ip}"
        count = await redis_client.incr(key)
        if count == 1:
            await redis_client.expire(key, settings.PUBLIC_RATE_LIMIT_WINDOW_SECONDS)
        if count > settings.PUBLIC_RATE_LIMIT_REQUESTS:
            ttl = await redis_client.ttl(key)
            logger.warning(
                "public_rate_limit_429 ip=%s path=%s count=%s limit=%s ttl=%s",
                client_ip,
                request.url.path,
                count,
                settings.PUBLIC_RATE_LIMIT_REQUESTS,
                ttl,
            )
            return JSONResponse(
                status_code=429,
                content={"detail": f"Too many requests. Try again in {ttl} seconds."},
                headers={"Retry-After": str(ttl)},
            )

        return await call_next(request)
