"""
Repository package upload request/response schemas (DTOs).

Per the DTO Pattern (SAD Section 5.8), these Pydantic models define and
validate the metadata accompanying an administrator's installer upload
(FR-006 Software Repository Management, Backlog REP-001) and shape the
resulting API response. The uploaded file itself is not part of this
schema - it is received separately as a ``multipart/form-data`` file part
(see ``backend/api/routers/repository.py``), consistent with the request
carrying binary content alongside form fields (PRS Appendix C "Upload
Repository Package").
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from backend.models.enums import ApprovalStatus, InstallerType

# FR-006: "The Silent Installation Command shall reference only the
# installer file that was downloaded for the current deployment (for
# example, using a placeholder token such as `{installer_path}`) and
# shall not include additional file system paths, shell operators, or
# references to executables other than the approved installer."
_INSTALLER_PATH_PLACEHOLDER = "{installer_path}"

# Characters/sequences that would allow the silent command to escape a
# single, direct process execution of the approved installer (FR-011:
# "invoked as a direct process execution rather than through a system
# shell, to prevent shell metacharacter injection"). Rejecting these at
# upload time keeps an unsafe command out of the repository in the first
# place, rather than relying solely on FR-011's execution-time behavior.
_FORBIDDEN_COMMAND_SEQUENCES = ("&&", "||", "|", ";", ">", "<", "`", "$(", "..")


class RepositoryPackageUploadMetadata(BaseModel):
    """
    Validated metadata fields accompanying an installer upload (FR-006
    Repository Metadata: Software Name, Software Version, Installer Type,
    Silent Installation Command).

    Constructed explicitly by the router from the individual
    ``multipart/form-data`` fields (rather than used directly as a
    request-body model), since FastAPI does not natively bind a nested
    Pydantic model to ``Form(...)`` fields the way it does for JSON
    bodies.
    """

    software_name: str = Field(..., max_length=255, description="Approved software name.")
    version: str = Field(..., max_length=100, description="Approved software version.")
    installer_type: InstallerType = Field(..., description="Installer type: EXE or MSI.")
    silent_command: str = Field(
        ..., max_length=2000, description="Silent installation command referencing '{installer_path}'."
    )
    publisher: Optional[str] = Field(
        None,
        max_length=255,
        description=(
            "Software publisher, optional (FR-004/FR-007: 'where available'). Used, together with "
            "software name, to disambiguate repository packages that share a name across different "
            "vendors (FR-007 Software Matching Rules)."
        ),
    )

    @field_validator("software_name", "version")
    @classmethod
    def not_blank(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("must not be empty")
        return value.strip()

    @field_validator("publisher")
    @classmethod
    def blank_publisher_to_none(cls, value: Optional[str]) -> Optional[str]:
        """
        Treat a whitespace-only publisher the same as an absent one,
        consistent with ``backend.schemas.inventory.
        SoftwareInventoryItem.blank_optional_to_none``.
        """
        if value is not None and not value.strip():
            return None
        return value.strip() if value is not None else None

    @field_validator("silent_command")
    @classmethod
    def validate_silent_command(cls, value: str) -> str:
        """
        Enforce FR-006's Silent Installation Command constraints: the
        command must reference the downloaded installer only through the
        ``{installer_path}`` placeholder token and must not contain
        additional file system paths, shell operators, or references to
        other executables.
        """
        command = value.strip()
        if not command:
            raise ValueError("must not be empty")
        if _INSTALLER_PATH_PLACEHOLDER not in command:
            raise ValueError(
                f"must reference the downloaded installer via the '{_INSTALLER_PATH_PLACEHOLDER}' "
                "placeholder token"
            )
        for sequence in _FORBIDDEN_COMMAND_SEQUENCES:
            if sequence in command:
                raise ValueError(f"must not contain '{sequence}'")
        return command


class RepositoryPackageResponse(BaseModel):
    """
    Response body describing a persisted ``RepositoryPackage`` (FR-006
    Outputs: "Repository Record - Newly created repository entry").

    ``model_config``'s ``from_attributes=True`` allows this schema to be
    built directly from a ``backend.models.repository_package.
    RepositoryPackage`` ORM instance, matching the pattern already used
    by ``backend.schemas.updates.SoftwareUpdateStatusResponse``.
    """

    model_config = ConfigDict(from_attributes=True)

    id: UUID = Field(..., description="Repository package identifier.")
    software_name: str = Field(..., description="Approved software name.")
    version: str = Field(..., description="Approved software version.")
    publisher: Optional[str] = Field(None, description="Software publisher, if provided at upload.")
    installer_filename: str = Field(..., description="Server-generated, sanitized storage filename.")
    installer_type: InstallerType = Field(..., description="EXE or MSI.")
    silent_command: str = Field(..., description="Silent installation command.")
    checksum: str = Field(..., description="SHA-256 checksum of the stored installer file.")
    file_size: int = Field(..., description="Installer file size, in bytes.")
    approval_status: ApprovalStatus = Field(..., description="Approved or Inactive.")
    created_at: datetime = Field(..., description="Upload timestamp (PRS 'upload_date').")
    updated_at: datetime = Field(..., description="Timestamp of the most recent change to this record.")


class RepositoryPackageListResponse(BaseModel):
    """
    Response body for the repository package listing endpoint (Backlog
    REP-002 "Repository page" / "Search" deliverables).

    Reuses ``RepositoryPackageResponse`` for each item so the listing and
    detail views share an identical, single field set rather than
    maintaining two overlapping DTOs.
    """

    model_config = ConfigDict(from_attributes=True)

    packages: list[RepositoryPackageResponse] = Field(
        ..., description="Repository packages matching the requested filters."
    )
    total: int = Field(..., description="Number of packages returned.")
