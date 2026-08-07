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
"""

from __future__ import annotations

import logging
from typing import Any, Dict

from fastapi import APIRouter, File, Form, UploadFile, status
from pydantic import ValidationError

from backend.api.dependencies import (
    CSRFProtection,
    CurrentAdministrator,
    DBSessionDependency,
    RepositoryServiceDependency,
    SettingsDependency,
)
from backend.core.exceptions import AppException
from backend.models.enums import InstallerType
from backend.schemas.repository import RepositoryPackageResponse, RepositoryPackageUploadMetadata

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
    current_admin: CurrentAdministrator,
    _csrf: CSRFProtection,
    installer: UploadFile = File(..., description="The installer package file (.exe or .msi)."),
    software_name: str = Form(..., description="Approved software name."),
    version: str = Form(..., description="Approved software version."),
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
        max_size_bytes=settings.max_installer_upload_size_bytes,
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
