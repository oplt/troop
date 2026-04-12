import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger("backend.error")


def register_exception_handlers(app: FastAPI) -> None:
    @app.exception_handler(RequestValidationError)
    async def request_validation_error_handler(request: Request, exc: RequestValidationError):
        return JSONResponse(
            status_code=422,
            content={
                "detail": "Request validation failed",
                "errors": exc.errors(),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )

    @app.exception_handler(ValueError)
    async def value_error_handler(request: Request, exc: ValueError):
        return JSONResponse(
            status_code=400,
            content={
                "detail": str(exc),
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )

    @app.exception_handler(HTTPException)
    async def http_exception_handler(request: Request, exc: HTTPException):
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "detail": exc.detail,
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
            headers=exc.headers,
        )

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        logger.exception(
            "unhandled_exception path=%s correlation_id=%s",
            request.url.path,
            getattr(request.state, "correlation_id", None),
        )
        return JSONResponse(
            status_code=500,
            content={
                "detail": "Internal server error",
                "correlation_id": getattr(request.state, "correlation_id", None),
            },
        )
