from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from backend.core.error_payloads import error_payload
from backend.core.logging import get_logger

logger = get_logger("backend.error")


def _request_ids(request: Request) -> tuple[str | None, str | None]:
    return (
        getattr(request.state, "request_id", None),
        getattr(request.state, "correlation_id", None),
    )


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        request_id, correlation_id = _request_ids(request)
        return JSONResponse(
            status_code=422,
            content=error_payload(
                code="REQUEST_VALIDATION_FAILED",
                message="Request validation failed",
                correlation_id=correlation_id,
                request_id=request_id,
                details={"errors": exc.errors()},
            )
            | {"errors": exc.errors()},
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        request_id, correlation_id = _request_ids(request)
        logger.warning(
            "client_value_error method=%s path=%s request_id=%s correlation_id=%s "
            "exception_type=%s",
            request.method,
            request.url.path,
            request_id,
            correlation_id,
            type(exc).__name__,
        )
        logger.info(
            "client_value_error_detail request_id=%s correlation_id=%s detail=%s",
            request_id,
            correlation_id,
            str(exc)[:500],
        )
        return JSONResponse(
            status_code=400,
            content=error_payload(
                code="INVALID_REQUEST",
                message="Invalid request",
                correlation_id=correlation_id,
                request_id=request_id,
            ),
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        request_id, correlation_id = _request_ids(request)
        if exc.status_code in {401, 403, 429}:
            logger.warning(
                "http_%s path=%s request_id=%s correlation_id=%s detail=%s",
                exc.status_code,
                request.url.path,
                request_id,
                correlation_id,
                exc.detail,
            )
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            payload = dict(exc.detail)
            payload.setdefault("correlation_id", correlation_id)
            payload.setdefault("request_id", request_id)
            message = (
                payload.get("detail") or payload.get("error", {}).get("message") or "HTTP error"
            )
        else:
            message = exc.detail if isinstance(exc.detail, str) else "HTTP error"
            payload = error_payload(
                code=f"HTTP_{exc.status_code}",
                message=message,
                correlation_id=correlation_id,
                request_id=request_id,
                details=exc.detail if not isinstance(exc.detail, str) else None,
            ) | {"detail": exc.detail}
        return JSONResponse(
            status_code=exc.status_code,
            content=payload,
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        request_id, correlation_id = _request_ids(request)
        db_code = getattr(getattr(exc, "orig", None), "pgcode", None)
        logger.exception(
            "unhandled_exception method=%s path=%s request_id=%s correlation_id=%s "
            "exception_type=%s database_error_code=%s",
            request.method,
            request.url.path,
            request_id,
            correlation_id,
            type(exc).__name__,
            db_code,
        )
        return JSONResponse(
            status_code=500,
            content=error_payload(
                code="INTERNAL_SERVER_ERROR",
                message="Internal server error",
                correlation_id=correlation_id,
                request_id=request_id,
            ),
        )
