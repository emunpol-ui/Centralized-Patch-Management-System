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

Extended by REP-002 (Backlog "Repository Dashboard", FR-006 dashboard
integration / FR-017 Repository Maintenance) with the read operations the
dashboard requires (``list_all``, ``get_by_id``) and the status-update
operation backing package removal (``deactivate``). Metadata *editing*
(e.g. changing the silent install command after upload) remains out of
scope and is not implemented here.

Extended again by the repository-identity hardening ticket with
publisher-aware identity matching (``software_identity_matches``, shared
with ``VersionComparisonService``) and ``list_approved_for_identity``,
which ``RepositoryService`` uses to supersede a software identity's
previous approved package when a new one is approved, so at most one
``APPROVED`` package exists per identity going forward.
"""

from __future__ import annotations

from typing import List, Optional
from uuid import UUID

from sqlalchemy import or_, select
from sqlalchemy.orm import Session

from backend.models.enums import ApprovalStatus, InstallerType
from backend.models.repository_package import RepositoryPackage
from backend.utils.version_compare import same_version, software_identity_matches


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
        self, db: Session, *, software_name: str, version: str, publisher: Optional[str] = None
    ) -> Optional[RepositoryPackage]:
        """
        Return an existing ``APPROVED`` package that would conflict with a
        new upload of the same software identity and version (FR-006
        Error Conditions: "Duplicate repository entries violate
        repository rules"), or ``None`` if no such package exists.

        Identity matching uses ``software_identity_matches`` (FR-007
        Software Matching Rules: normalized name, plus normalized
        publisher when *both* sides report one) - the same predicate used
        by ``VersionComparisonService`` - so that, for example,
        ``"Google Chrome"`` and ``"google chrome"`` are treated as the
        same package, while two different vendors' same-named software
        are not conflated once both supply a publisher. Version equality
        uses ``same_version`` so that, consistent with FR-007's numeric
        version comparison rules, ``"4.15"`` and ``"4.15.0"`` are
        recognized as the identical version for duplicate-detection
        purposes, not merely for update-status purposes.

        ``INACTIVE`` packages (FR-017 "removed" entries) are intentionally
        excluded - a previously removed package must not block a new
        upload of the same identity/version.
        """
        stmt = select(RepositoryPackage).where(RepositoryPackage.approval_status == ApprovalStatus.APPROVED)
        for candidate in db.execute(stmt).scalars().all():
            if (
                software_identity_matches(software_name, publisher, candidate.software_name, candidate.publisher)
                and same_version(version, candidate.version)
            ):
                return candidate
        return None

    def list_approved_for_identity(
        self, db: Session, *, software_name: str, publisher: Optional[str] = None
    ) -> List[RepositoryPackage]:
        """
        Return every currently ``APPROVED`` package that shares the given
        software identity (FR-007 Software Matching Rules, via
        ``software_identity_matches``).

        Used by ``RepositoryService`` to enforce the "one current
        approved package per software identity" invariant when a new
        package is approved (the "Approval Transition" behavior): the
        previously approved package(s) for the same identity are
        superseded rather than left ``APPROVED`` alongside the new one.
        Under normal operation this returns at most one package; it may
        legitimately return more than one for data uploaded before this
        invariant was introduced, which callers should treat as "all of
        these are superseded", not as an error.
        """
        stmt = select(RepositoryPackage).where(RepositoryPackage.approval_status == ApprovalStatus.APPROVED)
        return [
            candidate
            for candidate in db.execute(stmt).scalars().all()
            if software_identity_matches(software_name, publisher, candidate.software_name, candidate.publisher)
        ]

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
        publisher: Optional[str] = None,
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

        ``publisher`` is optional (FR-004/FR-007: "where available") and
        defaults to ``None`` for callers - and legacy rows - that do not
        supply it.
        """
        package = RepositoryPackage(
            software_name=software_name,
            version=version,
            installer_filename=installer_filename,
            installer_type=installer_type,
            silent_command=silent_command,
            checksum=checksum,
            file_size=file_size,
            publisher=publisher,
            approval_status=approval_status,
        )
        db.add(package)
        db.flush()
        return package

    def list_all(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        approval_status: Optional[ApprovalStatus] = None,
    ) -> List[RepositoryPackage]:
        """
        Return repository packages for the administrator-facing dashboard
        (Backlog REP-002 "Repository page" / "Search" deliverables).

        ``search`` performs a simple, case-insensitive substring match
        against ``software_name`` (SQLite ``LIKE`` is case-insensitive for
        ASCII by default), appropriate for the current proof-of-concept
        scope - no full-text search engine is introduced. ``approval_status``
        optionally restricts results to a single status (``APPROVED`` or
        ``INACTIVE``); omitting it returns packages of every status so the
        administrator can review previously removed packages as well as
        active ones. Results are ordered by ``software_name`` for a stable,
        predictable dashboard listing.
        """
        stmt = select(RepositoryPackage)
        if approval_status is not None:
            stmt = stmt.where(RepositoryPackage.approval_status == approval_status)
        if search:
            term = search.strip()
            if term:
                pattern = f"%{term}%"
                stmt = stmt.where(
                    or_(
                        RepositoryPackage.software_name.ilike(pattern),
                        RepositoryPackage.version.ilike(pattern),
                    )
                )
        stmt = stmt.order_by(RepositoryPackage.software_name.asc(), RepositoryPackage.version.asc())
        return list(db.execute(stmt).scalars().all())

    def get_by_id(self, db: Session, package_id: UUID) -> Optional[RepositoryPackage]:
        """
        Return a single ``RepositoryPackage`` by primary key, or ``None``
        if no such package exists (Backlog REP-002 "Package details" /
        "Delete" deliverables).
        """
        return db.get(RepositoryPackage, package_id)

    def deactivate(self, db: Session, package: RepositoryPackage) -> RepositoryPackage:
        """
        Set ``approval_status = INACTIVE`` on an existing package (FR-017
        "removal" semantics - see the design note on
        ``backend.models.repository_package.RepositoryPackage``) and flush
        the change.

        This is a logical deactivation, not a physical row delete: the
        package row, its checksum, and its relationship to any existing
        ``Deployment`` records are preserved. Once deactivated, the
        package is automatically excluded from ``list_approved`` and
        ``get_active_conflict`` (both already status-filtered to
        ``APPROVED``), so it stops appearing as an active/deployable
        package and no longer participates in ``VersionComparisonService``
        matching, without any change required to either of those.
        """
        package.approval_status = ApprovalStatus.INACTIVE
        db.add(package)
        db.flush()
        return package
