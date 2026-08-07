"""
Shared FastAPI dependency-injection providers.

Centralizing dependency declarations here (rather than redefining
``Depends(...)`` inline in every router) keeps route signatures concise and
gives every router a single, consistent source for cross-cutting
dependencies, per SAD Section 5.6 (Dependency Injection).
"""

from __future__ import annotations

import hmac
import logging
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.database.session import get_db
from backend.models.administrator import Administrator
from backend.models.client import Client
from backend.services.auth_service import AuthenticationError, AuthService
from backend.services.client_auth_service import ClientAuthService
from backend.services.client_service import ClientService
from backend.services.heartbeat_service import HeartbeatService
from backend.services.inventory_service import InventoryService
from backend.services.repository_service import RepositoryService
from backend.services.version_comparison_service import VersionComparisonService

logger = logging.getLogger(__name__)

# Reusable, typed dependency: injects the cached application Settings
# instance into any route or service that declares `SettingsDependency`.
SettingsDependency = Annotated[Settings, Depends(get_settings)]

# Reusable, typed dependency: injects a request-scoped SQLAlchemy Session
# (CPM-002) into any route or service that declares `DBSessionDependency`.
DBSessionDependency = Annotated[Session, Depends(get_db)]


def get_auth_service(settings: SettingsDependency) -> AuthService:
    """
    Build an ``AuthService`` configured from the current application
    settings (session inactivity timeout - FR-018 / NFR-028).

    A new, stateless ``AuthService`` instance is constructed per request;
    it holds no per-request state itself (the database ``Session`` is
    passed into each method call), so this has no measurable cost.
    """
    return AuthService(session_timeout=timedelta(minutes=settings.SESSION_INACTIVITY_TIMEOUT_MINUTES))


# Reusable, typed dependency: injects a configured `AuthService`.
AuthServiceDependency = Annotated[AuthService, Depends(get_auth_service)]


def get_client_auth_service() -> ClientAuthService:
    """
    Build a ``ClientAuthService``.

    Unlike ``get_auth_service``, no settings are needed - API keys, unlike
    administrator sessions, do not currently expire (see the scoping note
    at the top of ``backend.services.client_auth_service``).
    """
    return ClientAuthService()


# Reusable, typed dependency: injects a configured `ClientAuthService`.
ClientAuthServiceDependency = Annotated[ClientAuthService, Depends(get_client_auth_service)]


def get_client_service() -> ClientService:
    """
    Build a ``ClientService`` (CLIENT-001 - FR-001 registration business
    logic). Stateless, like every other service constructed here.
    """
    return ClientService()


# Reusable, typed dependency: injects a configured `ClientService`.
ClientServiceDependency = Annotated[ClientService, Depends(get_client_service)]


def get_heartbeat_service() -> HeartbeatService:
    """
    Build a ``HeartbeatService`` (CLIENT-002 - FR-003 heartbeat business
    logic). Stateless, like every other service constructed here.
    """
    return HeartbeatService()


# Reusable, typed dependency: injects a configured `HeartbeatService`.
HeartbeatServiceDependency = Annotated[HeartbeatService, Depends(get_heartbeat_service)]


def get_inventory_service() -> InventoryService:
    """
    Build an ``InventoryService`` (INV-001 - FR-005 inventory upload
    business logic). Stateless, like every other service constructed here.
    """
    return InventoryService()


# Reusable, typed dependency: injects a configured `InventoryService`.
InventoryServiceDependency = Annotated[InventoryService, Depends(get_inventory_service)]


def get_version_comparison_service() -> VersionComparisonService:
    """
    Build a ``VersionComparisonService`` (INV-002 - FR-007 version
    comparison business logic). Stateless, like every other service
    constructed here.
    """
    return VersionComparisonService()


# Reusable, typed dependency: injects a configured `VersionComparisonService`.
VersionComparisonServiceDependency = Annotated[
    VersionComparisonService, Depends(get_version_comparison_service)
]


def get_repository_service() -> RepositoryService:
    """
    Build a ``RepositoryService`` (REP-001 - FR-006 installer package
    upload business logic). Stateless, like every other service
    constructed here.
    """
    return RepositoryService()


# Reusable, typed dependency: injects a configured `RepositoryService`.
RepositoryServiceDependency = Annotated[RepositoryService, Depends(get_repository_service)]


def require_administrator(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> Administrator:
    """
    FastAPI dependency enforcing an authenticated administrator session.

    Reads the session cookie by its *configured* name
    (``Settings.SESSION_COOKIE_NAME``) directly from the request, rather
    than via a hardcoded ``Cookie(...)`` parameter, so the cookie name
    remains centrally configurable (Charter/SAD "Configuration over
    Hardcoding"). Raises ``AuthenticationError`` (401) if the cookie is
    missing, or if ``AuthService.validate_session`` rejects it as unknown
    or expired.

    This is the "Protected routes" mechanism required by AUTH-001: any
    router that declares ``CurrentAdministrator`` in its signature is
    automatically inaccessible without a valid, active session.
    """
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        raise AuthenticationError("Not authenticated.")
    return auth_service.validate_session(db, raw_token=raw_token)


# Reusable, typed dependency: injects the authenticated Administrator and
# enforces that a valid session exists (raises 401 otherwise). Protected
# admin routes (this ticket's and future tickets') should declare this.
CurrentAdministrator = Annotated[Administrator, Depends(require_administrator)]


def extract_bearer_token(request: Request) -> str | None:
    """
    Extract the raw token from an ``Authorization: Bearer <token>`` header
    (PRS Appendix B "Standard Request Headers" for Client Agent requests),
    or ``None`` if the header is absent or does not use the Bearer scheme.

    Public (module-level, not underscore-prefixed) so that CLIENT-001's
    registration endpoint (``backend/api/routers/registration.py``) can
    reuse this exact extraction logic rather than duplicating it: FR-001
    registration requests also authenticate via ``Authorization: Bearer``
    (see PRS Appendix B), but cannot go through ``require_client_api_key``
    below, since that dependency only ever resolves a key that already
    matches an *existing* ``Client`` row - see the design note on
    ``backend.services.client_auth_service.ClientAuthService.
    resolve_registration_credential`` for the full reasoning. Originally
    named ``_extract_bearer_token``; renamed (behavior unchanged) as part
    of this ticket's minimal, documented extension rather than duplicating
    header-parsing logic in a second module.
    """
    auth_header = request.headers.get("Authorization")
    if not auth_header:
        return None
    scheme, _, token = auth_header.partition(" ")
    if scheme.lower() != "bearer" or not token:
        return None
    return token


def require_client_api_key(
    request: Request,
    db: DBSessionDependency,
    client_auth_service: ClientAuthServiceDependency,
) -> Client:
    """
    FastAPI dependency enforcing API-key authentication for Client Agent
    requests (FR-002; AUTH-002's "Authentication dependency" deliverable).

    This is the function every agent-facing router's ``dependencies=[...]``
    list should include (see ``backend/api/routers/agent.py``) so that
    "all agent endpoints protected" (AUTH-002 acceptance criterion) holds
    automatically for every route added to that router - present or
    future - without relying on each individual endpoint remembering to
    declare it. Handlers that also need the identified ``Client`` object
    itself should additionally declare ``CurrentClient`` as a parameter;
    FastAPI resolves a given dependency at most once per request, so doing
    both does not authenticate the request twice.

    Raises ``AuthenticationError`` (401) if the ``Authorization`` header is
    missing/malformed, or if ``ClientAuthService.authenticate`` rejects
    the key as unknown.

    NOT used by ``POST /api/register`` (CLIENT-001) - see
    ``extract_bearer_token`` above.
    """
    raw_key = extract_bearer_token(request)
    if not raw_key:
        raise AuthenticationError("Not authenticated. Missing or malformed Authorization header.")
    client = client_auth_service.authenticate(db, raw_api_key=raw_key)
    logger.debug("Client %s authenticated for %s %s.", client.id, request.method, request.url.path)
    return client


# Reusable, typed dependency: injects the authenticated Client and
# enforces that a valid API key was presented (raises 401 otherwise).
# Agent-facing routes (this ticket's and future tickets') should declare
# this, in addition to applying `require_client_api_key` at the router
# level (see the docstring above and backend/api/routers/agent.py).
CurrentClient = Annotated[Client, Depends(require_client_api_key)]


def _constant_time_equals(a: str, b: str) -> bool:
    """Constant-time string comparison to avoid timing side channels."""
    return hmac.compare_digest(a, b)


def verify_csrf_token(
    request: Request,
    settings: SettingsDependency,
    x_csrf_token: Annotated[str | None, Header(alias="X-CSRF-Token")] = None,
) -> None:
    """
    Enforce the double-submit-cookie CSRF check required by NFR-028 on
    every state-changing (non-GET) administrator request.

    The CSRF cookie is set (non-HttpOnly, so client-side JavaScript can
    read it) alongside the session cookie at login. A request is accepted
    only if the ``X-CSRF-Token`` header exactly matches the current value
    of the CSRF cookie: an attacker who can trigger a cross-site request
    (e.g. via a forged form on another site) cannot read the victim's
    cookie value due to the browser's same-origin policy, so they cannot
    construct a header that matches it, even though the cookie itself is
    sent automatically by the browser.
    """
    cookie_value = request.cookies.get(settings.CSRF_COOKIE_NAME)
    if not cookie_value or not x_csrf_token or not _constant_time_equals(cookie_value, x_csrf_token):
        raise AuthenticationError("CSRF token missing or invalid.", status_code=403)


# Reusable, typed dependency: enforces the CSRF check above. Declared as a
# no-return-value guard dependency - routes depend on it purely for its
# side effect (raising on failure), e.g. `Depends(verify_csrf_token)`.
CSRFProtection = Annotated[None, Depends(verify_csrf_token)]