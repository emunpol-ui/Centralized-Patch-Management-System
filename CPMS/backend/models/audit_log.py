"""
AuditLog ORM model.

Records significant administrative and client-generated system events
(PRS Section 7.5.6 / FR-016 System Logging and Audit Trail; ``admin_id``
added per PRS v1.2 finding AF-02).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import DateTime, ForeignKey, Index, String, Text, Uuid, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import BaseModel
from backend.models.enums import AuditSeverity

if TYPE_CHECKING:
    from backend.models.administrator import Administrator
    from backend.models.client import Client


class AuditLog(BaseModel):
    """
    A single, immutable audit trail entry.

    Inherits directly from ``BaseModel`` (id only) rather than
    ``AuditModel``: audit log entries are written once and never updated,
    so an ``updated_at`` column would be meaningless. ``timestamp``
    captures the moment of the audited event, per PRS Section 7.5.6.

    ``client_id`` and ``admin_id`` are both optional, independent
    (non-mutually-exclusive) references identifying which actor, if any,
    triggered the event - matching the SAD's "Related client (optional)" /
    "Related administrator (optional)" relationship definitions (Section
    7.6). Both use ``ondelete="SET NULL"`` so that removing a client or
    administrator later never destroys historical audit entries; only the
    reference is cleared, and ``description`` retains the human-readable
    record of what happened.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        Index("ix_audit_logs_timestamp", "timestamp"),
        Index("ix_audit_logs_event_type", "event_type"),
    )

    timestamp: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(100), nullable=False)
    severity: Mapped[AuditSeverity] = mapped_column(
        SAEnum(AuditSeverity, name="audit_severity", native_enum=False, validate_strings=True),
        nullable=False,
        default=AuditSeverity.INFO,
    )
    client_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("clients.id", ondelete="SET NULL"), nullable=True
    )
    admin_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("administrators.id", ondelete="SET NULL"), nullable=True
    )
    description: Mapped[str] = mapped_column(Text, nullable=False)

    # --- Relationships -------------------------------------------------------
    client: Mapped[Optional["Client"]] = relationship(back_populates="audit_logs")
    administrator: Mapped[Optional["Administrator"]] = relationship(back_populates="audit_logs")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<AuditLog id={self.id} event_type={self.event_type!r} severity={self.severity}>"
