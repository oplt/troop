from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.error_payloads import error_payload
from backend.core.logging import get_logger

logger = get_logger("backend.error")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="REQUEST_VALIDATION_FAILED",
                message="Request validation failed",
                correlation_id=getattr(request.state, "correlation_id", None),
                details={"errors": exc.errors()},
            )
            | {"errors": exc.errors()},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content=error_payload(
                code="BAD_REQUEST",
                message=str(exc),
                correlation_id=getattr(request.state, "correlation_id", None),
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        if exc.status_code == 429:
            logger.warning(
                "http_429 path=%s correlation_id=%s detail=%s",
                request.url.path,
                getattr(request.state, "correlation_id", None),
                exc.detail,
            )
        message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
        return JSONResponse(
            status_code=exc.status_code,
            content=error_payload(
                code=f"HTTP_{exc.status_code}",
                message=message,
                correlation_id=getattr(request.state, "correlation_id", None),
                details=exc.detail if not isinstance(exc.detail, str) else None,
            )
            | {"detail": exc.detail},
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        duration_hint = getattr(request.state, "started_at", None)
        db_code = getattr(getattr(exc, "orig", None), "pgcode", None)
        logger.exception(
            "unhandled_exception method=%s path=%s correlation_id=%s "
            "exception_type=%s database_error_code=%s",
            request.method,
            request.url.path,
            getattr(request.state, "correlation_id", None),
            type(exc).__name__,
            db_code,
        )
        del duration_hint
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="Internal server error",
                correlation_id=getattr(request.state, "correlation_id", None),
            ),
        )
