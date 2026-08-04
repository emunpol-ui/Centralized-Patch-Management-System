"""
Administrator authentication router.

Implements ``POST /api/admin/login`` exactly as specified in PRS
Appendix B (request/response bodies, validation rules, status codes), plus
the "Logout" and "Protected routes" deliverables explicitly listed under
AUTH-001 in the Backlog (PRS Appendix B documents login, key issuance, and
deployment cancellation in detail, but does not enumerate a logout
endpoint - this fills that gap rather than overriding a specified design).

Response bodies follow the standard CPMS envelope (PRS Appendix B
"Standard Response Format" / "Standard Error Response") already used
throughout the codebase.
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, Request, Response, status

from backend.api.dependencies import (
    AuthServiceDependency,
    CSRFProtection,
    CurrentAdministrator,
    DBSessionDependency,
    SettingsDependency,
)
from backend.core.config import Settings
from backend.core.security import generate_token
from backend.schemas.auth import AdminLoginRequest

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["Administrator Authentication"])


def _set_auth_cookies(
    response: Response, settings: Settings, *, session_token: str, csrf_token: str, max_age: int
) -> None:
    """
    Attach the session and CSRF cookies to ``response``.

    See ``Settings.SESSION_COOKIE_SECURE`` (backend/core/config.py) for
    why the `Secure` attribute defaults to disabled in this prototype.
    """
    response.set_cookie(
        key=settings.SESSION_COOKIE_NAME,
        value=session_token,
        max_age=max_age,
        httponly=True,
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )
    response.set_cookie(
        key=settings.CSRF_COOKIE_NAME,
        value=csrf_token,
        max_age=max_age,
        httponly=False,  # must be readable by client-side JavaScript
        secure=settings.SESSION_COOKIE_SECURE,
        samesite="lax",
        path="/",
    )


def _clear_auth_cookies(response: Response, settings: Settings) -> None:
    response.delete_cookie(settings.SESSION_COOKIE_NAME, path="/")
    response.delete_cookie(settings.CSRF_COOKIE_NAME, path="/")


@router.post(
    "/login",
    status_code=status.HTTP_200_OK,
    summary="Administrator login",
    description="Authenticate an administrator and establish a dashboard session (FR-019).",
)
async def login(
    payload: AdminLoginRequest,
    response: Response,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> Dict[str, Any]:
    """
    Authenticate an administrator and establish a dashboard session.

    On success, issues the ``session`` (HttpOnly) and ``csrf_token``
    (readable) cookies described in PRS Appendix B / NFR-028. The session
    token itself is never included in the JSON body - only in the
    HttpOnly cookie - matching the documented response body exactly.
    """
    administrator = auth_service.authenticate(db, username=payload.username, password=payload.password)
    session_token, expires_at = auth_service.create_session(db, administrator=administrator)
    csrf_token = generate_token()

    _set_auth_cookies(
        response,
        settings,
        session_token=session_token,
        csrf_token=csrf_token,
        max_age=settings.session_inactivity_timeout_seconds,
    )

    return {
        "success": True,
        "message": "Login successful.",
        "data": {
            "admin_id": str(administrator.id),
            "username": administrator.username,
        },
    }


@router.post(
    "/logout",
    status_code=status.HTTP_200_OK,
    summary="Administrator logout",
    description="Invalidate the current administrator session.",
)
async def logout(
    request: Request,
    response: Response,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    _current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
) -> Dict[str, Any]:
    """
    Log out the current administrator.

    Requires both an active session (``CurrentAdministrator``) and a valid
    CSRF token (``CSRFProtection``), since logout is a state-changing
    request (NFR-028 applies to it the same as any other state-changing
    dashboard action).
    """
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME) or ""
    auth_service.invalidate_session(db, raw_token=raw_token)
    _clear_auth_cookies(response, settings)

    return {"success": True, "message": "Logged out successfully.", "data": {}}


@router.get(
    "/me",
    status_code=status.HTTP_200_OK,
    summary="Current administrator",
    description="Return the currently authenticated administrator. Demonstrates the 'protected route' mechanism (AUTH-001).",
)
async def get_current_administrator_info(current_admin: CurrentAdministrator) -> Dict[str, Any]:
    """
    Return the identity of the currently authenticated administrator.

    Exists to give this ticket's "Protected routes" acceptance criterion
    ("Unauthorized users blocked") a concrete, testable endpoint, the same
    way CPM-001's ``/api/health`` proved the application foundation. Future
    tickets' protected routes should follow this same pattern: declare
    ``CurrentAdministrator`` in the route signature.
    """
    return {
        "success": True,
        "message": "Authenticated.",
        "data": {
            "admin_id": str(current_admin.id),
            "username": current_admin.username,
            "last_login": current_admin.last_login.isoformat() if current_admin.last_login else None,
        },
    }
