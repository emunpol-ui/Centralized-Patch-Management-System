"""
Repository service.

Contains the business logic for administrator installer package uploads
(FR-006 Software Repository Management), per the Service Layer Pattern
(SAD Section 5.5, Section 10.9 "Repository Service"). Coordinates the
``RepositoryPackage`` and Audit Log repositories with the filesystem-level
helpers in ``backend.utils.file_storage``, enforcing the FR-006 Upload
Validation Rules end-to-end:

    1. The uploaded file's extension must match the declared Installer
       Type.
    2. An approved package for the same software name/version must not
       already exist (duplicate-entry rejection).
    3. The file is streamed to a server-generated, sanitized filename
       under the configured repository directory, its SHA-256 checksum
       computed while being written, and its size checked against the
       configured maximum.
    4. Metadata (including the computed checksum) is persisted only after
       the file has been fully and successfully written to disk.

Package *approval workflow* changes and metadata *editing* (FR-017
Repository Maintenance) remain out of scope.

Extended by REP-002 (Backlog "Repository Dashboard") with the read
operations (``list_packages``, ``get_package``) and the removal operation
(``deactivate_package``) the administrator-facing dashboard requires.
Removal is implemented as a logical status change to ``INACTIVE`` (FR-017
"removal" semantics), not a physical row delete - see the design note on
``backend.models.repository_package.RepositoryPackage``.

Extended again by the repository-identity hardening ticket with an
optional ``publisher`` parameter on ``upload_package`` and an "Approval
Transition" step (``_supersede_previous_approved``): once a new upload is
persisted as ``APPROVED``, any other package(s) previously ``APPROVED``
for the same software identity are transitioned to ``INACTIVE``, so
``VersionComparisonService`` and deployment creation always resolve a
software identity to at most one current approved package, rather than
relying on "highest approved version wins" among several simultaneously
approved candidates.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import BinaryIO, List, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from backend.core.exceptions import AppException
from backend.models.enums import ApprovalStatus, AuditSeverity, InstallerType
from backend.models.repository_package import RepositoryPackage
from backend.repositories.audit_log_repository import AuditLogRepository
from backend.repositories.repository_package_repository import RepositoryPackageRepository
from backend.utils.file_storage import (
    InstallerFileError,
    generate_storage_filename,
    save_and_hash,
    validate_extension,
)

logger = logging.getLogger(__name__)


class RepositoryPackageValidationError(AppException):
    """
    Raised when an uploaded installer package fails an FR-006 Upload
    Validation Rule (extension/installer-type mismatch, oversized upload,
    or an empty file).
    """

    def __init__(self, message: str) -> None:
        super().__init__(message, status_code=400)


class RepositoryPackageConflictError(AppException):
    """
    Raised when an uploaded package duplicates an existing, approved
    repository entry (FR-006 Error Conditions: "Duplicate repository
    entries violate repository rules").
    """

    def __init__(self, software_name: str, version: str) -> None:
        super().__init__(
            f"An approved repository package for '{software_name}' version '{version}' already exists.",
            status_code=409,
        )


class RepositoryPackageNotFoundError(AppException):
    """
    Raised when a requested repository package id does not exist
    (Backlog REP-002 "Package details" / "Delete" deliverables).
    """

    def __init__(self, package_id: UUID) -> None:
        super().__init__(f"Repository package '{package_id}' was not found.", status_code=404)


class RepositoryService:
    """
    Repository package upload (FR-006).

    Stateless and safe to reuse across requests; the database session,
    storage location, and size limit are passed into each method call,
    consistent with every other service in this codebase.
    """

    def __init__(
        self,
        repository_package_repository: RepositoryPackageRepository | None = None,
        audit_log_repository: AuditLogRepository | None = None,
    ) -> None:
        self._packages = repository_package_repository or RepositoryPackageRepository()
        self._audit_logs = audit_log_repository or AuditLogRepository()

    def upload_package(
        self,
        db: Session,
        *,
        admin_id: UUID,
        software_name: str,
        version: str,
        installer_type: InstallerType,
        silent_command: str,
        original_filename: str | None,
        file_stream: BinaryIO,
        storage_dir: Path,
        max_size_bytes: int,
        publisher: str | None = None,
    ) -> RepositoryPackage:
        """
        Validate and persist a new administrator-uploaded installer
        package (FR-006 functional behavior steps 1-8).

        Raises:
            ``RepositoryPackageValidationError`` (400) - the uploaded
            file's extension does not match ``installer_type``, the file
            exceeds ``max_size_bytes``, or the file is empty.

            ``RepositoryPackageConflictError`` (409) - an approved
            package already exists for the same software identity
            (FR-007 Software Matching Rules: name, plus publisher when
            both sides report one) and version.

        The extension check runs before any file I/O, and the duplicate
        check runs before the (potentially large) file is streamed to
        disk, so a request that will ultimately be rejected fails as
        early as possible.

        ``publisher`` is optional (FR-004/FR-007: "where available").

        --------------------------------------------------------------
        APPROVAL TRANSITION (repository-identity hardening ticket)

        A successful upload defaults to ``APPROVED`` (see
        ``RepositoryPackageRepository.create``). Once persisted, any
        *other* package(s) previously ``APPROVED`` for the same software
        identity (same normalized name, and same normalized publisher
        when both report one) are superseded - transitioned to
        ``INACTIVE`` - so that at most one ``APPROVED`` package exists
        per identity going forward. This does not delete or otherwise
        alter those rows: their deployment history remains intact (see
        the design note on ``backend.models.repository_package.
        RepositoryPackage``), they simply stop being an eligible update
        target for ``VersionComparisonService`` and deployment creation.
        A new version that exactly duplicates the current approved
        version is already rejected above (``RepositoryPackageConflictError``)
        before this point, so supersession only ever applies to a
        genuinely different version.
        """
        try:
            validate_extension(original_filename, installer_type)
        except InstallerFileError as exc:
            raise RepositoryPackageValidationError(str(exc)) from exc

        existing = self._packages.get_active_conflict(
            db, software_name=software_name, version=version, publisher=publisher
        )
        if existing is not None:
            self._audit_logs.create(
                db,
                event_type="REPOSITORY_UPLOAD_CONFLICT",
                severity=AuditSeverity.WARNING,
                description=(
                    f"Repository upload rejected: an approved package for '{software_name}' version "
                    f"'{version}' already exists (existing package id={existing.id})."
                ),
                admin_id=admin_id,
            )
            db.commit()
            logger.warning(
                "Repository upload rejected for administrator %s: duplicate package '%s' v'%s'.",
                admin_id,
                software_name,
                version,
            )
            raise RepositoryPackageConflictError(software_name, version)

        storage_filename = generate_storage_filename(installer_type)
        try:
            file_size, checksum = save_and_hash(
                file_stream,
                storage_dir,
                storage_filename,
                max_size_bytes=max_size_bytes,
            )
        except InstallerFileError as exc:
            raise RepositoryPackageValidationError(str(exc)) from exc

        package = self._packages.create(
            db,
            software_name=software_name,
            version=version,
            installer_filename=storage_filename,
            installer_type=installer_type,
            silent_command=silent_command,
            checksum=checksum,
            file_size=file_size,
            publisher=publisher,
        )

        self._audit_logs.create(
            db,
            event_type="REPOSITORY_PACKAGE_UPLOADED",
            severity=AuditSeverity.INFO,
            description=(
                f"Repository package '{software_name}' version '{version}' uploaded "
                f"(installer_filename={storage_filename}, file_size={file_size}, checksum={checksum})."
            ),
            admin_id=admin_id,
        )

        self._supersede_previous_approved(
            db,
            admin_id=admin_id,
            new_package=package,
        )

        db.commit()

        logger.info(
            "Repository package %s (%s v%s, %d bytes) uploaded by administrator %s.",
            package.id,
            software_name,
            version,
            file_size,
            admin_id,
        )
        return package

    def _supersede_previous_approved(
        self,
        db: Session,
        *,
        admin_id: UUID,
        new_package: RepositoryPackage,
    ) -> None:
        """
        Transition any *other* package(s) still ``APPROVED`` for
        ``new_package``'s software identity to ``INACTIVE`` (the
        "Approval Transition" behavior - see ``upload_package``'s
        docstring).

        Uses ``list_approved_for_identity`` (identity match via
        ``software_identity_matches``) rather than
        ``get_active_conflict`` (which only reports an exact version
        duplicate): here we want *every* other approved package sharing
        this identity, regardless of whether its version is older or
        newer than ``new_package``'s, since FR-017's "one current
        approved package per identity" invariant is about approval
        state, not about always approving the highest version number.

        Not called from anywhere that already holds a conflicting
        version (``get_active_conflict`` rejects the upload before this
        method ever runs), so ``new_package`` itself is simply excluded
        by id rather than by version comparison.
        """
        candidates = self._packages.list_approved_for_identity(
            db, software_name=new_package.software_name, publisher=new_package.publisher
        )
        for candidate in candidates:
            if candidate.id == new_package.id:
                continue

            self._packages.deactivate(db, candidate)
            self._audit_logs.create(
                db,
                event_type="REPOSITORY_PACKAGE_SUPERSEDED",
                severity=AuditSeverity.INFO,
                description=(
                    f"Repository package '{candidate.software_name}' version '{candidate.version}' "
                    f"(id={candidate.id}) superseded by newly approved version '{new_package.version}' "
                    f"(id={new_package.id})."
                ),
                admin_id=admin_id,
            )
            logger.info(
                "Repository package %s (%s v%s) superseded by %s (v%s), approved by administrator %s.",
                candidate.id,
                candidate.software_name,
                candidate.version,
                new_package.id,
                new_package.version,
                admin_id,
            )

    def list_packages(
        self,
        db: Session,
        *,
        search: Optional[str] = None,
        approval_status: Optional[ApprovalStatus] = None,
    ) -> List[RepositoryPackage]:
        """
        Return repository packages for the administrator dashboard
        listing (Backlog REP-002 "Repository page" / "Search"
        deliverables), optionally filtered by a free-text ``search`` term
        (matched against software name/version) and/or ``approval_status``.

        This is a read-only operation; no audit log entry is recorded,
        consistent with ``VersionComparisonService``'s existing "read-only
        query, not a state-changing operation" rationale (see
        CURRENT_STATE.md's Logging Standards note).
        """
        return self._packages.list_all(db, search=search, approval_status=approval_status)

    def get_package(self, db: Session, package_id: UUID) -> RepositoryPackage:
        """
        Return a single repository package by id (Backlog REP-002
        "Package details" deliverable).

        Raises:
            ``RepositoryPackageNotFoundError`` (404) - no package exists
            with the given id.
        """
        package = self._packages.get_by_id(db, package_id)
        if package is None:
            raise RepositoryPackageNotFoundError(package_id)
        return package

    def deactivate_package(self, db: Session, *, admin_id: UUID, package_id: UUID) -> RepositoryPackage:
        """
        Deactivate (FR-017 "remove") an existing repository package
        (Backlog REP-002 "Delete" deliverable).

        Sets ``approval_status = INACTIVE`` rather than physically
        deleting the row, preserving package history and any existing
        ``Deployment`` relationships. Deactivating an already-``INACTIVE``
        package is idempotent - it is re-persisted as ``INACTIVE`` without
        error, so a repeated or racing delete request does not fail.

        Raises:
            ``RepositoryPackageNotFoundError`` (404) - no package exists
            with the given id.
        """
        package = self.get_package(db, package_id)
        already_inactive = package.approval_status == ApprovalStatus.INACTIVE

        package = self._packages.deactivate(db, package)

        if not already_inactive:
            self._audit_logs.create(
                db,
                event_type="REPOSITORY_PACKAGE_DEACTIVATED",
                severity=AuditSeverity.INFO,
                description=(
                    f"Repository package '{package.software_name}' version '{package.version}' "
                    f"(id={package.id}) deactivated."
                ),
                admin_id=admin_id,
            )
        db.commit()

        logger.info(
            "Repository package %s (%s v%s) deactivated by administrator %s.",
            package.id,
            package.software_name,
            package.version,
            admin_id,
        )
        return package
