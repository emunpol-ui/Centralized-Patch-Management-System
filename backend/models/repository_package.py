"""
RepositoryPackage ORM model.

Represents an administrator-approved software installer available for
deployment (PRS Section 7.5.3 / FR-006 Software Repository Management,
FR-017 Repository Maintenance).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import Integer, String, Text
from sqlalchemy import Enum as SAEnum
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import AuditModel
from backend.models.enums import ApprovalStatus, InstallerType

if TYPE_CHECKING:
    from backend.models.deployment import Deployment


class RepositoryPackage(AuditModel):
    """
    An approved installer package in the centralized repository.

    ``created_at`` (inherited from ``AuditModel``) represents the upload
    timestamp documented in the PRS as ``upload_date``. ``checksum``
    stores the SHA-256 hash computed on upload (FR-006) and re-verified by
    the Client Agent before installation (FR-011). ``installer_filename``
    is the server-generated, sanitized filename under which the file is
    stored (FR-006 Upload Validation Rules) - never the client-supplied
    original filename.

    "Removing" a package (FR-017) is implemented by setting
    ``approval_status = INACTIVE`` rather than physically deleting the
    row - see the design note in ``backend/models/deployment.py`` for why
    this matters for deployment-history integrity.

    ``publisher`` (repository-identity hardening ticket) is optional,
    mirroring ``SoftwareInventory.publisher`` (FR-004: "where
    available"). FR-007's Software Matching Rules allow publisher to be
    considered "where available" to disambiguate software that shares a
    name across different vendors; before this field existed,
    ``RepositoryPackage`` had no publisher to match against and
    ``VersionComparisonService`` fell back to name-only matching
    unconditionally. Existing rows are backfilled to ``NULL`` by the
    accompanying migration and continue to match by name only (see
    ``backend.utils.version_compare.software_identity_matches``), so no
    previously-working comparison or deployment behavior changes for
    packages that do not set this field.
    """

    __tablename__ = "repository_packages"

    software_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
    publisher: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    installer_filename: Mapped[str] = mapped_column(String(255), nullable=False)
    installer_type: Mapped[InstallerType] = mapped_column(
        SAEnum(InstallerType, name="installer_type", native_enum=False, validate_strings=True),
        nullable=False,
    )
    silent_command: Mapped[str] = mapped_column(Text, nullable=False)
    checksum: Mapped[str] = mapped_column(String(64), nullable=False)
    file_size: Mapped[int] = mapped_column(Integer, nullable=False)
    approval_status: Mapped[ApprovalStatus] = mapped_column(
        SAEnum(ApprovalStatus, name="approval_status", native_enum=False, validate_strings=True),
        nullable=False,
        default=ApprovalStatus.APPROVED,
    )

    # --- Relationships -------------------------------------------------------
    deployments: Mapped[List["Deployment"]] = relationship(
        back_populates="repository_package",
        cascade="save-update, merge",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<RepositoryPackage id={self.id} software_name={self.software_name!r} version={self.version!r}>"
