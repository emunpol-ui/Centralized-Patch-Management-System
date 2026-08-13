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
computing display-ready aggregates; it purely composes already-existing,
already-completed repositories and services:

    * ``ClientRepository`` (AUTH-002/CLIENT-001/CLIENT-002) for the
      client summary and, as of DASH-004, the Client Management pages.
    * ``DeploymentRepository`` (DEPLOY-001..004) for the deployment
      summary and, as of DASH-002, the deployment-target detail list
      (also reused by DASH-004's Client Detail page for a single
      client's deployment history).
    * ``RepositoryPackageRepository`` (INV-002/REP-001/REP-002) for the
      repository summary.
    * ``AuditLogRepository`` (CORE-002) for the Audit Log Viewer
      (DASH-003), used here purely for reads - the write path used by
      every other ticket to record events is untouched.
    * ``SoftwareInventoryRepository`` (INV-001), used as of DASH-004
      purely to read each inventory record's ``install_date`` for
      display - see the design note on ``get_client_software`` below for
      why this repository is consulted directly rather than extending
      ``VersionComparisonService``.
    * ``VersionComparisonService`` (INV-002/UPDATE-001), used as of
      DASH-004 to compute the Client Software page's per-item FR-007
      status - reused unmodified; this ticket introduces no second
      version-comparison implementation.

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
from backend.models.enums import ApprovalStatus, ClientStatus, DeploymentStatus, UpdateStatus
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.client_repository import ClientRepository
from backend.repositories.deployment_repository import DeploymentRepository
from backend.repositories.repository_package_repository import RepositoryPackageRepository
from backend.repositories.software_inventory_repository import SoftwareInventoryRepository
from backend.schemas.audit_log import AuditLogEntry, AuditLogListResponse
from backend.schemas.client_dashboard import (
    ClientDetailResponse,
    ClientListItem,
    ClientListResponse,
    ClientSoftwareItem,
    ClientSoftwareResponse,
)
from backend.schemas.dashboard import (
    ClientSummary,
    DashboardStatsResponse,
    DeploymentSummary,
    RepositorySummary,
    SystemOverview,
)
from backend.schemas.deployment_monitor import DeploymentMonitoringResponse, DeploymentTargetDetail
from backend.schemas.updates import ClientUpdateStatusSummary
from backend.services.version_comparison_service import VersionComparisonService
from backend.repositories.system_configuration_repository import SystemConfigurationRepository

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
        software_inventory_repository: SoftwareInventoryRepository | None = None,
        version_comparison_service: VersionComparisonService | None = None,
        system_configuration_repository: SystemConfigurationRepository | None = None,
        settings: Settings | None = None,
    ) -> None:
        self._clients = client_repository or ClientRepository()
        self._deployments = deployment_repository or DeploymentRepository()
        self._packages = repository_package_repository or RepositoryPackageRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()
        self._inventory = software_inventory_repository or SoftwareInventoryRepository()
        self._version_comparison = version_comparison_service or VersionComparisonService()
        # SYS-001 - resolves the *effective* client heartbeat timeout
        # (persisted override, else Settings default) used by
        # `_effective_client_status` below, instead of that method
        # reading `self._settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES`
        # directly. Defaulted the same way every other repository above
        # is, so `get_dashboard_service` (backend/api/dependencies.py)
        # needs no changes to pick this up.
        self._system_config = system_configuration_repository or SystemConfigurationRepository()
        self._settings = settings or get_settings()

    # --- Client summary -------------------------------------------------

    # AFTER:
    def _resolve_heartbeat_timeout(self, db: Session) -> timedelta:
        """
        Resolve the *effective* client heartbeat timeout (SYS-001): a
        persisted override if an administrator has saved one via the
        Settings page, otherwise ``Settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES``.

        Queried once per calling method (not once per client in a loop)
        - every caller below resolves this a single time and passes the
        result into ``_effective_client_status`` for every client it
        classifies in that call.
        """
        row = self._system_config.get_current(db)
        minutes = row.client_heartbeat_timeout_minutes if row is not None else self._settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES
        return timedelta(minutes=minutes)

    def _effective_client_status(
        self, *, last_heartbeat: datetime | None, now: datetime, timeout: timedelta
    ) -> ClientStatus:
        """
        Classify a client's *effective*, read-time status - see the
        module docstring's design note for why this is not simply
        ``Client.status``.

        ``last_heartbeat`` is stored as ``DateTime(timezone=True)``
        (``backend/models/client.py``), but SQLite - unlike PostgreSQL -
        does not actually preserve timezone information: SQLAlchemy
        returns it 
as a naive ``datetime`` on this prototype's database.
        A naive value is therefore treated as UTC (the same convention
        used everywhere a timestamp is written in this codebase, e.g.
        ``ClientRepository.update_heartbeat``'s
        ``datetime.now(timezone.utc)``) before comparing it against the
        timezone-aware ``now``, to avoid ``TypeError: can't subtract
        offset-naive and offset-aware datetimes``.

        ``timeout`` is resolved by the caller via
        ``_resolve_heartbeat_timeout`` (SYS-001), rather than computed
        here from ``self._settings`` directly, so a persisted override
        takes effect without a restart.
        """
        if last_heartbeat is None:
            return ClientStatus.UNKNOWN
        if last_heartbeat.tzinfo is None:
            last_heartbeat = last_heartbeat.replace(tzinfo=timezone.utc)
        timeout = timedelta(minutes=self._settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES)
        return ClientStatus.ONLINE if (now - last_heartbeat) <= timeout else ClientStatus.OFFLINE
    # get_client_summary — AFTER:
    def get_client_summary(self, db: Session) -> ClientSummary:
        """Return registered-client counts by effective status (FR-014)."""
        clients = self._clients.list_all(db)
        now = datetime.now(timezone.utc)
        timeout = self._resolve_heartbeat_timeout(db)

        online = offline = unknown = 0
        for client in clients:
            effective = self._effective_client_status(last_heartbeat=client.last_heartbeat, now=now, timeout=timeout)
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

    # --- Client management (DASH-004) --------------------------------------

    def get_client_list(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        status_filter: Optional[ClientStatus] = None,
    ) -> ClientListResponse:
        """
        Return every registered client (Backlog DASH-004 - "Client
        List"), optionally filtered by a case-insensitive hostname/IP
        substring and/or by effective status.

        Reuses ``ClientRepository.list_all`` (already used internally by
        ``get_client_summary`` and ``list_clients_for_filter`` above) and
        ``_effective_client_status`` (the same read-time heartbeat
        classification DASH-001/DASH-002 already rely on) - no second
        status algorithm is introduced. For a 10-20 client prototype
        deployment (PRS Section 2.5 "Scalability Constraints"), filtering
        every row in Python after a single unfiltered query is simpler
        and adequately performant; this mirrors ``get_audit_logs``'s own
        choice to keep filtering "in the simplest maintainable way" per
        this ticket's explicit instruction, without introducing a new
        paginated repository query for a dataset this small.
        """
        
        clients = self._clients.list_all(db)
        now = datetime.now(timezone.utc)
        timeout = self._resolve_heartbeat_timeout(db)
        needle = search.strip().lower() if search else None

        items: List[ClientListItem] = []
        for client in clients:
            effective_status = self._effective_client_status(
                last_heartbeat=client.last_heartbeat, now=now, timeout=timeout
            )
            if status_filter is not None and effective_status is not status_filter:
                continue
            if needle and needle not in f"{client.hostname} {client.ip_address}".lower():
                continue

            items.append(
                ClientListItem(
                    id=client.id,
                    hostname=client.hostname,
                    ip_address=client.ip_address,
                    operating_system=client.operating_system,
                    agent_version=client.agent_version,
                    status=effective_status,
                    last_heartbeat=client.last_heartbeat,
                    registration_date=client.created_at,
                )
            )

        items.sort(key=lambda item: item.hostname.lower())

        logger.debug(
            "Client list computed: filters(search=%s, status=%s) returned %s of %s client(s).",
            search,
            status_filter,
            len(items),
            len(clients),
        )

        return ClientListResponse(clients=items, total=len(items))

    def get_client_detail(
        self,
        db: Session,
        client_id: uuid.UUID,
        *,
        deployment_history_limit: int = 20,
    ) -> Optional[ClientDetailResponse]:
        """
        Return a single client's detail payload (Backlog DASH-004 -
        "Client Detail"), or ``None`` if ``client_id`` does not match any
        registered client (the router translates that into a
        dashboard-friendly 404 rather than a raw traceback, per this
        ticket's error-handling requirements).

        Deployment history is obtained by calling
        ``get_deployment_monitoring`` above with the ``client_id`` filter
        it already supports (added by DASH-002) - this method does not
        query ``DeploymentRepository`` directly nor duplicate any
        deployment-target query logic.
        """
        client = self._clients.get_by_id(db, client_id)
        if client is None:
            return None

        now = datetime.now(timezone.utc)
        timeout = self._resolve_heartbeat_timeout(db)
        effective_status = self._effective_client_status(
            last_heartbeat=client.last_heartbeat, now=now, timeout=timeout
        )

        monitoring = self.get_deployment_monitoring(db, client_id=client_id, limit=deployment_history_limit)

        return ClientDetailResponse(
            id=client.id,
            agent_guid=client.agent_guid,
            hostname=client.hostname,
            ip_address=client.ip_address,
            operating_system=client.operating_system,
            agent_version=client.agent_version,
            status=effective_status,
            last_heartbeat=client.last_heartbeat,
            registration_date=client.created_at,
            deployment_targets=monitoring.targets,
        )

    def get_client_software(
        self,
        db: Session,
        client_id: uuid.UUID,
        *,
        search: Optional[str] = None,
        publisher: Optional[str] = None,
    ) -> Optional[ClientSoftwareResponse]:
        """
        Return a single client's installed software with FR-007 update
        status (Backlog DASH-004 - "Client Software / Inventory"), or
        ``None`` if ``client_id`` does not match any registered client.

        Reuses ``VersionComparisonService.compare_client_inventory``
        (INV-002/UPDATE-001) unmodified for the actual FR-007
        classification - no second comparison implementation is
        introduced. That service's ``SoftwareUpdateStatus`` result does
        not carry ``install_date`` (it has no reason to - see its module
        docstring), so this method separately calls
        ``SoftwareInventoryRepository.list_for_client`` (already used by
        that same service internally) and merges each result's
        ``install_date`` in by ``inventory_id``, purely for display. This
        keeps ``version_comparison_service.py`` untouched, consistent
        with this ticket's "do not modify ... unless genuinely required"
        constraint.

        ``search``/``publisher`` filter the returned ``items`` list
        (case-insensitive substring match); ``summary`` always reflects
        the client's *entire* installed software set, unaffected by
        those filters - the same convention ``get_deployment_monitoring``
        already established for its own summary vs. filtered target list.
        """
        client = self._clients.get_by_id(db, client_id)
        if client is None:
            return None

        comparison_results = self._version_comparison.compare_client_inventory(db, client_id=client_id)
        inventory_records = self._inventory.list_for_client(db, client_id)
        install_dates = {record.id: record.install_date for record in inventory_records}

        name_needle = search.strip().lower() if search else None
        publisher_needle = publisher.strip().lower() if publisher else None

        items: List[ClientSoftwareItem] = []
        for result in comparison_results:
            if name_needle and name_needle not in result.software_name.lower():
                continue
            if publisher_needle and publisher_needle not in (result.publisher or "").lower():
                continue

            items.append(
                ClientSoftwareItem(
                    inventory_id=result.inventory_id,
                    software_name=result.software_name,
                    installed_version=result.installed_version,
                    publisher=result.publisher,
                    install_date=install_dates.get(result.inventory_id),
                    status=result.status,
                    approved_version=result.approved_version,
                    repository_package_id=result.repository_package_id,
                )
            )

        items.sort(key=lambda item: item.software_name.lower())

        summary = ClientUpdateStatusSummary(
            up_to_date=sum(1 for r in comparison_results if r.status == UpdateStatus.UP_TO_DATE),
            update_available=sum(1 for r in comparison_results if r.status == UpdateStatus.UPDATE_AVAILABLE),
            not_managed=sum(1 for r in comparison_results if r.status == UpdateStatus.NOT_MANAGED),
            total=len(comparison_results),
        )

        logger.debug(
            "Client software computed for client %s: filters(search=%s, publisher=%s) returned %s of %s "
            "item(s).",
            client_id,
            search,
            publisher,
            len(items),
            len(comparison_results),
        )

        return ClientSoftwareResponse(
            client_id=client.id,
            client_hostname=client.hostname,
            items=items,
            summary=summary,
        )
