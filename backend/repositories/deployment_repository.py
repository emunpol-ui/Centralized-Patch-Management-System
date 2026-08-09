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
