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
from typing import List
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


__all__ = [
    "DeploymentService",
    "DeploymentPackageUnavailableError",
    "DeploymentClientNotFoundError",
    "DeploymentClientActiveError",
    "RepositoryPackageNotFoundError",
]
