"""
Dashboard router (Backlog DASH-001 - "Dashboard Home"; DASH-002 -
"Deployment Monitoring"; DASH-003 - "Audit Log Viewer").

Implements the administrator-facing Dashboard Home overview: system
statistics, client summary, deployment summary, and repository summary
(SAD Section 9.4 / Section 13.6 "Dashboard Home"). This is the first
ticket to render server-side HTML via Jinja2 (``backend/templates/``) -
every prior administrator-facing feature (CLIENT-*, INV-*, REP-*,
DEPLOY-*) was API-only, per CURRENT_STATE.md's own "Files Likely to Be
Modified (DASH-001 / DASH-002)" note anticipating this.

Three related HTML pages and two JSON endpoints are exposed:

    * ``GET /dashboard`` - the Dashboard Home page itself. Protected by
      the administrator session cookie; unlike every other protected
      route in this codebase (which declares ``CurrentAdministrator`` and
      lets a missing/invalid session surface as a JSON 401), a *page*
      route redirects an unauthenticated browser to ``/login`` instead -
      a JSON 401 is not a usable response for a top-level page
      navigation. See ``_resolve_administrator_or_none`` below, which
      composes the existing ``AuthService.validate_session`` rather than
      duplicating its logic.
    * ``GET /login`` - a minimal login page whose form posts to the
      already-existing ``POST /api/admin/login`` (AUTH-001) via
      JavaScript ``fetch``. No new authentication logic is introduced
      here; this page only makes the existing endpoint reachable from a
      browser, which no prior ticket needed since none served HTML.
    * ``GET /api/admin/dashboard/stats`` - the same summary data as JSON,
      grouped under ``/api/admin`` alongside every other administrator
      API endpoint (``updates.py``, ``repository.py``,
      ``deployments.py``), following this project's established
      API-first pattern and giving the dashboard page and any future
      client-side refresh logic (out of scope here) a stable contract.
      Read-only, so - like ``GET /api/admin/clients/{client_id}/updates``
      - it requires only an active administrator session, no CSRF token
      (NFR-028 scopes CSRF to state-changing requests).
    * ``GET /dashboard/deployments`` (DASH-002) - the Deployment
      Monitoring page: deployment status breakdown plus a filterable,
      most-recent-first list of individual ``DeploymentTarget`` rows,
      each showing its client and deployed software package. Uses the
      exact same session-cookie/redirect-to-``/login`` pattern as
      ``/dashboard`` above.
    * ``GET /api/admin/dashboard/deployments`` (DASH-002) - the JSON
      counterpart of the page above, grouped under ``/api/admin``
      alongside ``GET /api/admin/dashboard/stats``. Read-only, so it
      likewise requires only an active administrator session.
    * ``GET /dashboard/audit-logs`` (DASH-003) - the Audit Log Viewer
      page: recorded system audit events (FR-016), most-recent-first,
      with optional filtering by event type, severity, related client,
      related administrator, and date range, plus a free-text search over
      the event description, and pagination. Uses the exact same
      session-cookie/redirect-to-``/login`` pattern as ``/dashboard`` and
      ``/dashboard/deployments`` above.
    * ``GET /api/admin/dashboard/audit-logs`` (DASH-003) - the JSON
      counterpart of the page above, grouped under ``/api/admin``
      alongside the other Dashboard Module JSON endpoints. Read-only, so
      it likewise requires only an active administrator session.

The HTML pages and their JSON counterparts both call the same
``DashboardService`` methods directly (no internal HTTP call), so there
is exactly one code path computing the numbers shown either way.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime, time, timezone
from pathlib import Path
from typing import Any, Dict, Optional

from fastapi import APIRouter, Query, Request, status
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

from backend.api.dependencies import (
    AuthServiceDependency,
    CurrentAdministrator,
    DBSessionDependency,
    DashboardServiceDependency,
    SettingsDependency,
)
from backend.core.config import BASE_DIR
from backend.models.administrator import Administrator
from backend.models.enums import DeploymentStatus
from backend.services.auth_service import AuthenticationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["Dashboard"])

_TEMPLATES_DIR = Path(BASE_DIR) / "backend" / "templates"
templates = Jinja2Templates(directory=str(_TEMPLATES_DIR))

# Bootstrap badge classes for each DeploymentStatus, keyed by enum member
# *name* (rather than ``.value``) so this presentation-only mapping stays
# correct regardless of whatever raw string value each status happens to
# be assigned (DASH-002 - "Clear status presentation for Pending,
# Downloading, Installing, Completed, and Failed"). Deliberately kept in
# the router (Presentation/API glue), not the schema (backend.schemas.
# deployment_monitor.DeploymentTargetDetail), so the API response stays
# presentation-agnostic - see that schema's own docstring.
_STATUS_BADGE_CLASS: Dict[str, str] = {
    "PENDING": "text-bg-warning text-dark",
    "DOWNLOADING": "text-bg-info text-dark",
    "INSTALLING": "text-bg-info text-dark",
    "COMPLETED": "text-bg-success",
    "FAILED": "text-bg-danger",
    "CANCELLED": "text-bg-secondary",
}


def _status_badge_class(target_status: DeploymentStatus) -> str:
    """Bootstrap badge classes for ``target_status`` (DASH-002)."""
    return _STATUS_BADGE_CLASS.get(target_status.name, "text-bg-light text-dark border")


def _status_label(target_status: DeploymentStatus) -> str:
    """Human-readable label for ``target_status`` (DASH-002), e.g. ``PENDING`` -> ``Pending``."""
    return target_status.name.replace("_", " ").title()


# Bootstrap badge classes for audit log severity (DASH-003 - "Show useful
# event information such as ... severity"). Matched case-insensitively
# against whatever raw string the ``AuditLog.severity`` column holds (PRS
# Section 7.5.6 lists "Information, Warning, Error" as the expected
# values), so this stays correct regardless of exact casing.
_SEVERITY_BADGE_CLASS: Dict[str, str] = {
    "INFO": "text-bg-secondary",
    "INFORMATION": "text-bg-secondary",
    "WARNING": "text-bg-warning text-dark",
    "ERROR": "text-bg-danger",
}


def _severity_badge_class(severity: str) -> str:
    """Bootstrap badge class for an audit log entry's ``severity`` (DASH-003)."""
    return _SEVERITY_BADGE_CLASS.get(severity.upper(), "text-bg-light text-dark border")


def _resolve_administrator_or_none(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> Administrator | None:
    """
    Resolve the current administrator session for a *page* route, without
    raising when no valid session exists.

    Reuses ``AuthService.validate_session`` exactly as
    ``require_administrator`` (``backend/api/dependencies.py``) does for
    API routes, but converts the "not authenticated" outcome into
    ``None`` instead of letting ``AuthenticationError`` propagate - a
    browser page redirect (below) is the correct behavior here, not a
    JSON 401 body.
    """
    raw_token = request.cookies.get(settings.SESSION_COOKIE_NAME)
    if not raw_token:
        return None
    try:
        return auth_service.validate_session(db, raw_token=raw_token)
    except AuthenticationError:
        return None


@router.get("/", include_in_schema=False)
async def root() -> RedirectResponse:
    """Redirect the application root to the Dashboard Home page."""
    return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
) -> HTMLResponse:
    """
    Render the administrator login page.

    If the browser already carries a valid session cookie, skip straight
    to the dashboard rather than showing the form again.
    """
    if _resolve_administrator_or_none(request, db, auth_service, settings) is not None:
        return RedirectResponse(url="/dashboard", status_code=status.HTTP_302_FOUND)
    return templates.TemplateResponse(request, "login.html", {})


@router.get("/dashboard", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_home(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    dashboard_service: DashboardServiceDependency,
) -> HTMLResponse:
    """
    Render the Dashboard Home page (Backlog DASH-001): system statistics,
    client summary, deployment summary, and repository summary.

    Redirects to ``/login`` if no valid administrator session is present,
    rather than returning a bare 401 - see
    ``_resolve_administrator_or_none``.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    overview = dashboard_service.get_overview(db)
    return templates.TemplateResponse(
        request,
        "dashboard/home.html",
        {
            "administrator": administrator,
            "overview": overview,
        },
    )


@router.get(
    "/api/admin/dashboard/stats",
    status_code=status.HTTP_200_OK,
    summary="Dashboard Home summary statistics",
    description=(
        "Return the Dashboard Home overview (Backlog DASH-001): system statistics, client summary, "
        "deployment summary, and repository summary."
    ),
)
async def get_dashboard_stats(
    db: DBSessionDependency,
    dashboard_service: DashboardServiceDependency,
    current_admin: CurrentAdministrator,
) -> Dict[str, Any]:
    """Return the Dashboard Home summary data as JSON (standard CPMS envelope)."""
    overview = dashboard_service.get_overview(db)
    logger.debug("Administrator %s requested dashboard statistics.", current_admin.id)
    return {
        "success": True,
        "message": "Dashboard statistics computed.",
        "data": overview.model_dump(mode="json"),
    }


@router.get(
    "/dashboard/deployments",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def deployment_monitoring_page(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    dashboard_service: DashboardServiceDependency,
    status_filter: Optional[DeploymentStatus] = Query(default=None, alias="status"),
    client_id: Optional[uuid.UUID] = Query(default=None),
    limit: int = Query(default=50, ge=1, le=200),
) -> HTMLResponse | RedirectResponse:
    """
    Render the Deployment Monitoring page (Backlog DASH-002): deployment
    status breakdown plus a filterable, most-recent-first list of
    individual deployment targets, each showing its client and deployed
    software package - "Active/recent deployments", "Per-client
    deployment status", and "Clear status presentation for Pending,
    Downloading, Installing, Completed, and Failed".

    ``status``/``client_id`` are optional query-string filters (e.g.
    ``/dashboard/deployments?status=failed``); ``limit`` bounds how many
    recent targets are shown (default 50, max 200).

    Redirects to ``/login`` if no valid administrator session is present,
    identical to ``dashboard_home`` above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    monitoring = dashboard_service.get_deployment_monitoring(
        db,
        status=status_filter,
        client_id=client_id,
        limit=limit,
    )
    clients = dashboard_service.list_clients_for_filter(db)

    rows = [
        {
            "target": target,
            "badge_class": _status_badge_class(target.status),
            "label": _status_label(target.status),
        }
        for target in monitoring.targets
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/deployments.html",
        {
            "administrator": administrator,
            "monitoring": monitoring,
            "rows": rows,
            "clients": clients,
            "statuses": list(DeploymentStatus),
            "selected_status": status_filter,
            "selected_client_id": client_id,
            "limit": limit,
        },
    )


@router.get(
    "/api/admin/dashboard/deployments",
    status_code=status.HTTP_200_OK,
    summary="Deployment monitoring overview",
    description=(
        "Return the Deployment Monitoring overview (Backlog DASH-002): the overall deployment status "
        "breakdown plus a filterable, most-recent-first list of individual deployment targets, each "
        "denormalized with its target client and deployed software package."
    ),
)
async def get_deployment_monitoring(
    db: DBSessionDependency,
    dashboard_service: DashboardServiceDependency,
    current_admin: CurrentAdministrator,
    status_filter: Optional[DeploymentStatus] = Query(
        default=None, alias="status", description="Filter targets by deployment status."
    ),
    client_id: Optional[uuid.UUID] = Query(default=None, description="Filter targets by target client id."),
    deployment_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter targets by deployment batch id."
    ),
    limit: int = Query(default=50, ge=1, le=200, description="Maximum number of targets to return."),
) -> Dict[str, Any]:
    """Return the Deployment Monitoring data as JSON (standard CPMS envelope)."""
    monitoring = dashboard_service.get_deployment_monitoring(
        db,
        status=status_filter,
        client_id=client_id,
        deployment_id=deployment_id,
        limit=limit,
    )
    logger.debug("Administrator %s requested deployment monitoring data.", current_admin.id)
    return {
        "success": True,
        "message": "Deployment monitoring data computed.",
        "data": monitoring.model_dump(mode="json"),
    }


def _day_range_to_datetimes(
    date_from: Optional[date], date_to: Optional[date]
) -> tuple[Optional[datetime], Optional[datetime]]:
    """
    Convert inclusive ``date`` query-string bounds (DASH-003's date-range
    filter, submitted by an ``<input type="date">`` field) into
    timezone-aware UTC ``datetime`` bounds suitable for comparison against
    ``AuditLog.created_at``.

    ``date_from`` becomes the start of that day (00:00:00 UTC); ``date_to``
    becomes the end of that day (23:59:59.999999 UTC), so a single-day
    filter (``date_from == date_to``) correctly includes every event
    recorded on that day rather than none.
    """
    start_dt = datetime.combine(date_from, time.min, tzinfo=timezone.utc) if date_from else None
    end_dt = datetime.combine(date_to, time.max, tzinfo=timezone.utc) if date_to else None
    return start_dt, end_dt


@router.get("/dashboard/audit-logs", response_class=HTMLResponse, response_model=None, include_in_schema=False)
async def audit_log_page(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    dashboard_service: DashboardServiceDependency,
    event_type: Optional[str] = Query(default=None),
    severity: Optional[str] = Query(default=None),
    client_id: Optional[uuid.UUID] = Query(default=None),
    date_from: Optional[date] = Query(default=None),
    date_to: Optional[date] = Query(default=None),
    search: Optional[str] = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
) -> HTMLResponse | RedirectResponse:
    """
    Render the Audit Log Viewer page (Backlog DASH-003): recorded system
    audit events, most-recent-first, with optional filtering by event
    type, severity, related client, and date range, plus free-text search
    over the event description, and pagination - "Display recorded system
    audit events", "Show useful event information...", "Provide practical
    filtering/search" (FR-016 System Logging and Audit Trail).

    ``event_type``/``severity``/``client_id``/``date_from``/``date_to``/
    ``search`` are optional query-string filters (e.g.
    ``/dashboard/audit-logs?severity=Error``); ``page``/``page_size``
    control pagination (default page size 50, max 200 - the same upper
    bound already used by ``/dashboard/deployments``).

    Redirects to ``/login`` if no valid administrator session is present,
    identical to ``dashboard_home``/``deployment_monitoring_page`` above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    date_from_dt, date_to_dt = _day_range_to_datetimes(date_from, date_to)

    result = dashboard_service.get_audit_logs(
        db,
        event_type=event_type or None,
        severity=severity or None,
        client_id=client_id,
        date_from=date_from_dt,
        date_to=date_to_dt,
        search=search or None,
        page=page,
        page_size=page_size,
    )
    clients = dashboard_service.list_clients_for_filter(db)

    rows = [
        {"entry": entry, "badge_class": _severity_badge_class(entry.severity)} for entry in result.entries
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/audit_logs.html",
        {
            "administrator": administrator,
            "result": result,
            "rows": rows,
            "clients": clients,
            "selected_event_type": event_type,
            "selected_severity": severity,
            "selected_client_id": client_id,
            "selected_date_from": date_from,
            "selected_date_to": date_to,
            "selected_search": search,
            "page": page,
            "page_size": page_size,
        },
    )


@router.get(
    "/api/admin/dashboard/audit-logs",
    status_code=status.HTTP_200_OK,
    summary="Audit log viewer",
    description=(
        "Return recorded system audit events (Backlog DASH-003), optionally filtered by event type, "
        "severity, related client, related administrator, and date range, with free-text search over the "
        "event description, paginated."
    ),
)
async def get_audit_logs(
    db: DBSessionDependency,
    dashboard_service: DashboardServiceDependency,
    current_admin: CurrentAdministrator,
    event_type: Optional[str] = Query(default=None, description="Filter by exact event type."),
    severity: Optional[str] = Query(default=None, description="Filter by exact severity."),
    client_id: Optional[uuid.UUID] = Query(default=None, description="Filter by related client id."),
    admin_id: Optional[uuid.UUID] = Query(
        default=None, description="Filter by related administrator id."
    ),
    date_from: Optional[date] = Query(
        default=None, description="Only include events recorded on/after this date (UTC)."
    ),
    date_to: Optional[date] = Query(
        default=None, description="Only include events recorded on/before this date (UTC)."
    ),
    search: Optional[str] = Query(
        default=None, description="Free-text, case-insensitive search over the event description/type."
    ),
    page: int = Query(default=1, ge=1, description="1-indexed page number."),
    page_size: int = Query(default=50, ge=1, le=200, description="Maximum number of entries per page."),
) -> Dict[str, Any]:
    """Return a page of audit log entries as JSON (standard CPMS envelope)."""
    date_from_dt, date_to_dt = _day_range_to_datetimes(date_from, date_to)

    result = dashboard_service.get_audit_logs(
        db,
        event_type=event_type,
        severity=severity,
        client_id=client_id,
        admin_id=admin_id,
        date_from=date_from_dt,
        date_to=date_to_dt,
        search=search,
        page=page,
        page_size=page_size,
    )
    logger.debug("Administrator %s requested audit logs (page=%s).", current_admin.id, page)
    return {
        "success": True,
        "message": "Audit log entries retrieved.",
        "data": result.model_dump(mode="json"),
    }
