"""
DeploymentTarget ORM model.

Represents the execution status of a single deployment for a single
targeted client. See the design note at the top of
``backend/models/deployment.py`` for how this reconciles the PRS's
per-client "Deployment Jobs" + "Deployment Results" tables with the SAD's
"Deployment Target" entity.

Covers the data underlying FR-009 through FR-013 and FR-021 (job
retrieval, installer download/execution acknowledgement, status
reporting, deployment history, and cancellation); the corresponding
workflow logic belongs to the Service Layer implemented in the DEPLOY-*
tickets, not this one.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, Integer, Text, UniqueConstraint, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import AuditModel
from backend.models.enums import DeploymentStatus

if TYPE_CHECKING:
    from backend.models.client import Client
    from backend.models.deployment import Deployment


class DeploymentTarget(AuditModel):
    """
    One targeted client's progress within a ``Deployment`` batch.

    A client shall process only one active deployment at a time (Business
    Rule 9, PRS Section 2.7). That is a *business* rule, enforced by the
    Service Layer in DEPLOY-001 (out of scope for this ticket - "keep
    business logic out of the models"); at the data layer it is supported
    by the ``ix_deployment_targets_client_status`` index below, which the
    service layer will use to efficiently check for an existing active job
    before creating a new one.

    ``client_id`` uses ``ondelete="RESTRICT"`` (not ``CASCADE``): per
    NFR-024, historical deployment records must not be lost, so a client
    with deployment history cannot be hard-deleted. ``deployment_id`` uses
    ``CASCADE`` because a target row has no independent meaning once its
    parent batch is removed.
    """

    __tablename__ = "deployment_targets"
    __table_args__ = (
        UniqueConstraint("deployment_id", "client_id", name="uq_deployment_target_deployment_client"),
        Index("ix_deployment_targets_client_status", "client_id", "status"),
    )

    deployment_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("deployments.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    client_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        ForeignKey("clients.id", ondelete="RESTRICT"),
        nullable=False,
        index=True,
    )
    status: Mapped[DeploymentStatus] = mapped_column(
        SAEnum(DeploymentStatus, name="deployment_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=DeploymentStatus.PENDING,
    )
    completion_time: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    exit_code: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # --- Relationships -------------------------------------------------------
    deployment: Mapped["Deployment"] = relationship(back_populates="targets")
    client: Mapped["Client"] = relationship(back_populates="deployment_targets")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<DeploymentTarget id={self.id} client_id={self.client_id} status={self.status}>"
