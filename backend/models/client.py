"""
Client ORM model.

Represents a registered Windows computer running the CPMS Client Agent
(PRS Section 7.5.1 / FR-001 Client Registration).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, Index, String, Uuid
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import AuditModel
from backend.models.enums import ClientStatus

if TYPE_CHECKING:
    from backend.models.audit_log import AuditLog
    from backend.models.deployment_target import DeploymentTarget
    from backend.models.software_inventory import SoftwareInventory


class Client(AuditModel):
    """
    A managed Windows endpoint.

    ``agent_guid`` is the persistent identifier generated locally by the
    Client Agent on first run (distinct from ``id``, the server-assigned
    surrogate primary key) - it is the field the server matches on during
    re-registration (FR-001), never hostname or IP address, since those
    may be duplicated (cloned images) or reassigned (DHCP).

    ``created_at`` (inherited from ``AuditModel``) represents the initial
    registration timestamp documented in the PRS as ``registration_date``.
    """

    __tablename__ = "clients"
    __table_args__ = (
        Index("ix_clients_hostname", "hostname"),
        Index("ix_clients_status", "status"),
    )

    agent_guid: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), unique=True, nullable=False)
    api_key_hash: Mapped[str] = mapped_column(String(255), unique=True, nullable=False)
    hostname: Mapped[str] = mapped_column(String(255), nullable=False)
    logged_in_user: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    ip_address: Mapped[str] = mapped_column(String(45), nullable=False)
    operating_system: Mapped[str] = mapped_column(String(100), nullable=False)
    agent_version: Mapped[str] = mapped_column(String(50), nullable=False)
    status: Mapped[ClientStatus] = mapped_column(
        SAEnum(ClientStatus, name="client_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=ClientStatus.UNKNOWN,
    )
    last_heartbeat: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relationships -------------------------------------------------------
    software_inventory: Mapped[List["SoftwareInventory"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )
    deployment_targets: Mapped[List["DeploymentTarget"]] = relationship(
        back_populates="client",
        cascade="all, delete-orphan",
    )
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        back_populates="client",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Client id={self.id} hostname={self.hostname!r} status={self.status}>"
