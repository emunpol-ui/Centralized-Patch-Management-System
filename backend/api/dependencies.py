"""
Shared FastAPI dependency-injection providers.

Centralizing dependency declarations here (rather than redefining
``Depends(...)`` inline in every router) keeps route signatures concise and
gives every router a single, consistent source for cross-cutting
dependencies, per SAD Section 5.6 (Dependency Injection).

Additional dependencies (authenticated client agent) will be added here
in a later ticket (AUTH-002) without requiring changes to this ticket's
scaffolding.
"""

from __future__ import annotations

import hmac
from datetime import timedelta
from typing import Annotated

from fastapi import Depends, Header, Request
from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.database.session import get_db
from backend.models.administrator import Administrator
from backend.services.auth_service import AuthenticationError, AuthService

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
