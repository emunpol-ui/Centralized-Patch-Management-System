"""
Deployment service.

Contains the business logic behind administrator deployment creation
(FR-008 Deployment Job Creation, FR-009 Deployment Job Retrieval
targeting), per the Service Layer Pattern (SAD Section 5.5, Section 10.10
"Deployment Service"). Coordinates the ``Deployment``/``DeploymentTarget``,
``RepositoryPackage``, ``Client``, and Audit Log repositories, enforcing:

    1. The selected repository package exists and is currently
       ``Approved`` (FR-006/FR-017: a deployment must not target an
       unknown or deactivated/removed package).
    2. Every requested target client exists (rejecting any unknown
       client id).
    3. No target client is listed more than once within the same request
       (also enforced at the schema layer -
       ``backend.schemas.deployment.DeploymentCreateRequest`` - but
       re-checked here since the service is the authoritative boundary).
    4. No target client already has an active (non-terminal) deployment
       in progress (Business Rule 9, PRS Section 2.7: "A client may
       process only one deployment job at a time").
    5. The deployment batch and all of its per-client targets are created
       atomically: if any validation fails, nothing is persisted (no
       ``db.commit()`` is ever reached on a failure path, and this
       service's caller - the FastAPI request lifecycle via
       ``backend.database.session.get_db`` - closes the session without
       committing, discarding any flushed-but-uncommitted rows).

Deployment *execution* (installer download, silent installation, status
reporting) belongs to DEPLOY-003/DEPLOY-004 and remains out of scope here.

--------------------------------------------------------------------------
DEPLOY-002 ADDITION - ``poll_pending_deployment``

Implements FR-009 Deployment Job Retrieval (Client Polling): given the
*authenticated* client identity, resolve that client's own oldest
``Pending`` deployment target, if any. Strictly read-only - no
``DeploymentTarget`` row is created, modified, or transitioned by this
method (see the method's own docstring for why no status transition
happens on poll). Composed alongside ``create_deployment`` in this same
service, per SAD Section 10.10 ("Deployment Service... coordinates
deployment operations") and this project's "one service per business
domain" principle (SAD Section 10.14) - polling is part of the same
Deployment business domain as creation, not a separate one.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import List, Optional, Tuple
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.exceptions import AppException
from backend.models.client import Client
from backend.models.deployment import Deployment
from backend.models.deployment_target import DeploymentTarget
from backend.models.enums import ApprovalStatus, AuditSeverity, DeploymentStatus
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.client_repository import ClientRepository
from backend.repositories.deployment_repository import DeploymentRepository
from backend.services.repository_service import RepositoryPackageNotFoundError, RepositoryService

logger = logging.getLogger(__name__)

# Per-client target states from which an installer download may still be
# requested (DEPLOY-003, FR-010). ``Pending`` covers the normal first
# download; ``Downloading`` covers a Client Agent retrying an interrupted
# download of the same target. Terminal states (``Completed``, ``Failed``,
# ``Cancelled``) and ``Installing`` (the download has already finished) are
# deliberately excluded - a request against one of those indicates the
# Client Agent is out of sync with the server's view of the deployment, not
# a legitimate retry.
DOWNLOADABLE_STATUSES: tuple[DeploymentStatus, ...] = (
    DeploymentStatus.PENDING,
    DeploymentStatus.DOWNLOADING,
)

# --------------------------------------------------------------------------
# DEPLOY-004 ADDITIONS - status reporting (FR-012) / cancellation (FR-021)
# --------------------------------------------------------------------------

# Terminal per-client statuses: once a ``DeploymentTarget`` reaches one of
# these, it must never be transitioned again (PRS FR-012 Deployment Status
# Values; this ticket's explicit "terminal states must not be casually
# overwritten" requirement - e.g. ``Completed`` -> ``Installing`` or
# ``Failed`` -> ``Downloading`` must never be accepted).
TERMINAL_DEPLOYMENT_STATUSES: tuple[DeploymentStatus, ...] = (
    DeploymentStatus.COMPLETED,
    DeploymentStatus.FAILED,
    DeploymentStatus.CANCELLED,
)

# The deployment lifecycle's legal forward transitions, keyed by the
# target's *current* status (PRS FR-012: Pending -> Downloading ->
# Installing -> Completed/Failed). ``Downloading`` and ``Installing`` may
# each also transition directly to ``Failed`` (e.g. a download or checksum
# failure occurring before installation ever begins - see
# ``agent.deployment.manager.ChecksumMismatchError``, which is reported as
# ``Failed`` without an intervening ``Installing`` report) - this is a
# deliberate, documented extension of the ticket's minimum "at least
# consider Pending -> Downloading, Downloading -> Installing, Installing ->
# Completed, Installing -> Failed" transition set, since the Client Agent
# genuinely can fail during the download/verification stage, before
# installation is ever attempted.
STATUS_TRANSITIONS: dict[DeploymentStatus, frozenset[DeploymentStatus]] = {
    DeploymentStatus.PENDING: frozenset({DeploymentStatus.DOWNLOADING, DeploymentStatus.FAILED}),
    DeploymentStatus.DOWNLOADING: frozenset({DeploymentStatus.INSTALLING, DeploymentStatus.FAILED}),
    DeploymentStatus.INSTALLING: frozenset({DeploymentStatus.COMPLETED, DeploymentStatus.FAILED}),
}


class DeploymentPackageUnavailableError(AppException):
    """
    Raised when a deployment is requested against a repository package
    that exists but is not currently ``Approved`` (FR-017: a deactivated
    ("removed") package must not be selectable for a new deployment).
    """

    def __init__(self, package_id: UUID) -> None:
        super().__init__(
            f"Repository package '{package_id}' is not Approved and cannot be deployed.",
            status_code=400,
        )


class DeploymentClientNotFoundError(AppException):
    """
    Raised when one or more requested target client ids do not match any
    registered ``Client`` (FR-008 Error Conditions: a deployment must
    target only registered client computers).
    """

    def __init__(self, client_ids: List[UUID]) -> None:
        formatted = ", ".join(str(client_id) for client_id in client_ids)
        super().__init__(
            f"The following target client id(s) were not found: {formatted}.",
            status_code=404,
        )


class DeploymentClientActiveError(AppException):
    """
    Raised when one or more requested target clients already have an
    active (non-terminal) deployment in progress (Business Rule 9, PRS
    Section 2.7: "A client may process only one deployment job at a
    time").
    """

    def __init__(self, client_ids: List[UUID]) -> None:
        formatted = ", ".join(str(client_id) for client_id in client_ids)
        super().__init__(
            f"The following client(s) already have an active deployment in progress: {formatted}.",
            status_code=409,
        )


class DeploymentTargetNotFoundError(AppException):
    """
    Raised when a requested deployment target id does not exist, or does
    not belong to the client requesting it (DEPLOY-003, FR-010).

    Deliberately raised identically for "does not exist at all" and
    "exists but belongs to a different client" - the two cases are
    indistinguishable to the requester by design (this ticket's "Client
    Isolation" requirement: a client must never learn anything about the
    existence of another client's deployment targets, not even via a
    different error message/status code).
    """

    def __init__(self, target_id: UUID) -> None:
        super().__init__(
            f"Deployment target '{target_id}' was not found for the authenticated client.",
            status_code=404,
        )


class DeploymentTargetNotDownloadableError(AppException):
    """
    Raised when a deployment target exists and belongs to the requesting
    client, but its current status is not one from which an installer
    download may be requested (see ``DOWNLOADABLE_STATUSES``).
    """

    def __init__(self, target_id: UUID, current_status: DeploymentStatus) -> None:
        super().__init__(
            f"Deployment target '{target_id}' is not available for download "
            f"(current status: {current_status.value}).",
            status_code=409,
        )


class DeploymentInstallerUnavailableError(AppException):
    """
    Raised when a deployment target's associated repository package
    record exists, but its installer file cannot be located on disk under
    the configured repository directory.

    This represents a server-side data-integrity problem (a
    ``RepositoryPackage`` row with no corresponding file), not a fault of
    the requesting Client Agent - reported as a 500 rather than a 404/409.
    """

    def __init__(self, package_id: UUID) -> None:
        super().__init__(
            f"Installer file for repository package '{package_id}' could not be located on the server.",
            status_code=500,
        )


class DeploymentStatusTransitionError(AppException):
    """
    Raised when a Client Agent's reported ``status`` is not a legal
    transition from a deployment target's current status (FR-012).

    Covers both "not a recognized forward transition" (e.g. ``Pending`` ->
    ``Installing``, skipping ``Downloading``) and "the target is already in
    a terminal state" (e.g. ``Completed`` -> ``Installing``, ``Failed`` ->
    ``Downloading``, ``Cancelled`` -> ``Installing``) - this ticket's
    explicit requirement that terminal states must not be casually
    overwritten.
    """

    def __init__(
        self, target_id: UUID, current_status: DeploymentStatus, requested_status: DeploymentStatus
    ) -> None:
        super().__init__(
            f"Deployment target '{target_id}' cannot transition from "
            f"'{current_status.value}' to '{requested_status.value}'.",
            status_code=409,
        )


class DeploymentStatusReportValidationError(AppException):
    """
    Raised when a status report is otherwise a legal transition but is
    missing information FR-012 requires for that particular outcome (e.g.
    reporting ``Failed`` with no ``error_message``).

    This duplicates part of what ``backend.schemas.deployment.
    DeploymentStatusReportRequest`` already validates at the schema layer;
    it is kept here as well since the Service Layer is this project's
    authoritative validation boundary and must not assume every caller
    goes through the schema layer (mirroring
    ``DeploymentService._validate_clients``'s existing "de-duplicated
    again defensively" rationale).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class DeploymentCancellationTargetNotFoundError(AppException):
    """
    Raised when an administrator attempts to cancel a deployment target
    id that does not exist (FR-021).

    Deliberately a distinct exception from ``DeploymentTargetNotFoundError``
    above: that one is raised for Client Agent-facing, client-scoped
    lookups (and is intentionally worded to be indistinguishable from "this
    target belongs to someone else"), whereas this one is raised for an
    administrator-facing, unscoped lookup, where no such ambiguity is
    necessary or desirable - an administrator is authorized to know a
    target id simply does not exist.
    """

    def __init__(self, target_id: UUID) -> None:
        super().__init__(f"Deployment target '{target_id}' was not found.", status_code=404)


class DeploymentCancellationNotAllowedError(AppException):
    """
    Raised when an administrator attempts to cancel a deployment target
    that is not currently ``Pending`` (FR-021: "Once a Client Agent has
    retrieved a deployment job through polling (FR-009), the job shall no
    longer be eligible for cancellation... If the job is no longer
    Pending, the server rejects the cancellation request").
    """

    def __init__(self, target_id: UUID, current_status: DeploymentStatus) -> None:
        super().__init__(
            f"Deployment target '{target_id}' is no longer Pending (current status: "
            f"{current_status.value}) and cannot be cancelled.",
            status_code=409,
        )


@dataclass(frozen=True)
class _ValidatedClients:
    """Internal helper bundling the resolved, order-preserving client list."""

    clients: List[Client]


class DeploymentService:
    """
    Deployment batch creation (FR-008, FR-009).

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase. ``RepositoryService`` is composed (not subclassed) so
    package lookup/validation logic is reused rather than duplicated -
    per this ticket's instruction to reuse existing repository/service
    methods where appropriate.
    """

    def __init__(
        self,
        deployment_repository: DeploymentRepository | None = None,
        client_repository: ClientRepository | None = None,
        repository_service: RepositoryService | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._deployments = deployment_repository or DeploymentRepository()
        self._clients = client_repository or ClientRepository()
        self._repository_service = repository_service or RepositoryService()
        self._audit_logs = audit_log_repository or AuditLogRepository()

    def _validate_package(self, db: Session, repository_package_id: UUID) -> None:
        """
        Ensure ``repository_package_id`` refers to an existing, currently
        ``Approved`` repository package.

        Reuses ``RepositoryService.get_package`` (REP-002) rather than
        duplicating package lookup logic; that method already raises
        ``RepositoryPackageNotFoundError`` (404) for an unknown id, which
        is allowed to propagate unchanged here.
        """
        package = self._repository_service.get_package(db, repository_package_id)
        if package.approval_status != ApprovalStatus.APPROVED:
            raise DeploymentPackageUnavailableError(repository_package_id)

    def _validate_clients(self, db: Session, client_ids: List[UUID]) -> _ValidatedClients:
        """
        Ensure every id in ``client_ids`` matches an existing, registered
        ``Client``.

        Duplicate ids are rejected by
        ``DeploymentCreateRequest.no_duplicate_clients`` before this
        service is ever called, but ``client_ids`` is de-duplicated again
        defensively (preserving request order) since the service layer is
        the authoritative validation boundary.

        Raises:
            ``DeploymentClientNotFoundError`` (404) - one or more ids do
            not match a registered client.
        """
        seen: set[UUID] = set()
        ordered_unique_ids: List[UUID] = []
        for client_id in client_ids:
            if client_id not in seen:
                seen.add(client_id)
                ordered_unique_ids.append(client_id)

        resolved: List[Client] = []
        missing: List[UUID] = []
        for client_id in ordered_unique_ids:
            client = self._clients.get_by_id(db, client_id)
            if client is None:
                missing.append(client_id)
            else:
                resolved.append(client)

        if missing:
            raise DeploymentClientNotFoundError(missing)

        return _ValidatedClients(clients=resolved)

    def _validate_no_active_deployments(self, db: Session, clients: List[Client]) -> None:
        """
        Ensure none of ``clients`` already has an active (non-terminal)
        deployment target (Business Rule 9, PRS Section 2.7).

        Raises:
            ``DeploymentClientActiveError`` (409) - one or more clients
            already have a Pending, Downloading, or Installing target.
        """
        client_ids = [client.id for client in clients]
        active_targets = self._deployments.get_active_targets_for_clients(db, client_ids)
        if active_targets:
            conflicting_ids = [target.client_id for target in active_targets]
            raise DeploymentClientActiveError(conflicting_ids)

    def create_deployment(
        self,
        db: Session,
        *,
        admin_id: UUID,
        repository_package_id: UUID,
        client_ids: List[UUID],
    ) -> Deployment:
        """
        Validate and create a new deployment batch targeting one or more
        registered clients (FR-008 functional behavior steps 1-9).

        Validation order (package -> clients exist -> clients not
        already active) runs entirely before any ``Deployment`` or
        ``DeploymentTarget`` row is created, so a request that will
        ultimately be rejected never leaves a partial batch behind - per
        this ticket's explicit "no partial deployments" requirement. No
        row created by this method is committed until every validation
        step has succeeded; the caller's FastAPI dependency
        (``backend.database.session.get_db``) discards any
        flushed-but-uncommitted work if an exception propagates out of
        this method, since it never calls ``db.commit()`` itself.

        Raises:
            ``RepositoryPackageNotFoundError`` (404) - no repository
            package exists with the given id.

            ``DeploymentPackageUnavailableError`` (400) - the repository
            package exists but is not currently ``Approved``.

            ``DeploymentClientNotFoundError`` (404) - one or more target
            client ids do not match a registered client.

            ``DeploymentClientActiveError`` (409) - one or more target
            clients already have an active deployment in progress.
        """
        self._validate_package(db, repository_package_id)

        validated = self._validate_clients(db, client_ids)
        self._validate_no_active_deployments(db, validated.clients)

        deployment = self._deployments.create_deployment(
            db,
            repository_id=repository_package_id,
            created_by_admin_id=admin_id,
        )

        for client in validated.clients:
            self._deployments.add_target(
                db,
                deployment_id=deployment.id,
                client_id=client.id,
                status=DeploymentStatus.PENDING,
            )

        self._audit_logs.create(
            db,
            event_type="DEPLOYMENT_CREATED",
            severity=AuditSeverity.INFO,
            description=(
                f"Deployment batch {deployment.id} created for repository package "
                f"{repository_package_id}, targeting {len(validated.clients)} client(s)."
            ),
            admin_id=admin_id,
        )
        db.commit()

        logger.info(
            "Deployment %s created by administrator %s (package=%s, targets=%d).",
            deployment.id,
            admin_id,
            repository_package_id,
            len(validated.clients),
        )
        return deployment

    def poll_pending_deployment(self, db: Session, *, client: Client) -> DeploymentTarget | None:
        """
        Resolve ``client``'s own oldest ``Pending`` deployment target, if
        any (FR-009 Deployment Job Retrieval).

        ``client`` MUST be the ``Client`` already authenticated by
        ``require_client_api_key`` (AUTH-002) - see
        ``backend/api/routers/agent.py``'s ``poll_deployment`` handler,
        which passes ``current_client`` (never a client id read from
        request input). The lookup is delegated to
        ``DeploymentRepository.get_pending_target_for_client``, which
        filters strictly on ``client.id`` at the database layer - this is
        what guarantees a client can never retrieve another client's
        deployment (this ticket's "Client Isolation" requirement), since
        there is no code path here that accepts an arbitrary client id.

        --------------------------------------------------------------------
        DESIGN NOTE - no status transition on poll, no audit log entry

        FR-009's own functional behavior (steps 1-6) describes searching
        for and returning a pending deployment; it does not describe a
        status change. FR-012's Deployment Status Values table ties the
        ``Pending`` -> ``Downloading`` transition to the Client Agent
        *beginning the installer download* (FR-010) and *reporting* that
        transition (FR-012 step 1, "Upon beginning the installer download
        (FR-010), the Client Agent reports a Downloading status update") -
        both of which are DEPLOY-003/DEPLOY-004 scope, explicitly excluded
        from this ticket ("DEPLOY-002 IS POLLING ONLY... DO NOT
        IMPLEMENT... Installation status reporting"). Mutating
        ``DeploymentTarget.status`` here would therefore be performing
        DEPLOY-004's work prematurely and would let a client claim a
        target without ever actually downloading it. This method is
        consequently a pure read: no ``db.add``/``db.flush``/``db.commit``
        occurs, and the caller's request-scoped session is simply closed
        (uncommitted, and unmodified) once the response is returned.

        For the same reason, and mirroring
        ``HeartbeatService.record_heartbeat``'s documented rationale
        (routine, frequent, non-security-relevant traffic), a poll is not
        written to the audit log - only this module's application logger
        records it, consistent with FR-009's own "polling activity *may*
        be recorded" (not "shall be recorded in the audit log", unlike the
        FR-016 audit-logged-events list, which does not mention polling).
        --------------------------------------------------------------------
        """
        target = self._deployments.get_pending_target_for_client(db, client.id)
        if target is None:
            logger.debug("Client %s polled for a deployment; none pending.", client.id)
        else:
            logger.info(
                "Client %s polled for a deployment; returning target %s (deployment=%s).",
                client.id,
                target.id,
                target.deployment_id,
            )
        return target

    def prepare_installer_download(
        self,
        db: Session,
        *,
        client: Client,
        target_id: UUID,
        repository_dir: Path,
    ) -> Tuple[DeploymentTarget, Path]:
        """
        Resolve and authorize a Client Agent's request to download the
        installer for one of its own deployment targets (DEPLOY-003,
        FR-010 Installer Download).

        ``client`` MUST be the ``Client`` already authenticated by
        ``require_client_api_key`` (AUTH-002) - see
        ``backend/api/routers/agent.py``'s ``download_installer`` handler,
        which passes ``current_client`` (never a client id read from
        request input). Resolution is delegated to
        ``DeploymentRepository.get_target_for_client``, which filters
        strictly on ``client.id`` at the database layer, mirroring
        ``poll_pending_deployment``'s existing client-isolation approach
        (DEPLOY-002) - this is what guarantees a client can never download
        another client's installer, even by guessing/enumerating target
        ids (this ticket's "Client Isolation" requirement).

        Validation order:

            1. The target must exist and belong to ``client``
               (``DeploymentTargetNotFoundError``, 404 - identical for
               "does not exist" and "belongs to someone else", per that
               exception's own docstring).
            2. The target's status must be one from which a download may
               be requested (``DOWNLOADABLE_STATUSES`` -
               ``DeploymentTargetNotDownloadableError``, 409).
            3. The associated repository package's installer file must
               actually be present on disk under ``repository_dir``
               (``DeploymentInstallerUnavailableError``, 500).

        Every successful and rejected-for-isolation-reasons attempt is
        recorded in the audit log (PRS FR-016 Logged Events explicitly
        lists "Installer Downloads"), each followed by ``db.commit()`` so
        the entry is actually persisted before this read-only endpoint
        returns its (non-JSON, streamed) response.

        Returns the resolved ``DeploymentTarget`` and the absolute
        filesystem ``Path`` to its installer file - the caller (the
        FastAPI router) is responsible for actually streaming that file
        back to the client (e.g. via ``fastapi.responses.FileResponse``);
        this service performs no I/O beyond the existence check.

        Raises:
            ``DeploymentTargetNotFoundError`` (404) - no target with
            ``target_id`` exists for this client.

            ``DeploymentTargetNotDownloadableError`` (409) - the target
            exists but is not currently downloadable (e.g. already
            ``Completed``/``Failed``/``Cancelled``, or still
            ``Installing``).

            ``DeploymentInstallerUnavailableError`` (500) - the target's
            repository package has no corresponding installer file on
            disk.
        """
        target = self._deployments.get_target_for_client(db, target_id=target_id, client_id=client.id)
        if target is None:
            self._audit_logs.create(
                db,
                event_type="INSTALLER_DOWNLOAD_REJECTED",
                severity=AuditSeverity.WARNING,
                description=(
                    f"Client {client.id} requested installer download for deployment target "
                    f"'{target_id}', which does not exist or does not belong to this client."
                ),
                client_id=client.id,
            )
            db.commit()
            logger.warning(
                "Client %s requested installer download for unknown/foreign deployment target %s.",
                client.id,
                target_id,
            )
            raise DeploymentTargetNotFoundError(target_id)

        if target.status not in DOWNLOADABLE_STATUSES:
            logger.info(
                "Client %s requested installer download for target %s, but its status is %s "
                "(not currently downloadable).",
                client.id,
                target.id,
                target.status.value,
            )
            raise DeploymentTargetNotDownloadableError(target_id, target.status)

        package = target.deployment.repository_package
        installer_path = repository_dir / package.installer_filename

        if not installer_path.is_file():
            self._audit_logs.create(
                db,
                event_type="INSTALLER_FILE_MISSING",
                severity=AuditSeverity.ERROR,
                description=(
                    f"Installer file '{package.installer_filename}' for repository package "
                    f"{package.id} (deployment target {target.id}, client {client.id}) is missing "
                    f"from the repository directory."
                ),
                client_id=client.id,
            )
            db.commit()
            logger.error(
                "Installer file %s for package %s missing on disk (target=%s, client=%s).",
                installer_path,
                package.id,
                target.id,
                client.id,
            )
            raise DeploymentInstallerUnavailableError(package.id)

        self._audit_logs.create(
            db,
            event_type="INSTALLER_DOWNLOAD",
            severity=AuditSeverity.INFO,
            description=(
                f"Client {client.id} downloaded installer for deployment target {target.id} "
                f"(deployment={target.deployment_id}, package={package.id} "
                f"'{package.software_name}' v'{package.version}')."
            ),
            client_id=client.id,
        )
        db.commit()

        logger.info(
            "Client %s downloading installer for target %s (package=%s, file=%s).",
            client.id,
            target.id,
            package.id,
            package.installer_filename,
        )
        return target, installer_path

    def report_status(
        self,
        db: Session,
        *,
        client: Client,
        target_id: UUID,
        status: DeploymentStatus,
        exit_code: Optional[int] = None,
        error_message: Optional[str] = None,
    ) -> DeploymentTarget:
        """
        Record a Client Agent-reported status transition for one of its
        own deployment targets (DEPLOY-004, FR-012 Deployment Status
        Reporting).

        ``client`` MUST be the ``Client`` already authenticated by
        ``require_client_api_key`` (AUTH-002) - see
        ``backend/api/routers/agent.py``'s ``report_deployment_status``
        handler, which passes ``current_client`` (never a client id read
        from request input). Resolution is delegated to
        ``DeploymentRepository.get_target_for_client``, the exact same
        client-scoped lookup already used by
        ``prepare_installer_download`` (DEPLOY-003) and
        ``poll_pending_deployment`` (DEPLOY-002) - this is what guarantees
        a client can never report status for, and therefore never mutate,
        another client's deployment target (this ticket's "Client
        Isolation" requirement).

        --------------------------------------------------------------------
        DESIGN NOTE - idempotent re-reporting

        If ``status`` already equals the target's current status, this is
        treated as a harmless, idempotent no-op (the target is returned
        unchanged, without a new audit log entry) rather than an invalid
        transition. This supports the PRS's client communication retry
        requirement (NFR-004 / FR-012 Error Conditions: "If reporting
        fails, the Client Agent shall retain the report and retry
        transmission during the next communication cycle") - if the
        server successfully processed a report but the Client Agent never
        saw the HTTP response (e.g. the connection dropped after the
        server committed), the Agent's retry of the *same* report must
        not be rejected as "already in a terminal state."
        --------------------------------------------------------------------

        Validation order:

            1. The target must exist and belong to ``client``
               (``DeploymentTargetNotFoundError``, 404 - reused unchanged
               from DEPLOY-003, identical for "does not exist" and
               "belongs to someone else").
            2. If ``status`` differs from the target's current status,
               that current status must not already be terminal
               (``DeploymentStatusTransitionError``, 409) and the
               requested ``status`` must be a legal forward transition
               from it, per ``STATUS_TRANSITIONS``
               (``DeploymentStatusTransitionError``, 409).
            3. Reporting ``Failed`` without a non-blank ``error_message``
               is rejected (``DeploymentStatusReportValidationError``,
               400) - defensive re-validation of what
               ``DeploymentStatusReportRequest`` already enforces at the
               schema layer.

        ``completion_time`` is set to the current server time (never a
        client-supplied value - this ticket's explicit "prefer
        server-side timestamps for persistent deployment completion
        records" instruction) when, and only when, ``status`` is
        ``Completed`` or ``Failed``. Reporting ``Downloading`` or
        ``Installing`` updates only ``status`` - the intermediate
        transitions carry no ``exit_code``/``error_message``/
        ``completion_time`` semantics of their own.

        Only the two terminal outcomes are audit-logged
        (``DEPLOYMENT_COMPLETED`` / ``DEPLOYMENT_FAILED``) - PRS FR-016's
        Logged Events list explicitly names "Deployment Results", but does
        not call out intermediate progress updates the way it does for
        e.g. "Installer Downloads"; ``Downloading``/``Installing``
        transitions are instead only recorded via this module's
        application logger, mirroring ``poll_pending_deployment``'s
        already-documented "routine, frequent, non-security-relevant
        traffic" rationale for what does and does not warrant an audit
        log entry.

        Raises:
            ``DeploymentTargetNotFoundError`` (404) - no target with
            ``target_id`` exists for this client.

            ``DeploymentStatusTransitionError`` (409) - the target is
            already in a terminal state, or ``status`` is not a legal
            transition from its current status.

            ``DeploymentStatusReportValidationError`` (400) - ``status``
            is ``Failed`` but ``error_message`` is missing/blank.
        """
        target = self._deployments.get_target_for_client(db, target_id=target_id, client_id=client.id)
        if target is None:
            logger.warning(
                "Client %s reported status for unknown/foreign deployment target %s.",
                client.id,
                target_id,
            )
            raise DeploymentTargetNotFoundError(target_id)

        if status == target.status:
            logger.info(
                "Client %s re-reported status '%s' for target %s (idempotent no-op).",
                client.id,
                status.value,
                target.id,
            )
            return target

        current_status = target.status
        if current_status in TERMINAL_DEPLOYMENT_STATUSES:
            raise DeploymentStatusTransitionError(target_id, current_status, status)

        allowed_next_statuses = STATUS_TRANSITIONS.get(current_status, frozenset())
        if status not in allowed_next_statuses:
            raise DeploymentStatusTransitionError(target_id, current_status, status)

        if status == DeploymentStatus.FAILED and not (error_message and error_message.strip()):
            raise DeploymentStatusReportValidationError(
                "error_message is required when reporting status 'Failed'."
            )

        completion_time: Optional[datetime] = None
        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            completion_time = datetime.now(timezone.utc)

        updated = self._deployments.update_status(
            db,
            target,
            status=status,
            exit_code=exit_code,
            error_message=error_message,
            completion_time=completion_time,
        )

        if status in (DeploymentStatus.COMPLETED, DeploymentStatus.FAILED):
            self._audit_logs.create(
                db,
                event_type="DEPLOYMENT_COMPLETED" if status == DeploymentStatus.COMPLETED else "DEPLOYMENT_FAILED",
                severity=AuditSeverity.INFO if status == DeploymentStatus.COMPLETED else AuditSeverity.WARNING,
                description=(
                    f"Deployment target {updated.id} (deployment={updated.deployment_id}, "
                    f"client={client.id}) reported final status '{status.value}'"
                    f"{f' (exit_code={exit_code})' if exit_code is not None else ''}."
                ),
                client_id=client.id,
            )
            db.commit()
        else:
            db.commit()

        logger.info(
            "Client %s reported status '%s' -> '%s' for target %s (deployment=%s).",
            client.id,
            current_status.value,
            status.value,
            updated.id,
            updated.deployment_id,
        )
        return updated

    def cancel_deployment_target(
        self,
        db: Session,
        *,
        admin_id: UUID,
        target_id: UUID,
    ) -> DeploymentTarget:
        """
        Cancel a still-``Pending`` deployment target (DEPLOY-004, FR-021
        Deployment Cancellation).

        Unlike ``report_status``/``prepare_installer_download``, this
        operation is administrator-authorized (``CurrentAdministrator``,
        the caller in ``backend/api/routers/deployments.py``), not
        client-authenticated - resolution therefore uses
        ``DeploymentRepository.get_target_by_id`` (no client-ownership
        filter), not ``get_target_for_client``.

        Per FR-021's functional behavior, only a target still in
        ``Pending`` status may be cancelled: "Once a Client Agent has
        retrieved a deployment job through polling (FR-009), the job
        shall no longer be eligible for cancellation through this
        function, since the client may already be downloading or
        installing the software." This project's ``DeploymentTarget.
        status`` field is the sole source of truth for that check (poll
        itself never mutates status - see ``poll_pending_deployment``'s
        design note - so "still Pending" here means exactly what FR-021
        describes: no status-changing action has happened yet).

        Raises:
            ``DeploymentCancellationTargetNotFoundError`` (404) - no
            target exists with ``target_id``.

            ``DeploymentCancellationNotAllowedError`` (409) - the target
            exists but is not currently ``Pending``.
        """
        target = self._deployments.get_target_by_id(db, target_id)
        if target is None:
            raise DeploymentCancellationTargetNotFoundError(target_id)

        if target.status != DeploymentStatus.PENDING:
            raise DeploymentCancellationNotAllowedError(target_id, target.status)

        updated = self._deployments.update_status(db, target, status=DeploymentStatus.CANCELLED)

        self._audit_logs.create(
            db,
            event_type="DEPLOYMENT_CANCELLED",
            severity=AuditSeverity.INFO,
            description=(
                f"Deployment target {updated.id} (deployment={updated.deployment_id}, "
                f"client={updated.client_id}) cancelled by administrator {admin_id}."
            ),
            admin_id=admin_id,
        )
        db.commit()

        logger.info("Administrator %s cancelled deployment target %s.", admin_id, updated.id)
        return updated


__all__ = [
    "DeploymentService",
    "DeploymentPackageUnavailableError",
    "DeploymentClientNotFoundError",
    "DeploymentClientActiveError",
    "DeploymentTargetNotFoundError",
    "DeploymentTargetNotDownloadableError",
    "DeploymentInstallerUnavailableError",
    "DeploymentStatusTransitionError",
    "DeploymentStatusReportValidationError",
    "DeploymentCancellationTargetNotFoundError",
    "DeploymentCancellationNotAllowedError",
    "RepositoryPackageNotFoundError",
]