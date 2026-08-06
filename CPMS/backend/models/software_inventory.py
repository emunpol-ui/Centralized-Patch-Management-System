"""
SoftwareInventory ORM model.

Represents a single installed-application record collected from a managed
client (PRS Section 7.5.2 / FR-004 Software Inventory Scan, FR-005
Software Inventory Upload).
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from typing import TYPE_CHECKING, Optional

from sqlalchemy import Date, DateTime, ForeignKey, Index, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import AuditModel

if TYPE_CHECKING:
    from backend.models.client import Client


class SoftwareInventory(AuditModel):
    """
    One installed-application record for a given client.

    A client typically has many ``SoftwareInventory`` rows (one per
    installed application). ``last_scanned`` is kept as its own column,
    distinct from the inherited ``updated_at``, because it carries
    specific business meaning for FR-007 version comparison (the moment
    this software was last confirmed present on the client via a scan),
    whereas ``updated_at`` only reflects when any column on the row last
    changed.
    """

    __tablename__ = "software_inventory"
    __table_args__ = (
        Index("ix_software_inventory_client_software", "client_id", "software_name"),
    )

    client_id: Mapped[uuid.UUID] = mapped_column(
        ForeignKey("clients.id", ondelete="CASCADE"), nullable=False
    )
    software_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    install_date: Mapped[Optional[date_type]] = mapped_column(Date, nullable=True)
    install_location: Mapped[Optional[str]] = mapped_column(String(500), nullable=True)
    last_scanned: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Relationships -------------------------------------------------------
    client: Mapped["Client"] = relationship(back_populates="software_inventory")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<SoftwareInventory id={self.id} software_name={self.software_name!r} client_id={self.client_id}>"
