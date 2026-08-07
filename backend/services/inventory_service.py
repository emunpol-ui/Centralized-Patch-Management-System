"""
Inventory service.

Contains the business logic behind Client Agent software inventory
processing (FR-005 Software Inventory Upload), per the Service Layer
Pattern (SAD Section 5.5, Section 10.8 "Inventory Service"). Coordinates
the ``SoftwareInventory`` and Audit Log repositories; enforces no rules
beyond what FR-005 requires. Comparing installed versions against the
approved repository (FR-007) is explicitly out of scope for this ticket
(INV-001) - see UPDATE-001 in the Backlog.

--------------------------------------------------------------------------
DESIGN NOTE - full-sync (insert / update / remove) rather than append-only

FR-005's functional behavior lists: "Existing inventory records associated
with the client are retrieved" and "The server inserts new software
records and updates existing entries as necessary" - i.e. an upload is
matched against the client's *current* stored inventory, not simply
appended to it. The PRS does not explicitly describe what should happen to
a stored record whose software is no longer present in a new upload, but
FR-004/FR-005 together describe each upload as a fresh, complete scan of
"installed software" at that point in time (not an incremental diff the
Client Agent computes itself). Treating each upload as the client's
complete, authoritative current state - and therefore removing any
previously stored record that the new upload does not reaffirm - is the
interpretation that keeps the server's stored inventory accurate for
FR-007 version comparison and the FR-005 dashboard requirement ("the
administrator can view the latest software inventory"): a record for
software the client uninstalled weeks ago must not continue to display as
"currently installed" indefinitely. This is a documented design decision,
not a change to any documented requirement.

--------------------------------------------------------------------------
DESIGN NOTE - matching key used to decide insert vs. update vs. remove

Records are matched on ``software_name`` alone (trimmed, case-insensitive)
within a given client's inventory. This ticket does not implement the full
FR-007 "Software Matching Rules" (architecture-suffix stripping, publisher
tie-breaking) - those rules exist specifically to support cross-referencing
against the *repository* for version comparison (UPDATE-001), a different
problem from deciding whether two uploads, from the same client, days
apart, describe the same already-installed application. A simple
case-insensitive name match is sufficient for that narrower purpose and
avoids duplicating FR-007 logic ahead of the ticket that actually owns it.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, List, Set

from sqlalchemy.orm import Session

from backend.models.client import Client
from backend.models.enums import AuditSeverity
from backend.models.software_inventory import SoftwareInventory
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.software_inventory_repository import SoftwareInventoryRepository
from backend.schemas.inventory import SoftwareInventoryItem

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class InventoryUploadResult:
    """Outcome summary of a single inventory upload (FR-005 Outputs table)."""

    total: int
    created: int
    updated: int
    removed: int


def _normalize_key(software_name: str) -> str:
    """Case/whitespace-insensitive matching key for a software name."""
    return software_name.strip().casefold()


class InventoryService:
    """
    Client Agent software inventory processing (FR-005).

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase.
    """

    def __init__(
        self,
        inventory_repository: SoftwareInventoryRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._inventory = inventory_repository or SoftwareInventoryRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()

    def upload_inventory(
        self, db: Session, *, client: Client, items: List[SoftwareInventoryItem]
    ) -> InventoryUploadResult:
        """
        Process a full software inventory upload for ``client`` (FR-005
        functional behavior steps 2-6).

        ``client`` must already be the authenticated, registered ``Client``
        resolved by ``require_client_api_key`` (AUTH-002) - mirroring
        ``HeartbeatService.record_heartbeat``, no additional existence
        check is performed here.
        """
        existing_records = self._inventory.list_for_client(db, client.id)
        existing_by_key: Dict[str, SoftwareInventory] = {
            _normalize_key(record.software_name): record for record in existing_records
        }

        scanned_at = datetime.now(timezone.utc)
        seen_keys: Set[str] = set()
        created = 0
        updated = 0

        for item in items:
            key = _normalize_key(item.software_name)
            if key in seen_keys:
                # Duplicate software name within the same upload payload
                # (FR-004 requires the Client Agent to filter these, but the
                # server does not trust that solely happened) - the last
                # occurrence in the payload wins.
                logger.debug(
                    "Duplicate software name in upload for client %s: %r (last occurrence wins).",
                    client.id,
                    item.software_name,
                )
            seen_keys.add(key)

            record = existing_by_key.get(key)
            if record is None:
                record = self._inventory.create(
                    db,
                    client_id=client.id,
                    software_name=item.software_name,
                    version=item.version,
                    publisher=item.publisher,
                    install_date=item.install_date,
                    install_location=item.install_location,
                    last_scanned=scanned_at,
                )
                existing_by_key[key] = record
                created += 1
            else:
                self._inventory.update(
                    db,
                    record,
                    version=item.version,
                    publisher=item.publisher,
                    install_date=item.install_date,
                    install_location=item.install_location,
                    last_scanned=scanned_at,
                )
                updated += 1

        removed = 0
        for key, record in list(existing_by_key.items()):
            if key not in seen_keys:
                self._inventory.delete(db, record)
                removed += 1

        total = len(seen_keys)
        self._audit_logs.create(
            db,
            event_type="INVENTORY_UPLOADED",
            severity=AuditSeverity.INFO,
            description=(
                f"Software inventory uploaded for client '{client.hostname}': "
                f"{created} added, {updated} updated, {removed} removed, {total} total records."
            ),
            client_id=client.id,
        )
        db.commit()

        logger.info(
            "Inventory upload processed for client %s (%s): created=%d updated=%d removed=%d total=%d.",
            client.id,
            client.hostname,
            created,
            updated,
            removed,
            total,
        )

        return InventoryUploadResult(total=total, created=created, updated=updated, removed=removed)
