"""
Repository management router (FR-006 Software Repository Management).

Implements the administrator-facing installer upload endpoint (Backlog
REP-001 "Installer upload" deliverable): ``POST
/api/admin/repository/packages``. Grouped under ``/api/admin`` -
consistent with ``backend/api/routers/auth.py`` and
``backend/api/routers/updates.py`` - since this is an administrator-facing
action belonging to the SAD's "Repository Management Module" (SAD Section
9.4, Section 10.9), not a Client Agent-facing endpoint. It is a
state-changing request, so it is protected by both an active administrator
session (``CurrentAdministrator``) and a valid CSRF token
(``CSRFProtection``), per NFR-028 - the same pattern already used by
``POST /api/admin/keys`` in ``auth.py``.

Uses ``multipart/form-data`` (FastAPI ``File``/``Form`` parameters) rather
than a JSON body, since the request carries a binary installer file
alongside its metadata (PRS Appendix C "Upload Repository Package").

Extended by REP-002 (Backlog "Repository Dashboard") with three
additional administrator-facing endpoints:

    * ``GET /api/admin/repository/packages`` - list/search packages.
    * ``GET /api/admin/repository/packages/{package_id}`` - package
      details.
    * ``POST /api/admin/repository/packages/{package_id}/deactivate`` -
      remove (deactivate) a package (FR-017).

The two ``GET`` endpoints are read-only and therefore require only an
active administrator session (no CSRF token - NFR-028 scopes CSRF to
state-changing requests, the same reasoning already applied to
``GET /api/admin/clients/{client_id}/updates`` in ``updates.py``). The
``POST .../deactivate`` endpoint is state-changing and therefore requires
both the session and a valid CSRF token, matching the upload endpoint
below.
"""

from __future__ import annotations

import logging
from typing import Any, Dict
from uuid import UUID

from fastapi import APIRouter, File, Form, Query, UploadFile, status
from pydantic import ValidationError

from backend.api.dependencies import (
    CSRFProtection,
    CurrentAdministrator,
    DBSessionDependency,
    RepositoryServiceDependency,
    SettingsDependency,
)
from backend.core.exceptions import AppException
from backend.models.enums import ApprovalStatus, InstallerType
from backend.schemas.repository import (
    RepositoryPackageListResponse,
    RepositoryPackageResponse,
    RepositoryPackageUploadMetadata,
)
from backend.api.dependencies import SystemConfigurationServiceDependency

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin/repository", tags=["Repository Management"])


class RepositoryPackageMetadataError(AppException):
    """
    Raised when the ``multipart/form-data`` metadata fields accompanying
    an installer upload fail ``RepositoryPackageUploadMetadata``
    validation (FR-006).
    """

    def __init__(self, exc: ValidationError) -> None:
        details = "; ".join(
            f"{'.'.join(str(part) for part in error['loc'])}: {error['msg']}" for error in exc.errors()
        )
        super().__init__(f"Invalid repository package metadata: {details}", status_code=400)


@router.post(
    "/packages",
    status_code=status.HTTP_201_CREATED,
    summary="Upload an approved installer package",
    description=(
        "Upload a new administrator-approved software installer into the centralized repository "
        "(FR-006). Validates the installer extension against the declared installer type, rejects "
        "duplicate approved packages, computes a SHA-256 checksum, stores the file under a "
        "server-generated filename, and persists the package metadata."
    ),
)
async def upload_repository_package(
    db: DBSessionDependency,
    repository_service: RepositoryServiceDependency,
    settings: SettingsDependency,
    config_service: SystemConfigurationServiceDependency,
    current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
    installer: UploadFile = File(..., description="The installer package file (.exe or .msi)."),
    software_name: str = Form(..., description="Approved software name (RepositoryPackage.software_name)."),
    version: str = Form(..., description="Approved software version (RepositoryPackage.version)."),
    installer_type: InstallerType = Form(..., description="Installer type: EXE or MSI."),
    silent_command: str = Form(
        ...,
        description="Silent installation command, referencing the installer via the '{installer_path}' "
        "placeholder token.",
    ),
) -> Dict[str, Any]:
    """
    Upload and register a new repository installer package (FR-006).

    Requires both an active administrator session and a valid CSRF token
    (NFR-028), since this is a state-changing request. Metadata is
    validated with ``RepositoryPackageUploadMetadata`` before any file
    I/O occurs, so malformed requests are rejected before the (larger)
    installer upload is streamed to disk.
    """
    try:
        metadata = RepositoryPackageUploadMetadata(
            software_name=software_name,
            version=version,
            installer_type=installer_type,
            silent_command=silent_command,
        )
    except ValidationError as exc:
        raise RepositoryPackageMetadataError(exc) from exc

    # AFTER:
    # SYS-001 - use the effective (persisted-override-or-default)
    # maximum upload size rather than the static environment default,
    # so a saved override takes effect on the very next upload.
    effective = config_service.get_effective_settings(db, settings)
    package = repository_service.upload_package(
        db,
        admin_id=current_admin.id,
        software_name=metadata.software_name,
        version=metadata.version,
        installer_type=metadata.installer_type,
        silent_command=metadata.silent_command,
        original_filename=installer.filename,
        file_stream=installer.file,
        storage_dir=settings.repository_path,
        max_size_bytes=effective.max_installer_upload_size_bytes,
    )

    response = RepositoryPackageResponse.model_validate(package)

    logger.debug(
        "Administrator %s uploaded repository package %s (%s v%s).",
        current_admin.id,
        package.id,
        package.software_name,
        package.version,
    )

    return {
        "success": True,
        "message": "Repository package uploaded successfully.",
        "data": response.model_dump(mode="json"),
    }


@router.get(
    "/packages",
    status_code=status.HTTP_200_OK,
    summary="List repository packages",
    description=(
        "List repository packages, optionally filtered by a free-text search term (matched against "
        "software name/version) and/or approval status (FR-006 dashboard integration / Backlog REP-002)."
    ),
)
async def list_repository_packages(
    db: DBSessionDependency,
    repository_service: RepositoryServiceDependency,
    _current_admin: CurrentAdministrator,
    search: str | None = Query(
        default=None, max_length=255, description="Case-insensitive substring match on name/version."
    ),
    approval_status: ApprovalStatus | None = Query(
        default=None, description="Restrict results to Approved or Inactive packages only."
    ),
) -> Dict[str, Any]:
    """
    List repository packages for the administrator dashboard (Backlog
    REP-002 "Repository page" / "Search" deliverables).

    Read-only; requires only an active administrator session (no CSRF
    token required for GET requests, per NFR-028).
    """
    packages = repository_service.list_packages(db, search=search, approval_status=approval_status)
    response = RepositoryPackageListResponse(
        packages=[RepositoryPackageResponse.model_validate(package) for package in packages],
        total=len(packages),
    )
    return {
        "success": True,
        "message": "Repository packages retrieved successfully.",
        "data": response.model_dump(mode="json"),
    }


@router.get(
    "/packages/{package_id}",
    status_code=status.HTTP_200_OK,
    summary="Get repository package details",
    description="Retrieve the full metadata for a single repository package (Backlog REP-002).",
)
async def get_repository_package(
    db: DBSessionDependency,
    repository_service: RepositoryServiceDependency,
    _current_admin: CurrentAdministrator,
    package_id: UUID,
) -> Dict[str, Any]:
    """
    Retrieve a single repository package's details (Backlog REP-002
    "Package details" deliverable).

    Read-only; requires only an active administrator session. Returns 404
    if no package exists with the given id (``RepositoryPackageNotFoundError``,
    handled by the global ``AppException`` handler).
    """
    package = repository_service.get_package(db, package_id)
    response = RepositoryPackageResponse.model_validate(package)
    return {
        "success": True,
        "message": "Repository package retrieved successfully.",
        "data": response.model_dump(mode="json"),
    }


@router.post(
    "/packages/{package_id}/deactivate",
    status_code=status.HTTP_200_OK,
    summary="Deactivate (remove) a repository package",
    description=(
        "Deactivate a repository package (FR-017 Repository Maintenance / Backlog REP-002 'Delete' "
        "deliverable). Implemented as a logical status change to Inactive rather than a physical row "
        "delete, preserving package history and existing deployment relationships."
    ),
)
async def deactivate_repository_package(
    db: DBSessionDependency,
    repository_service: RepositoryServiceDependency,
    current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
    package_id: UUID,
) -> Dict[str, Any]:
    """
    Deactivate ("remove") a repository package (Backlog REP-002 "Delete"
    deliverable).

    Requires both an active administrator session and a valid CSRF token
    (NFR-028), since this is a state-changing request - the same pattern
    as the upload endpoint above. Returns 404 if no package exists with
    the given id.
    """
    package = repository_service.deactivate_package(db, admin_id=current_admin.id, package_id=package_id)
    response = RepositoryPackageResponse.model_validate(package)

    logger.debug(
        "Administrator %s deactivated repository package %s (%s v%s).",
        current_admin.id,
        package.id,
        package.software_name,
        package.version,
    )

    return {
        "success": True,
        "message": "Repository package deactivated successfully.",
        "data": response.model_dump(mode="json"),
    }
