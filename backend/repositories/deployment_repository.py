"""
Deployment repository.

Pure data-access layer for the ``Deployment`` and ``DeploymentTarget``
entities, per the Repository Pattern (SAD Section 5.4, Section 11).
Introduced by DEPLOY-001 (Backlog "Deployment creation API" / "Job
persistence" deliverables, FR-008 Deployment Job Creation, FR-009
Deployment Job Retrieval targeting).

Both tables were already defined by CORE-002
(``backend/models/deployment.py``, ``backend/models/deployment_target.py``)
but, per the same deferral pattern already used for
``RepositoryPackageRepository`` (see the note in
``backend/repositories/__init__.py``), no repository consumed them until
this ticket.

Contains only data-access operations - no business rules. In particular,
the "a client shall process only one active deployment at a time"
business rule (Business Rule 9, PRS Section 2.7) is enforced by
``backend.services.deployment_service.DeploymentService``, not here; this
repository only exposes the query
(``get_active_target_for_client``) that the service needs to evaluate
that rule, consistent with the design note already documented on
``DeploymentTarget`` ("that is a *business* rule, enforced by the Service
Layer in DEPLOY-001... at the data layer it is supported by the
``ix_deployment_targets_client_status`` index").
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Iterable, List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.deployment import Deployment
from backend.models.deployment_target import DeploymentTarget
from backend.models.enums import DeploymentStatus

# Per-client deployment states that are not yet terminal (PRS FR-012
# Deployment Status Values: Completed, Failed, and Cancelled are terminal;
# Pending, Downloading, and Installing are not). A client with any target
# in one of these states is still "processing" a deployment and, per
# Business Rule 9 (PRS Section 2.7), must not be assigned a second one.
ACTIVE_DEPLOYMENT_STATUSES: tuple[DeploymentStatus, ...] = (
    DeploymentStatus.PENDING,
    DeploymentStatus.DOWNLOADING,
    DeploymentStatus.INSTALLING,
)


class DeploymentRepository:
    """Data-access operations for the ``deployments`` and ``deployment_targets`` tables."""

    def create_deployment(
        self,
        db: Session,
        *,
        repository_id: uuid.UUID,
        created_by_admin_id: uuid.UUID,
    ) -> Deployment:
        """
        Persist a new ``Deployment`` (batch) record and flush it (FR-008
        functional behavior: "The server generates a Batch ID for the
        request... Deployment information is stored in the database").
        """
        deployment = Deployment(
            repository_id=repository_id,
            created_by_admin_id=created_by_admin_id,
        )
        db.add(deployment)
        db.flush()
        return deployment

    def add_target(
        self,
        db: Session,
        *,
        deployment_id: uuid.UUID,
        client_id: uuid.UUID,
        status: DeploymentStatus = DeploymentStatus.PENDING,
    ) -> DeploymentTarget:
        """
        Persist a new ``DeploymentTarget`` row for one client within a
        deployment batch and flush it (FR-008 functional behavior: "For
        each remaining targeted client, the server creates an individual
        deployment job record associated with the Batch ID... Each new
        deployment job's status is initialized as Pending").
        """
        target = DeploymentTarget(
            deployment_id=deployment_id,
            client_id=client_id,
            status=status,
        )
        db.add(target)
        db.flush()
        return target

    def get_active_target_for_client(
        self, db: Session, client_id: uuid.UUID
    ) -> Optional[DeploymentTarget]:
        """
        Return an existing ``DeploymentTarget`` for ``client_id`` whose
        status is not yet terminal (Pending, Downloading, or Installing),
        or ``None`` if the client has no active deployment.

        Used by ``DeploymentService`` to enforce Business Rule 9 (PRS
        Section 2.7: "A client may process only one deployment job at a
        time") before creating a new target for that client. Uses the
        ``ix_deployment_targets_client_status`` composite index defined
        on ``DeploymentTarget`` for an efficient lookup.
        """
        stmt = (
            select(DeploymentTarget)
            .where(DeploymentTarget.client_id == client_id)
            .where(DeploymentTarget.status.in_(ACTIVE_DEPLOYMENT_STATUSES))
            .limit(1)
        )
        return db.execute(stmt).scalars().first()

    def get_active_targets_for_clients(
        self, db: Session, client_ids: Iterable[uuid.UUID]
    ) -> List[DeploymentTarget]:
        """
        Return every existing ``DeploymentTarget`` whose ``client_id`` is
        in ``client_ids`` and whose status is not yet terminal.

        A single batched lookup (rather than one query per client) used
        by ``DeploymentService`` to validate an entire multi-client
        deployment request in one round trip before creating anything.
        """
        client_id_list = list(client_ids)
        if not client_id_list:
            return []
        stmt = (
            select(DeploymentTarget)
            .where(DeploymentTarget.client_id.in_(client_id_list))
            .where(DeploymentTarget.status.in_(ACTIVE_DEPLOYMENT_STATUSES))
        )
        return list(db.execute(stmt).scalars().all())

    def get_by_id(self, db: Session, deployment_id: uuid.UUID) -> Optional[Deployment]:
        """Return the ``Deployment`` with the given primary key, or ``None``."""
        return db.get(Deployment, deployment_id)

    def get_pending_target_for_client(
        self, db: Session, client_id: uuid.UUID
    ) -> Optional[DeploymentTarget]:
        """
        Return ``client_id``'s oldest ``Pending`` ``DeploymentTarget``, or
        ``None`` if it has none.

        Introduced by DEPLOY-002 (FR-009 Deployment Job Retrieval / Client
        Polling). The query is strictly scoped to ``client_id`` - the
        caller (``DeploymentService.poll_pending_deployment``) MUST always
        pass the identity resolved from the authenticated API key
        (``CurrentClient.id``), never a client id taken from request
        input, so that a client can never retrieve another client's
        deployment (this ticket's "Client Isolation" requirement).

        Only ``Pending`` targets are matched - not the full
        ``ACTIVE_DEPLOYMENT_STATUSES`` set used by
        ``get_active_target_for_client``/``get_active_targets_for_clients``
        for the DEPLOY-001 "one active deployment per client" check.
        ``Downloading`` and ``Installing`` represent a deployment the
        client has already claimed and moved past the "not yet retrieved"
        state FR-009 describes; polling again while in one of those states
        is not this ticket's concern (see FR-012/FR-010, DEPLOY-003 and
        DEPLOY-004 scope).

        Business Rule 9 (PRS Section 2.7, enforced by
        ``DeploymentService.create_deployment`` since DEPLOY-001) already
        guarantees a client has at most one non-terminal target at a time,
        so ``.limit(1)`` here is a defensive safeguard rather than a
        behavior-changing choice; ``created_at`` ascending simply makes
        the result deterministic if that invariant were ever violated.
        """
        stmt = (
            select(DeploymentTarget)
            .where(DeploymentTarget.client_id == client_id)
            .where(DeploymentTarget.status == DeploymentStatus.PENDING)
            .order_by(DeploymentTarget.created_at.asc())
            .limit(1)
        )
        return db.execute(stmt).scalars().first()

    def get_target_for_client(
        self, db: Session, *, target_id: uuid.UUID, client_id: uuid.UUID
    ) -> Optional[DeploymentTarget]:
        """
        Return the ``DeploymentTarget`` identified by ``target_id`` only if
        it belongs to ``client_id``, or ``None`` otherwise - including when
        ``target_id`` does not exist at all.

        Introduced by DEPLOY-003 (FR-010 Installer Download). The
        ``client_id`` filter is applied inside the SQL ``WHERE`` clause
        itself, mirroring ``get_pending_target_for_client`` (DEPLOY-002),
        so a client can never resolve - and therefore never download the
        installer for - another client's deployment target, even by
        guessing/enumerating target ids. The caller (``DeploymentService.
        prepare_installer_download``) MUST always pass the identity
        resolved from the authenticated API key (``CurrentClient.id``),
        never a client id taken from request input (this ticket's "Client
        Isolation" requirement).

        Unlike ``get_pending_target_for_client``, this lookup is not
        restricted to ``Pending`` status - a target already in
        ``Downloading`` (e.g. a client retrying an interrupted download)
        must still resolve here; the decision about *which* statuses are
        actually downloadable is a business rule and belongs to
        ``DeploymentService``, not this repository.
        """
        stmt = (
            select(DeploymentTarget)
            .where(DeploymentTarget.id == target_id)
            .where(DeploymentTarget.client_id == client_id)
        )
        return db.execute(stmt).scalars().first()

    def get_target_by_id(self, db: Session, target_id: uuid.UUID) -> Optional[DeploymentTarget]:
        """
        Return the ``DeploymentTarget`` with the given primary key, or
        ``None`` - with no client-scoping filter applied.

        Introduced by DEPLOY-004 for the administrator-facing cancellation
        endpoint (FR-021), which is authorized by administrator session
        (``CurrentAdministrator``), not by client identity - unlike
        ``get_target_for_client`` (DEPLOY-003), which deliberately DOES
        filter on ``client_id`` for Client Agent-facing operations. This
        method must never be used to satisfy a Client Agent-facing
        request, since it performs no client-ownership check at all.
        """
        return db.get(DeploymentTarget, target_id)

    def update_status(
        self,
        db: Session,
        target: DeploymentTarget,
        *,
        status: DeploymentStatus,
        exit_code: Optional[int] = None,
        error_message: Optional[str] = None,
        completion_time: Optional[datetime] = None,
    ) -> DeploymentTarget:
        """
        Mutate an already-resolved ``DeploymentTarget`` in place and flush
        the change.

        Introduced by DEPLOY-004 (FR-012 Deployment Status Reporting,
        FR-021 Deployment Cancellation). Pure data mutation only - which
        status transitions are legal, whether ``error_message`` is
        required, and when ``completion_time`` should be set are business
        rules decided by ``backend.services.deployment_service.
        DeploymentService`` before this method is ever called; this
        repository does not second-guess the caller's decision.

        ``exit_code``/``error_message``/``completion_time`` are only
        written when explicitly provided (not ``None``) so that an
        intermediate progress update (e.g. reporting ``Downloading`` or
        ``Installing``, neither of which carries a completion time) does
        not inadvertently clear a value that has not actually changed.
        """
        target.status = status
        if exit_code is not None:
            target.exit_code = exit_code
        if error_message is not None:
            target.error_message = error_message
        if completion_time is not None:
            target.completion_time = completion_time
        db.add(target)
        db.flush()
        return target