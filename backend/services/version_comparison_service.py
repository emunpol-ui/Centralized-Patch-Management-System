"""
Version comparison service.

Contains the business logic behind FR-007 Software Version Comparison,
per the Service Layer Pattern (SAD Section 5.5, Section 10 - "Version
Comparison Module" in SAD Section 3.5 / Section 9.4's module table).
Compares each ``SoftwareInventory`` record (INV-001) belonging to a
client against the administrator-approved ``RepositoryPackage`` catalog
and classifies every installed item as Up-to-Date, Update Available, or
Not Managed.

--------------------------------------------------------------------------
DESIGN NOTE - computed on demand, not persisted

FR-007 step 6 ("Results are stored") describes an in-memory step within a
single request/response cycle ("Results are stored. Results are displayed
in the administrator dashboard."), not a dedicated database entity - PRS
Chapter 7's entity list (Clients, Software Inventory, Repository,
Deployment Jobs, Deployment Results, Audit Logs, System Configuration,
Administrators) has no "comparison results" table, and none was added by
this ticket. Update status is a derived view over two already-persisted
tables (``software_inventory`` and ``repository_packages``), recomputed
on each request rather than cached as new state that could drift out of
sync with either source table.

This mirrors the project's established pattern for other derived,
read-time state - see CURRENT_STATE.md "Architecture Notes": "Client
`OFFLINE` status is currently computed at read time rather than
maintained by a background service." If a future ticket needs persisted
comparison snapshots (e.g. historical reporting), that is new, additive
scope layered on top of this service, not a change to it.

--------------------------------------------------------------------------
DESIGN NOTE - matching and comparison rules live in a separate module

Software-name normalization and numeric version comparison (FR-007
"Software Matching Rules" / "Version Comparison Rules") are implemented
as pure, database-independent functions in
``backend.utils.version_compare`` rather than inline in this service, so
they can be unit-tested in isolation and reused without a database
session. This service is responsible only for orchestrating repositories
and applying those rules to produce a per-item classification. See
``_select_best_match`` below for why publisher is not used to
disambiguate repository matches (``RepositoryPackage`` has no publisher
column in the existing schema).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.models.enums import UpdateStatus
from backend.models.repository_package import RepositoryPackage
from backend.models.software_inventory import SoftwareInventory
from backend.repositories.repository_package_repository import RepositoryPackageRepository
from backend.repositories.software_inventory_repository import SoftwareInventoryRepository
from backend.utils.version_compare import compare_versions, normalize_software_name, parse_version

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SoftwareUpdateStatus:
    """
    One inventory item's FR-007 comparison outcome (PRS FR-007 Outputs
    table: "Comparison Result - Software update status").
    """

    inventory_id: UUID
    software_name: str
    installed_version: str
    publisher: Optional[str]
    status: UpdateStatus
    approved_version: Optional[str] = None
    repository_package_id: Optional[UUID] = None


class VersionComparisonService:
    """
    Compares a client's installed software inventory against the
    approved repository catalog (FR-007).

    Stateless and safe to reuse across requests; the database session is
    passed into each method call, consistent with every other service in
    this codebase (see ``InventoryService``, ``HeartbeatService``).
    """

    def __init__(
        self,
        inventory_repository: SoftwareInventoryRepository | None = None,
        repository_package_repository: RepositoryPackageRepository | None = None,
    ) -> None:
        self._inventory = inventory_repository or SoftwareInventoryRepository()
        self._repository_packages = repository_package_repository or RepositoryPackageRepository()

    def compare_client_inventory(self, db: Session, *, client_id: UUID) -> List[SoftwareUpdateStatus]:
        """
        Compare every ``SoftwareInventory`` record belonging to
        ``client_id`` against the approved repository catalog (FR-007
        functional behavior steps 1-5; step 6 "Results are stored" is
        realized as this method's return value - see module docstring).

        Reuses ``SoftwareInventoryRepository.list_for_client`` (INV-001)
        unmodified, and the read-only
        ``RepositoryPackageRepository.list_approved`` introduced
        alongside this service. Performs no writes and requires no
        existence check on ``client_id`` beyond what the caller (the API
        router) has already established; an unknown client simply yields
        an empty inventory list and therefore an empty result list.
        """
        inventory_records = self._inventory.list_for_client(db, client_id)
        approved_packages = self._repository_packages.list_approved(db)
        catalog_index = _build_catalog_index(approved_packages)

        results = [_classify(record, catalog_index) for record in inventory_records]

        logger.debug(
            "Version comparison computed for client %s: %d inventory item(s) against %d approved package(s).",
            client_id,
            len(inventory_records),
            len(approved_packages),
        )
        return results


def _build_catalog_index(packages: List[RepositoryPackage]) -> Dict[str, List[RepositoryPackage]]:
    """Group approved repository packages by normalized software name for O(1) lookup."""
    index: Dict[str, List[RepositoryPackage]] = {}
    for package in packages:
        key = normalize_software_name(package.software_name)
        index.setdefault(key, []).append(package)
    return index


def _select_best_match(
    record: SoftwareInventory, candidates: List[RepositoryPackage]
) -> Optional[RepositoryPackage]:
    """
    Choose the best-matching ``RepositoryPackage`` among ``candidates``
    that already share ``record``'s normalized software name (FR-007
    Software Matching Rules).

    FR-007 additionally allows publisher to be considered "where
    available" to reduce false matches, but ``RepositoryPackage`` (PRS
    Section 7.5.3 / ``backend/models/repository_package.py``) does not
    currently model a ``publisher`` column - only ``SoftwareInventory``
    does - so publisher-based disambiguation is not applied here. This is
    a schema constraint inherited from the existing, already-implemented
    ``RepositoryPackage`` model (not modified by this ticket, per its
    "modify only the minimum files required" instruction), not a
    deviation from FR-007's *intent*; name-only matching is the strictest
    disambiguation the current data model supports.

    If several candidates remain (e.g. more than one approved entry
    happens to share a normalized name), the one with the highest
    parseable version is preferred, as the most-current administrator-
    approved target; a candidate with an unparseable version is only
    chosen if no parseable candidate exists, so an obviously comparable
    match is never skipped in favor of a broken one.
    """
    if not candidates:
        return None

    def sort_key(package: RepositoryPackage) -> tuple:
        parsed = parse_version(package.version)
        return (parsed is not None, parsed or ())

    return max(candidates, key=sort_key)


def _classify(
    record: SoftwareInventory, catalog_index: Dict[str, List[RepositoryPackage]]
) -> SoftwareUpdateStatus:
    """
    Classify a single installed software item per FR-007 Status
    Definitions (Up-to-Date / Update Available / Not Managed).
    """
    key = normalize_software_name(record.software_name)
    candidates = catalog_index.get(key, [])
    match = _select_best_match(record, candidates)

    if match is None:
        # "No approved repository entry exists for the software" - FR-007
        # Status Definitions table, Not Managed.
        return SoftwareUpdateStatus(
            inventory_id=record.id,
            software_name=record.software_name,
            installed_version=record.version,
            publisher=record.publisher,
            status=UpdateStatus.NOT_MANAGED,
        )

    comparison = compare_versions(record.version, match.version)
    if comparison is None:
        # "If a version string cannot be parsed into numeric segments,
        # the associated software shall be classified as Not Managed and
        # flagged for administrator review; it shall not be assumed to
        # be Up-to-Date." (FR-007 Version Comparison Rules)
        return SoftwareUpdateStatus(
            inventory_id=record.id,
            software_name=record.software_name,
            installed_version=record.version,
            publisher=record.publisher,
            status=UpdateStatus.NOT_MANAGED,
            approved_version=match.version,
            repository_package_id=match.id,
        )

    # "If the installed version is older than the approved version, the
    # software shall be identified as requiring an update. If the
    # installed version matches or exceeds the approved version, no
    # update shall be recommended." (FR-007 Description)
    status = UpdateStatus.UPDATE_AVAILABLE if comparison < 0 else UpdateStatus.UP_TO_DATE
    return SoftwareUpdateStatus(
        inventory_id=record.id,
        software_name=record.software_name,
        installed_version=record.version,
        publisher=record.publisher,
        status=status,
        approved_version=match.version,
        repository_package_id=match.id,
    )
