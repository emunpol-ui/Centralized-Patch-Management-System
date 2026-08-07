"""
CPMS Backend - Application Entry Point.

Builds and configures the FastAPI application instance:
    * Loads and validates configuration (backend.core.config).
    * Initializes application-wide logging (backend.core.logging).
    * Registers global exception handlers (backend.core.exceptions).
    * Enables CORS.
    * Registers API routers.
    * Enables interactive API documentation (Swagger UI at /docs,
      ReDoc at /redoc, raw OpenAPI schema at /openapi.json).

This module is executed either directly via ``run.py`` (project root) or
via Uvicorn's import string ``backend.main:app`` (see README "Installation
and Running").
"""

from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routers.agent import router as agent_router
from backend.api.routers.auth import router as auth_router
from backend.api.routers.health import router as health_router
from backend.api.routers.registration import router as registration_router
from backend.api.routers.repository import router as repository_router
from backend.api.routers.updates import router as updates_router
from backend.core.config import get_settings
from backend.core.exceptions import register_exception_handlers
from backend.core.logging import configure_logging

# --- Configuration & logging must be initialized before anything else ------
settings = get_settings()
configure_logging(settings)

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    """Application startup/shutdown lifecycle hooks."""
    logger.info(
        "%s v%s starting up (environment=%s, debug=%s).",
        settings.APP_NAME,
        settings.APP_VERSION,
        settings.APP_ENV,
        settings.DEBUG,
    )
    yield
    logger.info("%s shutting down.", settings.APP_NAME)


def create_app() -> FastAPI:
    """
    Application factory.

    Building the app inside a factory function (rather than at import time
    only) keeps the module import-safe for tooling and future test suites
    (TEST-001) that need to construct fresh application instances.
    """
    application = FastAPI(
        title=settings.APP_NAME,
        version=settings.APP_VERSION,
        description=(
            "REST API backend for the Centralized Patch Management System "
            "(CPMS) - an educational proof-of-concept for centralized "
            "Windows software inventory management and patch deployment."
        ),
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # --- Middleware ---------------------------------------------------------
    application.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins_list,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # --- Global exception handling ------------------------------------------
    register_exception_handlers(application)

    # --- Routers -------------------------------------------------------------
    application.include_router(health_router)
    application.include_router(auth_router)
    application.include_router(agent_router)
    application.include_router(registration_router)
    application.include_router(updates_router)
    application.include_router(repository_router)

    return application


app = create_app()
