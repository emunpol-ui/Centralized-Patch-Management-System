"""
AdministratorSession ORM model.

--------------------------------------------------------------------------
DESIGN NOTE - an addition beyond the PRS/SAD data dictionary

This entity does not appear in the PRS's Appendix D data dictionary or the
SAD's entity list (CPM-002 implemented every entity documented there).
It is added by this ticket (CPM-003) because FR-019 and NFR-028 require
server-managed administrator sessions with inactivity-based expiration -
a mechanism the PRS/SAD require but never named as a distinct table -
and PRS FR-019's own precondition ("An administrator account has been
provisioned...") confirms sessions are established at login time, not
pre-provisioned. Modeled as its own table (rather than, say, an in-memory
store) because:

    * NFR-028's "automatic session expiration after a configurable period
      of **inactivity**" needs a place to persist and update a rolling
      "last activity" timestamp across requests/processes.
    * It follows the same architecture already established in CPM-002
      (SQLAlchemy models + Alembic migrations) rather than introducing a
      separate storage mechanism.
--------------------------------------------------------------------------
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Index, String, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column, relationship

from backend.models.base import BaseModel

if TYPE_CHECKING:
    from backend.models.administrator import Administrator


class AdministratorSession(BaseModel):
    """
    A single, active administrator dashboard session (FR-019, NFR-028).

    Inherits directly from ``BaseModel`` (id only), not ``AuditModel``:
    this row's own record-keeping timestamps ARE the business data
    (``created_at``, ``last_activity_at``, ``expires_at`` each have
    distinct, specific meaning here), so a generic ``updated_at`` would
    be redundant with - and easy to confuse with - ``last_activity_at``.

    Only ``token_hash`` (a SHA-256 digest, see
    ``backend.core.security.hash_token``) is stored; the raw, opaque
    session token exists only in the administrator's browser cookie and
    in memory for the duration of a single request, never at rest here -
    the same pattern already used for ``Client.api_key_hash`` (CPM-002).

    CSRF protection (also required by NFR-028) is implemented as a
    stateless double-submit cookie (see ``backend.api.dependencies.
    verify_csrf_token``) and therefore does not require a column on this
    table.
    """

    __tablename__ = "administrator_sessions"
    __table_args__ = (
        Index("ix_administrator_sessions_admin_id", "admin_id"),
        Index("ix_administrator_sessions_expires_at", "expires_at"),
    )

    admin_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("administrators.id", ondelete="CASCADE"), nullable=False
    )
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    last_activity_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)

    # --- Relationships -------------------------------------------------------
    administrator: Mapped["Administrator"] = relationship(back_populates="sessions")

    def __repr__(self) -> str:  # pragma: no cover - debugging aid only
        return f"<AdministratorSession id={self.id} admin_id={self.admin_id} expires_at={self.expires_at}>"
