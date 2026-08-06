"""
Global exception handling.

Provides a base ``AppException`` type and registers centralized FastAPI
exception handlers so that:

    * Application-raised errors return the standardized response envelope
      used throughout the CPMS REST API (see PRS Appendix B - "Standard
      Error Response").
    * Unhandled exceptions are logged with a full stack trace but never
      leak internal implementation details to the caller (SAD Section
      15.12 - Error Handling).

CPM-003 FIX: ``handle_validation_error`` now passes ``exc.errors()``
through FastAPI's ``jsonable_encoder`` before returning it. Pydantic v2's
``.errors()`` can include a ``ctx`` dict containing the raw exception
object raised inside a ``field_validator`` (e.g. CPM-003's
``AdminLoginRequest.not_blank``, which raises ``ValueError``) - passed
directly to ``JSONResponse``, that object is not JSON-serializable and
crashes the 422 handler itself into an unhandled 500 instead of returning
the intended 422. This was latent in CPM-001 (nothing before CPM-003 used
a validator that raises) and is corrected here as a minimal, necessary
integration fix; no other behavior changes.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, Request
from fastapi.encoders import jsonable_encoder
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


class AppException(Exception):
    """
    Base class for all application-specific (business-rule) exceptions.

    Domain modules should subclass this exception rather than raising bare
    ``Exception`` instances, so that they are automatically converted into
    the standard API error envelope. See
    ``backend.services.auth_service.AuthenticationError`` for an example.
    """

    def __init__(self, message: str, status_code: int = 500) -> None:
        self.message = message
        self.status_code = status_code
        super().__init__(message)


def register_exception_handlers(app: FastAPI) -> None:
    """Attach the application's global exception handlers to ``app``."""

    @app.exception_handler(AppException)
    async def handle_app_exception(request: Request, exc: AppException) -> JSONResponse:
        logger.error("Application error on %s %s: %s", request.method, request.url.path, exc.message)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "success": False,
                "message": exc.message,
                "error": exc.__class__.__name__,
            },
        )

    @app.exception_handler(RequestValidationError)
    async def handle_validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
        # jsonable_encoder recursively converts the error list into
        # JSON-safe primitives (any raw exception objects become their
        # str() representation) - see the module docstring for why this
        # is required.
        safe_errors = jsonable_encoder(exc.errors())
        logger.warning("Validation error on %s %s: %s", request.method, request.url.path, safe_errors)
        return JSONResponse(
            status_code=422,
            content={
                "success": False,
                "message": "Request validation failed.",
                "error": "ValidationError",
                "details": safe_errors,
            },
        )

    @app.exception_handler(Exception)
    async def handle_unhandled_exception(request: Request, exc: Exception) -> JSONResponse:
        logger.exception("Unhandled exception on %s %s", request.method, request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "success": False,
                "message": "An unexpected error occurred.",
                "error": "InternalServerError",
            },
        )
