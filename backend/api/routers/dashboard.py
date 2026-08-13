"""
Dashboard router (Backlog DASH-001 - "Dashboard Home"; DASH-002 -
"Deployment Monitoring"; DASH-003 - "Audit Log Viewer"; DASH-004 -
"Client Management Dashboard").

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
    * ``GET /dashboard/clients`` (DASH-004) - the Client List page: every
      registered client, with effective status (FR-014), optionally
      filtered by a hostname/IP substring and/or status. Uses the exact
      same session-cookie/redirect-to-``/login`` pattern as the pages
      above.
    * ``GET /dashboard/clients/{client_id}`` (DASH-004) - the Client
      Detail page: one client's identifying/status information plus its
      recent deployment history, reusing ``get_deployment_monitoring``
      (DASH-002) filtered by ``client_id`` - no deployment query logic is
      duplicated. Renders a dashboard-friendly 404 page (not a raw
      traceback) if ``client_id`` is unknown.
    * ``GET /dashboard/clients/{client_id}/software`` (DASH-004) - the
      Client Software page: a client's installed software with its
      FR-007 update status, reusing ``VersionComparisonService.
      compare_client_inventory`` unmodified. Same 404 handling as above.
    * ``GET /api/admin/dashboard/clients``, ``GET
      /api/admin/dashboard/clients/{client_id}``, and ``GET
      /api/admin/dashboard/clients/{client_id}/software`` (DASH-004) -
      JSON counterparts of the three pages above, grouped under
      ``/api/admin`` alongside the other Dashboard Module JSON endpoints.

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
    CSRFProtection,
    CurrentAdministrator,
    DBSessionDependency,
    DashboardServiceDependency,
    RepositoryServiceDependency,
    SettingsDependency,
    SystemConfigurationServiceDependency,
)
from backend.schemas.system_configuration import SystemConfigurationUpdateRequest 
from backend.api.routers.updates import ClientNotFoundError
from backend.core.config import BASE_DIR
from backend.models.administrator import Administrator
from backend.models.enums import ApprovalStatus, ClientStatus, DeploymentStatus, UpdateStatus
from backend.services.auth_service import AuthenticationError
from backend.services.repository_service import RepositoryPackageNotFoundError
from backend.api.dependencies import SystemConfigurationServiceDependency  # add to existing import group
from backend.schemas.system_configuration import SystemConfigurationUpdateRequest


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


# Bootstrap badge classes for FR-007 update status (DASH-004 - "Expected
# status presentation: Up to Date (green badge), Update Available
# (yellow badge), Not Managed (gray badge)"). Keyed by enum member
# *name*, matching the convention already established by
# ``_STATUS_BADGE_CLASS`` above.
_UPDATE_STATUS_BADGE_CLASS: Dict[str, str] = {
    "UP_TO_DATE": "text-bg-success",
    "UPDATE_AVAILABLE": "text-bg-warning text-dark",
    "NOT_MANAGED": "text-bg-secondary",
}


def _update_status_badge_class(update_status: UpdateStatus) -> str:
    """Bootstrap badge class for a software item's FR-007 ``UpdateStatus`` (DASH-004)."""
    return _UPDATE_STATUS_BADGE_CLASS.get(update_status.name, "text-bg-light text-dark border")


# Bootstrap badge classes for a repository package's FR-006/FR-017
# ``ApprovalStatus`` (DASH-005 - "Package status is visible"). Keyed by
# enum member *name*, matching the convention already established by
# ``_STATUS_BADGE_CLASS``/``_UPDATE_STATUS_BADGE_CLASS`` above.
_APPROVAL_STATUS_BADGE_CLASS: Dict[str, str] = {
    "APPROVED": "text-bg-success",
    "INACTIVE": "text-bg-secondary",
}


def _approval_status_badge_class(approval_status: ApprovalStatus) -> str:
    """Bootstrap badge class for a repository package's ``ApprovalStatus`` (DASH-005)."""
    return _APPROVAL_STATUS_BADGE_CLASS.get(approval_status.name, "text-bg-light text-dark border")


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


# --- Client Management (DASH-004) -------------------------------------


@router.get(
    "/dashboard/clients",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def client_list_page(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    dashboard_service: DashboardServiceDependency,
    search: Optional[str] = Query(default=None),
    status_filter: Optional[ClientStatus] = Query(default=None, alias="status"),
) -> HTMLResponse | RedirectResponse:
    """
    Render the Client List page (Backlog DASH-004 - "Client List"):
    every registered client, with effective status (FR-014), optionally
    filtered by a case-insensitive hostname/IP substring and/or status.

    ``search``/``status`` are optional query-string filters (e.g.
    ``/dashboard/clients?status=Offline``), mirroring the query-param
    convention already established by ``deployment_monitoring_page``.

    Redirects to ``/login`` if no valid administrator session is present,
    identical to every other dashboard page route above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    result = dashboard_service.get_client_list(db, search=search or None, status_filter=status_filter)

    return templates.TemplateResponse(
        request,
        "dashboard/clients.html",
        {
            "administrator": administrator,
            "result": result,
            "statuses": list(ClientStatus),
            "selected_search": search,
            "selected_status": status_filter,
        },
    )


@router.get(
    "/api/admin/dashboard/clients",
    status_code=status.HTTP_200_OK,
    summary="Client list",
    description=(
        "Return every registered client (Backlog DASH-004), with effective status (FR-014), optionally "
        "filtered by a case-insensitive hostname/IP substring and/or status."
    ),
)
async def get_client_list(
    db: DBSessionDependency,
    dashboard_service: DashboardServiceDependency,
    current_admin: CurrentAdministrator,
    search: Optional[str] = Query(default=None, description="Case-insensitive hostname/IP substring filter."),
    status_filter: Optional[ClientStatus] = Query(
        default=None, alias="status", description="Filter by effective client status."
    ),
) -> Dict[str, Any]:
    """Return the Client List data as JSON (standard CPMS envelope)."""
    result = dashboard_service.get_client_list(db, search=search, status_filter=status_filter)
    logger.debug("Administrator %s requested client list (search=%s, status=%s).", current_admin.id, search, status_filter)
    return {
        "success": True,
        "message": "Client list retrieved.",
        "data": result.model_dump(mode="json"),
    }


@router.get(
    "/dashboard/clients/{client_id}",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def client_detail_page(
    request: Request,
    client_id: uuid.UUID,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    dashboard_service: DashboardServiceDependency,
) -> HTMLResponse | RedirectResponse:
    """
    Render the Client Detail page (Backlog DASH-004 - "Client Detail"):
    a single client's identifying/status information plus its recent
    deployment history (reused from DASH-002 via
    ``DashboardService.get_client_detail`` -> ``get_deployment_monitoring``
    filtered by ``client_id``; no deployment query logic is duplicated
    here).

    Renders a dashboard-friendly 404 page (not a raw traceback or bare
    JSON body) if ``client_id`` does not match any registered client.

    Redirects to ``/login`` if no valid administrator session is present,
    identical to every other dashboard page route above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    detail = dashboard_service.get_client_detail(db, client_id)
    if detail is None:
        return templates.TemplateResponse(
            request,
            "dashboard/not_found.html",
            {
                "administrator": administrator,
                "message": f"No client was found with id {client_id}.",
                "back_url": "/dashboard/clients",
                "back_label": "Back to Clients",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    rows = [
        {
            "target": target,
            "badge_class": _status_badge_class(target.status),
            "label": _status_label(target.status),
        }
        for target in detail.deployment_targets
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/client_detail.html",
        {
            "administrator": administrator,
            "detail": detail,
            "rows": rows,
        },
    )


@router.get(
    "/api/admin/dashboard/clients/{client_id}",
    status_code=status.HTTP_200_OK,
    summary="Client detail",
    description=(
        "Return a single client's detail, including its recent deployment history (Backlog DASH-004)."
    ),
)
async def get_client_detail(
    client_id: uuid.UUID,
    db: DBSessionDependency,
    dashboard_service: DashboardServiceDependency,
    current_admin: CurrentAdministrator,
) -> Dict[str, Any]:
    """
    Return a single client's detail data as JSON (standard CPMS
    envelope). Raises ``ClientNotFoundError`` (404) if ``client_id`` does
    not match any registered client - the same exception, and the same
    404 semantics, already used by ``GET
    /api/admin/clients/{client_id}/updates`` (``backend/api/routers/
    updates.py``), reused here rather than redefined.
    """
    detail = dashboard_service.get_client_detail(db, client_id)
    if detail is None:
        raise ClientNotFoundError(client_id)

    logger.debug("Administrator %s requested client detail for %s.", current_admin.id, client_id)
    return {
        "success": True,
        "message": "Client detail retrieved.",
        "data": detail.model_dump(mode="json"),
    }


@router.get(
    "/dashboard/clients/{client_id}/software",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def client_software_page(
    request: Request,
    client_id: uuid.UUID,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    dashboard_service: DashboardServiceDependency,
    search: Optional[str] = Query(default=None),
    publisher: Optional[str] = Query(default=None),
) -> HTMLResponse | RedirectResponse:
    """
    Render the Client Software page (Backlog DASH-004 - "Client Software
    / Inventory"): every installed software item for a client, with its
    FR-007 update status, reusing ``VersionComparisonService.
    compare_client_inventory`` unmodified via
    ``DashboardService.get_client_software`` - no second version-
    comparison implementation is introduced by this ticket.

    ``search``/``publisher`` are optional query-string filters over the
    software name and publisher, respectively (case-insensitive
    substring match).

    Renders a dashboard-friendly 404 page if ``client_id`` does not match
    any registered client. Redirects to ``/login`` if no valid
    administrator session is present, identical to every other dashboard
    page route above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    software = dashboard_service.get_client_software(
        db,
        client_id,
        search=search or None,
        publisher=publisher or None,
    )
    if software is None:
        return templates.TemplateResponse(
            request,
            "dashboard/not_found.html",
            {
                "administrator": administrator,
                "message": f"No client was found with id {client_id}.",
                "back_url": "/dashboard/clients",
                "back_label": "Back to Clients",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    rows = [
        {"item": item, "badge_class": _update_status_badge_class(item.status)} for item in software.items
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/client_software.html",
        {
            "administrator": administrator,
            "software": software,
            "rows": rows,
            "selected_search": search,
            "selected_publisher": publisher,
        },
    )


@router.get(
    "/api/admin/dashboard/clients/{client_id}/software",
    status_code=status.HTTP_200_OK,
    summary="Client software inventory with FR-007 update status",
    description=(
        "Return a client's installed software with FR-007 update status (Backlog DASH-004), optionally "
        "filtered by a case-insensitive software-name and/or publisher substring."
    ),
)
async def get_client_software(
    client_id: uuid.UUID,
    db: DBSessionDependency,
    dashboard_service: DashboardServiceDependency,
    current_admin: CurrentAdministrator,
    search: Optional[str] = Query(default=None, description="Case-insensitive software-name substring filter."),
    publisher: Optional[str] = Query(default=None, description="Case-insensitive publisher substring filter."),
) -> Dict[str, Any]:
    """
    Return a client's software inventory + FR-007 update status as JSON
    (standard CPMS envelope). Raises ``ClientNotFoundError`` (404) if
    ``client_id`` does not match any registered client.
    """
    software = dashboard_service.get_client_software(db, client_id, search=search, publisher=publisher)
    if software is None:
        raise ClientNotFoundError(client_id)

    logger.debug(
        "Administrator %s requested software inventory for client %s (search=%s, publisher=%s).",
        current_admin.id,
        client_id,
        search,
        publisher,
    )
    return {
        "success": True,
        "message": "Client software inventory retrieved.",
        "data": software.model_dump(mode="json"),
    }


# --- Repository Package Browser (DASH-005) ------------------------------


@router.get(
    "/dashboard/repository",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def repository_list_page(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    repository_service: RepositoryServiceDependency,
    search: Optional[str] = Query(default=None),
    status_filter: Optional[ApprovalStatus] = Query(default=None, alias="status"),
) -> HTMLResponse | RedirectResponse:
    """
    Render the Repository Package Browser list page (Backlog DASH-005 -
    "Repository Package List"): every repository package (FR-006),
    optionally filtered by a case-insensitive software-name/version
    substring and/or approval status.

    Reuses ``RepositoryService.list_packages`` (REP-001/REP-002)
    unmodified - the exact same method already backing the existing
    ``GET /api/admin/repository/packages`` JSON endpoint
    (``backend/api/routers/repository.py``) - so no repository query
    logic is duplicated by this ticket. ``RepositoryServiceDependency``
    is injected directly (rather than via a new ``DashboardService``
    passthrough method), consistent with this ticket's "prefer reusing
    ... rather than creating parallel repository/service classes"
    constraint and the architecture note that the router may sit atop
    "DashboardService / existing Service" interchangeably.

    ``search``/``status`` are optional query-string filters (e.g.
    ``/dashboard/repository?status=Inactive``), mirroring the query-param
    convention already established by ``client_list_page``.

    Redirects to ``/login`` if no valid administrator session is present,
    identical to every other dashboard page route above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    packages = repository_service.list_packages(db, search=search or None, approval_status=status_filter)

    rows = [
        {"package": package, "badge_class": _approval_status_badge_class(package.approval_status)}
        for package in packages
    ]

    return templates.TemplateResponse(
        request,
        "dashboard/repository.html",
        {
            "administrator": administrator,
            "rows": rows,
            "total": len(packages),
            "statuses": list(ApprovalStatus),
            "selected_search": search,
            "selected_status": status_filter,
        },
    )


@router.get(
    "/dashboard/repository/{package_id}",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def repository_detail_page(
    request: Request,
    package_id: uuid.UUID,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    repository_service: RepositoryServiceDependency,
    deactivated: bool = Query(default=False),
) -> HTMLResponse | RedirectResponse:
    """
    Render the Repository Package Detail page (Backlog DASH-005 -
    "Package Detail"): a single package's full metadata (FR-006 Repository
    Metadata), plus a Deactivate action.

    The Deactivate button (see ``dashboard/repository_detail.html``) posts
    directly, via client-side JavaScript, to the existing, already-secured
    ``POST /api/admin/repository/packages/{package_id}/deactivate``
    endpoint (REP-002/FR-017) - carrying the same administrator session
    cookie and ``X-CSRF-Token`` header (NFR-028) every other state-changing
    dashboard action already requires. No second deactivation mechanism,
    and no new state-changing route, is introduced by this ticket.

    Renders a dashboard-friendly 404 page (not a raw JSON body) if
    ``package_id`` does not match any repository package, by catching
    ``RepositoryPackageNotFoundError`` here - the same exception (and the
    same 404 semantics) already raised by ``RepositoryService.get_package``
    for the existing ``GET /api/admin/repository/packages/{package_id}``
    JSON endpoint - rather than letting the global ``AppException`` JSON
    handler produce a bare JSON body for what is otherwise an HTML page
    request.

    ``deactivated=1`` (set by the client-side redirect after a successful
    deactivation) renders a one-time success banner.

    Redirects to ``/login`` if no valid administrator session is present,
    identical to every other dashboard page route above.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    try:
        package = repository_service.get_package(db, package_id)
    except RepositoryPackageNotFoundError:
        return templates.TemplateResponse(
            request,
            "dashboard/not_found.html",
            {
                "administrator": administrator,
                "message": f"No repository package was found with id {package_id}.",
                "back_url": "/dashboard/repository",
                "back_label": "Back to Repository",
            },
            status_code=status.HTTP_404_NOT_FOUND,
        )

    return templates.TemplateResponse(
        request,
        "dashboard/repository_detail.html",
        {
            "administrator": administrator,
            "package": package,
            "badge_class": _approval_status_badge_class(package.approval_status),
            "deactivated": deactivated,
        },
    )
# --- System Configuration (SYS-001) ---------------------------------------
#
# Append these two routes to the end of backend/api/routers/dashboard.py,
# after the DASH-005 repository_detail_page route. Add the two imports
# noted above to the top of the file first.


@router.get(
    "/dashboard/settings",
    response_class=HTMLResponse,
    response_model=None,
    include_in_schema=False,
)
async def settings_page(
    request: Request,
    db: DBSessionDependency,
    auth_service: AuthServiceDependency,
    settings: SettingsDependency,
    config_service: SystemConfigurationServiceDependency,
    saved: bool = Query(default=False),
) -> HTMLResponse | RedirectResponse:
    """
    Render the System Configuration ("Settings") page (SYS-001 - FR-018
    System Configuration Management): the current effective value of
    every SYS-001-managed setting, editable and saved via
    ``POST /api/admin/settings`` below.

    Uses the exact same session-cookie/redirect-to-``/login`` pattern as
    every other dashboard page route in this file. ``saved=1`` (set by
    the client-side redirect after a successful save, the same
    convention already used by ``repository_detail_page``'s
    ``deactivated=1``) renders a one-time success banner.
    """
    administrator = _resolve_administrator_or_none(request, db, auth_service, settings)
    if administrator is None:
        return RedirectResponse(url="/login", status_code=status.HTTP_302_FOUND)

    values = config_service.get_effective_settings(db, settings)

    return templates.TemplateResponse(
        request,
        "dashboard/settings.html",
        {
            "administrator": administrator,
            "values": values,
            "saved": saved,
        },
    )


@router.post(
    "/api/admin/settings",
    status_code=status.HTTP_200_OK,
    summary="Update system configuration",
    description=(
        "Validate and persist the CPMS system configuration values managed by SYS-001 (FR-018): "
        "administrator session timeout, client heartbeat timeout, and maximum installer upload size. "
        "Records an audit log entry describing what changed."
    ),
)
async def update_settings(
    request: SystemConfigurationUpdateRequest,
    db: DBSessionDependency,
    settings: SettingsDependency,
    config_service: SystemConfigurationServiceDependency,
    current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
) -> Dict[str, Any]:
    """
    Persist a new set of SYS-001-managed setting values (FR-018).

    Requires both an active administrator session and a valid CSRF token
    (NFR-028), the same pattern used by every other state-changing
    administrator endpoint in this codebase (e.g.
    ``POST /api/admin/repository/packages/{package_id}/deactivate``).
    Field-level validation (positive integers, sensible upper bounds) is
    enforced by ``SystemConfigurationUpdateRequest`` before this handler
    runs; FastAPI returns 422 automatically for values outside those
    bounds, so no explicit validation-error branch is needed here.
    """
    previous = config_service.get_effective_settings(db, settings)
    updated = config_service.update_settings(
        db,
        admin_id=current_admin.id,
        request=request,
        previous=previous,
    )

    logger.info(
        "Administrator %s updated system configuration via /api/admin/settings.",
        current_admin.id,
    )

    return {
        "success": True,
        "message": "Configuration saved successfully.",
        "data": updated.model_dump(mode="json"),
    }