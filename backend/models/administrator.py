"""
Administrator ORM model.

Represents an authorized user of the CPMS administrative dashboard
(PRS Section 7.5.8 / FR-019 Administrator Authentication).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING, List, Optional

from sqlalchemy import DateTime, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import AuditModel

if TYPE_CHECKING:
    from backend.models.administrator_session import AdministratorSession
    from backend.models.audit_log import AuditLog
    from backend.models.deployment import Deployment


class Administrator(AuditModel):
    """
    An authenticated dashboard user.

    ``created_at`` (inherited from ``AuditModel``) represents the account
    creation timestamp documented in the PRS as ``created_date``.
    Credential hashing/verification and session issuance are implemented
    in ``backend.core.security`` and ``backend.services.auth_service``
    (CPM-003); this model only defines the storage column
    (``password_hash``) and never handles plaintext passwords itself.
    """

    __tablename__ = "administrators"

    username: Mapped[str] = mapped_column(String(100), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    last_login: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)

    # --- Relationships -------------------------------------------------------
    audit_logs: Mapped[List["AuditLog"]] = relationship(
        back_populates="administrator",
        cascade="save-update, merge",
    )
    deployments: Mapped[List["Deployment"]] = relationship(
        back_populates="created_by_admin",
        cascade="save-update, merge",
    )
    sessions: Mapped[List["AdministratorSession"]] = relationship(
        back_populates="administrator",
        cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<Administrator id={self.id} username={self.username!r}>"
