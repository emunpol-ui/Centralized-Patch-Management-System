"""
Deployment ORM model.

Represents a single administrator deployment *request* - selecting one
approved software package and one or more target clients in a single
action (PRS FR-008 Deployment Job Creation).

--------------------------------------------------------------------------
DESIGN NOTE - reconciling the PRS and the SAD

This is flagged explicitly per the project's standing instruction to
identify documentation conflicts and explain them rather than silently
inventing a design:

* The PRS (Section 4.3 FR-008; Appendix D) models this area as a single
  "Deployment Jobs" table with ONE ROW PER TARGETED CLIENT, all rows
  sharing a ``batch_id`` to represent one administrator action, plus a
  separate one-to-one "Deployment Results" table holding completion
  details (exit code, error message, completion time).

* The SAD (Sections 8.4 and 17) instead describes TWO entities:
  "Deployment" (the job definition - target application/version, creation
  date, status, initiating administrator; "may target one or multiple
  client computers") and "Deployment Target" (per-client execution status
  and result), with no separate "Deployment Results" table.

* CPM-002's deliverable list explicitly asks for a ``Deployment`` model
  AND a ``DeploymentTarget`` model (matching the SAD's split) and does
  NOT list a ``DeploymentResult`` model. This implementation therefore
  follows the SAD's two-entity structure:

      - ``Deployment`` (this class) = the batch-level request. Its ``id``
        serves the same grouping purpose as the PRS's ``batch_id``.
      - ``DeploymentTarget`` = one row per targeted client, merging the
        PRS's per-client "Deployment Jobs" row and its corresponding
        "Deployment Results" row (status, completion_time, exit_code,
        error_message) into a single entity - matching what the SAD
        describes "Deployment Target" as storing.

  ``Deployment`` intentionally has NO status column of its own: per-client
  progress lives entirely on ``DeploymentTarget.status`` (FR-012's status
  values: Pending / Downloading / Installing / Completed / Failed /
  Cancelled). An aggregate "batch status" view, if the dashboard ever
  needs one, should be computed by the Service Layer (a later ticket)
  rather than stored redundantly here.

* The PRS (Appendix D) documents ``created_by`` as a plain TEXT column.
  This implementation instead uses a foreign key to ``Administrator``
  (``created_by_admin_id``), since CPM-002 explicitly requires "proper
  relationships" and "constraints where appropriate." This is a
  deliberate, documented deviation from the PRS's literal column type in
  favor of referential integrity.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import uuid
from typing import TYPE_CHECKING, List

from sqlalchemy import ForeignKey, Uuid
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import AuditModel

if TYPE_CHECKING:
    from backend.models.administrator import Administrator
    from backend.models.deployment_target import DeploymentTarget
    from backend.models.repository_package import RepositoryPackage


class Deployment(AuditModel):
    """
    A single deployment request created by an administrator (FR-008).

    ``created_at`` (inherited from ``AuditModel``) represents the
    deployment creation timestamp documented in the PRS as
    ``created_date``.

    ``repository_id`` uses ``ondelete="RESTRICT"``: the expected way to
    retire a package (FR-017) is to set its ``approval_status`` to
    ``INACTIVE`` (see ``backend/models/repository_package.py``), not to
    delete the row, so this restriction is a safety net that also
    guarantees deployment history always resolves to a real package.
    ``created_by_admin_id`` is likewise ``RESTRICT`` to protect the
    deployment audit trail.
    """

    __tablename__ = "deployments"

    repository_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("repository_packages.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    created_by_admin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("administrators.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )

    # --- Relationships -------------------------------------------------------
    repository_package: Mapped["RepositoryPackage"] = relationship(back_populates="deployments")
    created_by_admin: Mapped["Administrator"] = relationship(back_populates="deployments")
    targets: Mapped[List["DeploymentTarget"]] = relationship(
        back_populates="deployment",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Deployment id={self.id} repository_id={self.repository_id}>"
