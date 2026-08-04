"""
RepositoryPackage ORM model.

Represents an administrator-approved software installer available for
deployment (PRS Section 7.5.3 / FR-006 Software Repository Management,
FR-017 Repository Maintenance).
"""

from __future__ import annotations

from typing import TYPE_CHECKING, List

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
    """

    __tablename__ = "repository_packages"

    software_name: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(100), nullable=False)
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
