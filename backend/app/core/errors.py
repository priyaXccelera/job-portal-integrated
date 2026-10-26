"""Application errors and the global JSON error-envelope handlers.

Every error leaves the API as ``{"success": false, "error": {"code", "message", "details": [...]}}``.
"""

from __future__ import annotations

import logging
from typing import Any

from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

logger = logging.getLogger(__name__)


class AppError(Exception):
    """Base class for all expected, client-visible errors."""

    def __init__(
        self,
        status_code: int,
        code: str,
        message: str,
        details: list[dict[str, Any]] | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.code = code
        self.message = message
        self.details = details or []
        self.headers = headers


class BadRequestError(AppError):
    def __init__(self, message: str, code: str = "BAD_REQUEST", details: list[dict[str, Any]] | None = None) -> None:
        super().__init__(400, code, message, details)


class UnauthorizedError(AppError):
    def __init__(self, message: str = "Authentication required") -> None:
        super().__init__(401, "UNAUTHORIZED", message, headers={"WWW-Authenticate": "Bearer"})


class ForbiddenError(AppError):
    def __init__(self, message: str = "Forbidden", code: str = "FORBIDDEN") -> None:
        super().__init__(403, code, message)


class NotFoundError(AppError):
    def __init__(self, message: str = "Resource not found") -> None:
        super().__init__(404, "NOT_FOUND", message)


class ConflictError(AppError):
    def __init__(self, message: str, code: str = "CONFLICT") -> None:
        super().__init__(409, code, message)


class RateLimitedError(AppError):
    def __init__(self, message: str = "Too many requests", retry_after: int = 60) -> None:
        super().__init__(429, "RATE_LIMITED", message, headers={"Retry-After": str(max(1, int(retry_after)))})


_STATUS_CODES: dict[int, str] = {
    400: "BAD_REQUEST",
    401: "UNAUTHORIZED",
    402: "INSUFFICIENT_CREDITS",
    403: "FORBIDDEN",
    404: "NOT_FOUND",
    405: "METHOD_NOT_ALLOWED",
    409: "CONFLICT",
    413: "PAYLOAD_TOO_LARGE",
    415: "UNSUPPORTED_MEDIA_TYPE",
    422: "VALIDATION_ERROR",
    429: "RATE_LIMITED",
}


def error_response(
    status_code: int,
    code: str,
    message: str,
    details: list[dict[str, Any]] | None = None,
    headers: dict[str, str] | None = None,
) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={"success": False, "error": {"code": code, "message": message, "details": details or []}},
        headers=headers,
    )


def _field_path(loc: tuple[Any, ...] | list[Any]) -> str:
    parts = [str(p) for p in loc]
    if parts and parts[0] in ("body", "query", "path", "header", "cookie"):
        parts = parts[1:]
    return ".".join(parts)


async def app_error_handler(request: Request, exc: AppError) -> JSONResponse:
    return error_response(exc.status_code, exc.code, exc.message, exc.details, exc.headers)


async def http_exception_handler(request: Request, exc: StarletteHTTPException) -> JSONResponse:
    status = exc.status_code
    headers = dict(exc.headers) if exc.headers else None
    if status == 404:
        detail = exc.detail if isinstance(exc.detail, str) and exc.detail not in ("Not Found",) else None
        message = detail or "Route not found"
        return error_response(404, "NOT_FOUND", message, headers=headers)
    if status == 405:
        return error_response(405, "METHOD_NOT_ALLOWED", "Method not allowed", headers=headers)
    code = _STATUS_CODES.get(status, "INTERNAL_ERROR" if status >= 500 else "BAD_REQUEST")
    message = exc.detail if isinstance(exc.detail, str) and exc.detail else code.replace("_", " ").capitalize()
    if status == 401 and headers is None:
        headers = {"WWW-Authenticate": "Bearer"}
    return error_response(status, code, message, headers=headers)


async def validation_exception_handler(request: Request, exc: RequestValidationError) -> JSONResponse:
    errors = exc.errors()
    if any(e.get("type") == "json_invalid" for e in errors):
        return error_response(400, "MALFORMED_BODY", "Malformed JSON body")
    details = [{"field": _field_path(e.get("loc", ())), "message": str(e.get("msg", "Invalid value"))} for e in errors]
    return error_response(422, "VALIDATION_ERROR", "Validation failed", details)


async def integrity_error_handler(request: Request, exc: IntegrityError) -> JSONResponse:
    logger.warning("Integrity error on %s %s: %s", request.method, request.url.path, exc.orig)
    return error_response(409, "CONFLICT", "Request conflicts with existing data")


async def sqlalchemy_error_handler(request: Request, exc: SQLAlchemyError) -> JSONResponse:
    logger.error("Database error on %s %s", request.method, request.url.path, exc_info=exc)
    return error_response(500, "INTERNAL_ERROR", "Internal server error")


async def unhandled_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.exception("Unhandled error on %s %s", request.method, request.url.path)
    return error_response(500, "INTERNAL_ERROR", "Internal server error")


def register_handlers(app: FastAPI) -> None:
    app.add_exception_handler(AppError, app_error_handler)
    app.add_exception_handler(StarletteHTTPException, http_exception_handler)
    app.add_exception_handler(RequestValidationError, validation_exception_handler)
    app.add_exception_handler(IntegrityError, integrity_error_handler)
    app.add_exception_handler(SQLAlchemyError, sqlalchemy_error_handler)
    app.add_exception_handler(Exception, unhandled_exception_handler)
