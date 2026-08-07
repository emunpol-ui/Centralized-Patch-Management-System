"""
Repository package repository.

Pure data-access layer for the ``RepositoryPackage`` entity, per the
Repository Pattern (SAD Section 5.4, Section 11). Introduced by INV-002
(Backlog UPDATE-001, FR-007 Software Version Comparison) as the minimal
read-only slice needed to compare installed software against the approved
repository catalog. The ``repository_packages`` table itself was already
defined by CORE-002 (``backend/models/repository_package.py``), but - like
``software_inventory`` before INV-001 - no repository consumed it until
INV-002 (see the deferral note in ``backend/repositories/__init__.py``).

Extended by this ticket (REP-001, FR-006 Software Repository Management)
with the write operations package upload requires: ``create`` and
``get_active_conflict`` (FR-006 duplicate-entry detection). Per the
INV-002 deferral note, these are added directly to this existing
repository rather than creating a second, competing one for the same
table.

Metadata *editing* and *removal* (FR-017 Repository Maintenance) remain
out of scope for this ticket and are not implemented here.
"""

from __future__ import annotations

from typing import List, Optional

from sqlalchemy import select
from sqlalchemy.orm import Session

from backend.models.enums import ApprovalStatus, InstallerType
from backend.models.repository_package import RepositoryPackage
from backend.utils.version_compare import normalize_software_name


class RepositoryPackageRepository:
    """Data-access operations for the ``repository_packages`` table."""

    def list_approved(self, db: Session) -> List[RepositoryPackage]:
        """
        Return every ``RepositoryPackage`` currently ``APPROVED`` (FR-007
        precondition: "Approved software versions have been defined").

        Packages set to ``INACTIVE`` (the FR-017 "removal" mechanism -
        see the design note on ``backend.models.repository_package.
        RepositoryPackage``) are intentionally excluded: an inactive
        package is no longer an administrator-approved version and must
        not be treated as an update target for comparison purposes.
        """
        stmt = select(RepositoryPackage).where(RepositoryPackage.approval_status == ApprovalStatus.APPROVED)
        return list(db.execute(stmt).scalars().all())

    def get_active_conflict(
        self, db: Session, *, software_name: str, version: str
    ) -> Optional[RepositoryPackage]:
        """
        Return an existing ``APPROVED`` package that would conflict with a
        new upload of the same ``software_name``/``version`` (FR-006
        Error Conditions: "Duplicate repository entries violate
        repository rules"), or ``None`` if no such package exists.

        Name matching reuses FR-007's ``normalize_software_name`` rule
        (trim, case-fold, strip a trailing architecture suffix) so that,
        for example, ``"Google Chrome"`` and ``"google chrome"`` are
        correctly treated as the same package for duplicate-detection
        purposes - the same normalization already applied when matching
        inventory against the repository. ``version`` is compared as a
        trimmed, exact string match: two installers legitimately
        targeting the identical version string is precisely the duplicate
        condition FR-006 guards against.

        ``INACTIVE`` packages (FR-017 "removed" entries) are intentionally
        excluded - a previously removed package must not block a new
        upload of the same name/version.
        """
        normalized_target_name = normalize_software_name(software_name)
        normalized_target_version = version.strip()

        stmt = select(RepositoryPackage).where(RepositoryPackage.approval_status == ApprovalStatus.APPROVED)
        for candidate in db.execute(stmt).scalars().all():
            if (
                normalize_software_name(candidate.software_name) == normalized_target_name
                and candidate.version.strip() == normalized_target_version
            ):
                return candidate
        return None

    def create(
        self,
        db: Session,
        *,
        software_name: str,
        version: str,
        installer_filename: str,
        installer_type: InstallerType,
        silent_command: str,
        checksum: str,
        file_size: int,
        approval_status: ApprovalStatus = ApprovalStatus.APPROVED,
    ) -> RepositoryPackage:
        """
        Persist a new ``RepositoryPackage`` record and flush it (FR-006
        functional behavior: "Metadata, including the computed checksum,
        is recorded in the database").

        Newly uploaded packages default to ``APPROVED`` - PRS Chapter 4
        FR-006 describes an uploaded package as immediately "available for
        deployment selection" once its metadata is recorded, with no
        separate approval workflow currently defined (SYS-*/future
        enhancement territory per the SAD's Extensibility notes).
        """
        package = RepositoryPackage(
            software_name=software_name,
            version=version,
            installer_filename=installer_filename,
            installer_type=installer_type,
            silent_command=silent_command,
            checksum=checksum,
            file_size=file_size,
            approval_status=approval_status,
        )
        db.add(package)
        db.flush()
        return package
