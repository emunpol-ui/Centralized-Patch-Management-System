"""
Dashboard service.

Contains the business logic behind the Dashboard Home overview (Backlog
DASH-001 - "Statistics", "Client summary", "Deployment summary",
"Repository summary") and the Deployment Monitoring page (Backlog
DASH-002 - "Deployment overview/statistics", "Deployment status
breakdown", "Active/recent deployments", "Per-client deployment
status") and, as of DASH-003, the Audit Log Viewer ("Display recorded
system audit events", "Provide practical filtering/search"), per the
Service Layer Pattern (SAD Section 5.5, Section 9.6 "Dashboard
Module").

This service performs no writes and enforces no business rules beyond
computing display-ready aggregates; it purely composes four
already-existing, already-completed repositories:

    * ``ClientRepository`` (AUTH-002/CLIENT-001/CLIENT-002) for the
      client summary.
    * ``DeploymentRepository`` (DEPLOY-001..004) for the deployment
      summary and, as of DASH-002, the deployment-target detail list.
    * ``RepositoryPackageRepository`` (INV-002/REP-001/REP-002) for the
      repository summary.
    * ``AuditLogRepository`` (CORE-002) for the Audit Log Viewer
      (DASH-003), used here purely for reads - the write path used by
      every other ticket to record events is untouched.

No new database table, column, or migration is introduced - every figure
below is derived entirely from existing columns.

--------------------------------------------------------------------------
DESIGN NOTE - effective client online/offline status is computed here,
not read from ``Client.status``

``Client.status`` (CORE-002) is only ever written by
``HeartbeatService.record_heartbeat`` (CLIENT-002), which sets it to
``ONLINE`` on every heartbeat. Nothing in the codebase so far has ever
transitioned it back to ``OFFLINE`` - CURRENT_STATE.md's own Architecture
Notes explicitly document this as a deliberate, standing design choice
("Client `OFFLINE` status is computed at read time... rather than updated
by a background job") that no ticket had actually implemented yet because
no feature needed it until now. DASH-001's client summary is the first
consumer of that computation: a client is classified ``ONLINE`` if it has
heartbeated within ``Settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES``,
``OFFLINE`` if its last heartbeat is older than that, and ``UNKNOWN`` if
it has never sent one (registered but not yet heartbeated) - the same
three-value vocabulary already defined by ``ClientStatus``. This is a
read-only, display-only computation: it never writes to ``Client.status``
or any other column, so it introduces no risk of interfering with
``HeartbeatService``, ``ClientAuthService``, or any other module that
reads or writes that field.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import List, Optional

from sqlalchemy.orm import Session

from backend.core.config import Settings, get_settings
from backend.models.client import Client
from backend.models.enums import ApprovalStatus, ClientStatus, DeploymentStatus
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.client_repository import ClientRepository
from backend.repositories.deployment_repository import DeploymentRepository
from backend.repositories.repository_package_repository import RepositoryPackageRepository
from backend.schemas.audit_log import AuditLogEntry, AuditLogListResponse
from backend.schemas.dashboard import (
    ClientSummary,
    DashboardStatsResponse,
    DeploymentSummary,
    RepositorySummary,
    SystemOverview,
)
from backend.schemas.deployment_monitor import DeploymentMonitoringResponse, DeploymentTargetDetail

logger = logging.getLogger(__name__)


class DashboardService:
    """
    Dashboard Home overview aggregation (DASH-001) and Deployment
    Monitoring aggregation (DASH-002).

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase.
    """

    def __init__(
        self,
        client_repository: ClientRepository | None = None,
        deployment_repository: DeploymentRepository | None = None,
        repository_package_repository: RepositoryPackageRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._clients = client_repository or ClientRepository()
        self._deployments = deployment_repository or DeploymentRepository()
        self._packages = repository_package_repository or RepositoryPackageRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()
        self._settings = settings or get_settings()

    # --- Client summary -------------------------------------------------

    def _effective_client_status(self, *, last_heartbeat: datetime | None, now: datetime) -> ClientStatus:
        """
        Classify a client's *effective*, read-time status - see the
        module docstring's design note for why this is not simply
        ``Client.status``.

        ``last_heartbeat`` is stored as ``DateTime(timezone=True)``
        (``backend/models/client.py``), but SQLite - unlike PostgreSQL -
        does not actually preserve timezone information: SQLAlchemy
        returns it as a naive ``datetime`` on this prototype's database.
        A naive value is therefore treated as UTC (the same convention
        used everywhere a timestamp is written in this codebase, e.g.
        ``ClientRepository.update_heartbeat``'s
        ``datetime.now(timezone.utc)``) before comparing it against the
        timezone-aware ``now``, to avoid ``TypeError: can't subtract
        offset-naive and offset-aware datetimes``.
        """
        if last_heartbeat is None:
            return ClientStatus.UNKNOWN
        if last_heartbeat.tzinfo is None:
            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)
        timeout = timedelta(minutes=self._settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES)
        return ClientStatus.ONLINE if (now - last_heartbeat) <= timeout else ClientStatus.OFFLINE

    def get_client_summary(self, db: Session) -> ClientSummary:
        """Return registered-client counts by effective status (FR-014)."""
        clients = self._clients.list_all(db)
        now = datetime.now(timezone.utc)

        online = offline = unknown = 0
        for client in clients:
            effective = self._effective_client_status(last_heartbeat=client.last_heartbeat, now=now)
            if effective is ClientStatus.ONLINE:
                online += 1
            elif effective is ClientStatus.OFFLINE:
                offline += 1
            else:
                unknown += 1

        return ClientSummary(total=len(clients), online=online, offline=offline, unknown=unknown)

    def list_clients_for_filter(self, db: Session) -> List[Client]:
        """
        Return every registered ``Client``, for the Deployment Monitoring
        page's client filter dropdown (DASH-002).

        A thin passthrough to ``ClientRepository.list_all`` (already used
        internally by ``get_client_summary`` above). Exposed as a public
        method - rather than accessing the private ``self._clients``
        attribute from the router - so the Presentation/API Layer only
        ever talks to the Service Layer, per the established layering
        (SAD Section 4.4/17 "Business Logic Placement").
        """
        return self._clients.list_all(db)

    # --- Deployment summary ----------------------------------------------

    def get_deployment_summary(self, db: Session) -> DeploymentSummary:
        """Return deployment batch/target counts (FR-008 through FR-013, FR-021)."""
        counts = self._deployments.count_targets_by_status(db)

        pending = counts.get(DeploymentStatus.PENDING, 0)
        downloading = counts.get(DeploymentStatus.DOWNLOADING, 0)
        installing = counts.get(DeploymentStatus.INSTALLING, 0)
        completed = counts.get(DeploymentStatus.COMPLETED, 0)
        failed = counts.get(DeploymentStatus.FAILED, 0)
        cancelled = counts.get(DeploymentStatus.CANCELLED, 0)

        return DeploymentSummary(
            total_batches=self._deployments.count_deployments(db),
            total_targets=pending + downloading + installing + completed + failed + cancelled,
            pending=pending,
            downloading=downloading,
            installing=installing,
            completed=completed,
            failed=failed,
            cancelled=cancelled,
            active=pending + downloading + installing,
        )

    # --- Deployment monitoring (DASH-002) ---------------------------------

    def get_deployment_monitoring(
        self,
        db: Session,
        *,
        status: Optional[DeploymentStatus] = None,
        client_id: Optional[uuid.UUID] = None,
        deployment_id: Optional[uuid.UUID] = None,
        limit: int = 50,
    ) -> DeploymentMonitoringResponse:
        """
        Return the complete Deployment Monitoring payload (Backlog
        DASH-002): the overall deployment status breakdown (reusing
        ``get_deployment_summary`` above, unaffected by the filters below
        - it always reflects ALL targets, matching the Dashboard Home
        Deployment Summary card) plus a filtered/limited list of
        individual ``DeploymentTarget`` rows, each denormalized with its
        client and software package details so the administrator can see
        "Active/recent deployments" and "Per-client deployment status" in
        a single table without further lookups.

        ``status``/``client_id``/``deployment_id`` are optional filters
        (all AND-ed together when more than one is supplied);
        ``limit`` bounds how many recent targets are returned. Reuses
        ``DeploymentRepository.list_target_details`` (added by this same
        ticket) for the underlying joined query - no deployment logic is
        duplicated here beyond composing that query's rows into DTOs.
        """
        summary = self.get_deployment_summary(db)

        rows = self._deployments.list_target_details(
            db,
            status=status,
            client_id=client_id,
            deployment_id=deployment_id,
            limit=limit,
        )

        targets = [
            DeploymentTargetDetail(
                target_id=target.id,
                deployment_id=target.deployment_id,
                client_id=target.client_id,
                client_hostname=client.hostname,
                client_ip_address=client.ip_address,
                software_name=package.software_name,
                software_version=package.version,
                status=target.status,
                created_at=target.created_at,
                completion_time=target.completion_time,
                exit_code=target.exit_code,
                error_message=target.error_message,
            )
            for target, deployment, client, package in rows
        ]

        logger.debug(
            "Deployment monitoring computed: filters(status=%s, client_id=%s, deployment_id=%s, "
            "limit=%s) returned %s target(s).",
            status,
            client_id,
            deployment_id,
            limit,
            len(targets),
        )

        return DeploymentMonitoringResponse(summary=summary, targets=targets)

    # --- Audit log viewer (DASH-003) --------------------------------------

    def get_audit_logs(
        self,
        db: Session,
        *,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        client_id: Optional[uuid.UUID] = None,
        admin_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        page: int = 1,
        page_size: int = 50,
    ) -> AuditLogListResponse:
        """
        Return a page of audit log entries (Backlog DASH-003 - "Display
        recorded system audit events", "Show useful event information...",
        "Provide practical filtering/search"), most-recent-first, together
        with pagination metadata and the distinct event-type/severity
        values currently present in the log (used to populate the filter
        dropdowns on both the HTML page and any future consumer of the
        JSON endpoint).

        Reuses the existing, already-implemented ``AuditLogRepository``
        (CORE-002) purely for reads - no new write path, table, column, or
        migration is introduced by this ticket. ``event_type``/``severity``
        are matched exactly (as populated by the filter dropdowns, which
        are themselves sourced from the distinct values already present in
        the log); ``search`` performs a case-insensitive substring match
        against the event description and event type, for administrators
        who don't know the exact stored spelling of either.

        ``page``/``page_size`` are clamped to sane bounds here (rather than
        solely at the API/router boundary) so this method is safe to call
        directly with untrusted values from any future caller.
        """
        page = max(page, 1)
        page_size = max(min(page_size, 200), 1)
        offset = (page - 1) * page_size

        total = self._audit_logs.count_logs(
            db,
            event_type=event_type,
            severity=severity,
            client_id=client_id,
            admin_id=admin_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        rows = self._audit_logs.list_log_details(
            db,
            event_type=event_type,
            severity=severity,
            client_id=client_id,
            admin_id=admin_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
            limit=page_size,
            offset=offset,
        )

        entries = [
            AuditLogEntry(
                id=log.id,
                timestamp=log.timestamp,
                event_type=log.event_type,
                severity=log.severity,
                client_id=log.client_id,
                client_hostname=client.hostname if client is not None else None,
                admin_id=log.admin_id,
                admin_username=admin.username if admin is not None else None,
                description=log.description,
            )
            for log, client, admin in rows
        ]

        total_pages = (total + page_size - 1) // page_size if total else 0

        logger.debug(
            "Audit log query: filters(event_type=%s, severity=%s, client_id=%s, admin_id=%s, "
            "date_from=%s, date_to=%s, search=%s) page=%s page_size=%s returned %s of %s entrie(s).",
            event_type,
            severity,
            client_id,
            admin_id,
            date_from,
            date_to,
            search,
            page,
            page_size,
            len(entries),
            total,
        )

        return AuditLogListResponse(
            entries=entries,
            total=total,
            page=page,
            page_size=page_size,
            total_pages=total_pages,
            event_types=self._audit_logs.list_distinct_event_types(db),
            severities=self._audit_logs.list_distinct_severities(db),
        )

    # --- Repository summary ----------------------------------------------

    def get_repository_summary(self, db: Session) -> RepositorySummary:
        """Return repository package counts by approval status (FR-006, FR-017)."""
        packages = self._packages.list_all(db)
        approved = sum(1 for package in packages if package.approval_status == ApprovalStatus.APPROVED)
        inactive = sum(1 for package in packages if package.approval_status == ApprovalStatus.INACTIVE)
        return RepositorySummary(total=len(packages), approved=approved, inactive=inactive)

    # --- Combined overview -------------------------------------------------

    def get_overview(self, db: Session) -> DashboardStatsResponse:
        """
        Return the complete Dashboard Home payload: system overview plus
        all three summaries, computed from a single call so both the JSON
        API and the server-rendered template share one code path.
        """
        system = SystemOverview(
            app_name=self._settings.APP_NAME,
            app_version=self._settings.APP_VERSION,
            environment=self._settings.APP_ENV,
            server_time=datetime.now(timezone.utc),
        )
        overview = DashboardStatsResponse(
            system=system,
            clients=self.get_client_summary(db),
            deployments=self.get_deployment_summary(db),
            repository=self.get_repository_summary(db),
        )
        logger.debug(
            "Dashboard overview computed: clients=%s deployments=%s repository=%s",
            overview.clients,
            overview.deployments,
            overview.repository,
        )
        return overview
