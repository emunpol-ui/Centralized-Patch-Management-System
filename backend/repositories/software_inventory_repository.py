"""
Software inventory repository.

Pure data-access layer for the ``SoftwareInventory`` entity, per the
Repository Pattern (SAD Section 5.4, Section 11). Introduced by this
ticket (INV-001) - the ``software_inventory`` table itself was already
defined by CORE-002 (``backend/models/software_inventory.py``), but no
repository consumed it until now, per CORE-002's own deferral note in
``backend/repositories/__init__.py``.
"""

from __future__ import annotations

import uuid
from datetime import date as date_type
from datetime import datetime
from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.software_inventory import SoftwareInventory


class SoftwareInventoryRepository:
    """Data-access operations for the ``software_inventory`` table."""

    def list_for_client(self, db: Session, client_id: uuid.UUID) -> List[SoftwareInventory]:
        """Return every ``SoftwareInventory`` record currently stored for ``client_id``."""
        stmt = select(SoftwareInventory).where(SoftwareInventory.client_id == client_id)
        return list(db.execute(stmt).scalars().all())

    def create(
        self,
        db: Session,
        *,
        client_id: uuid.UUID,
        software_name: str,
        version: str,
        publisher: Optional[str],
        install_date: Optional[date_type],
        install_location: Optional[str],
        last_scanned: datetime,
    ) -> SoftwareInventory:
        """Persist a brand-new ``SoftwareInventory`` record and flush it."""
        record = SoftwareInventory(
            client_id=client_id,
            software_name=software_name,
            version=version,
            publisher=publisher,
            install_date=install_date,
            install_location=install_location,
            last_scanned=last_scanned,
        )
        db.add(record)
        db.flush()
        return record

    def update(
        self,
        db: Session,
        record: SoftwareInventory,
        *,
        version: str,
        publisher: Optional[str],
        install_date: Optional[date_type],
        install_location: Optional[str],
        last_scanned: datetime,
    ) -> SoftwareInventory:
        """
        Refresh an already-persisted ``SoftwareInventory`` record to reflect
        the client's most recently reported state for that application
        (FR-005: "Existing inventory records shall be updated to reflect
        the client's most recent software state"). ``software_name`` and
        ``client_id`` are deliberately not accepted here - they are the
        identity of the row being updated, not mutable attributes of it.
        """
        record.version = version
        record.publisher = publisher
        record.install_date = install_date
        record.install_location = install_location
        record.last_scanned = last_scanned
        db.add(record)
        db.flush()
        return record

    def delete(self, db: Session, record: SoftwareInventory) -> None:
        """
        Remove a ``SoftwareInventory`` record.

        Used by ``InventoryService`` to drop records for software that was
        present in a client's previous upload but is absent from its most
        recent one (i.e. software the client has since uninstalled) - see
        that service's module docstring for the full design rationale.
        """
        db.delete(record)
        db.flush()
