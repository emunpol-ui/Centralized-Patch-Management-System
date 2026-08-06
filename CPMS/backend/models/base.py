"""
Abstract base model classes shared by every ORM model.

Provides the two infrastructure mixins requested by CPM-002:

    * ``BaseModel`` - the UUID surrogate primary key shared by every model.
    * ``AuditModel`` - ``BaseModel`` plus ``created_at`` / ``updated_at``
      record-keeping timestamps, used by every domain model except
      ``AuditLog`` (see the note below).

No business logic lives here, per this ticket's instructions - only
column/mapping infrastructure.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from sqlalchemy import DateTime, Uuid, func
from sqlalchemy.orm import Mapped, mapped_column

from backend.database.base import Base


class BaseModel(Base):
    """
    Root abstract base for all CPMS ORM models.

    Provides a UUID surrogate primary key (``id``), generated client-side
    via ``uuid.uuid4``. UUID keys are used throughout the schema (per this
    ticket's explicit requirement to "use UUID primary keys where
    appropriate") in place of the simple auto-increment integers shown in
    the Project Requirements Specification's illustrative data dictionary
    (Appendix D). This avoids exposing sequential identifiers over the
    REST API and eases a future migration to PostgreSQL (NFR-020), which
    has a native UUID type. Foreign key columns that reference these
    primary keys keep the PRS's original field names (e.g. ``client_id``,
    ``repository_id``) so the relationships remain traceable back to the
    PRS / SAD entity-relationship definitions.
    """

    __abstract__ = True

    id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True),
        primary_key=True,
        default=uuid.uuid4,
    )


class AuditModel(BaseModel):
    """
    Abstract base adding standard record-keeping timestamps.

    Adds ``created_at`` / ``updated_at`` columns (required on every model
    per this ticket's requirements) on top of ``BaseModel``'s primary key.
    Most domain models inherit from ``AuditModel`` rather than
    ``BaseModel`` directly; where the PRS documents an entity-specific
    timestamp with the same meaning (e.g. Client's ``registration_date``,
    Administrator's ``created_date``, RepositoryPackage's ``upload_date``),
    that field is *not* duplicated - the inherited ``created_at`` serves
    that purpose, and the mapping is noted in a docstring on that model.

    Soft delete: the Software Architecture Document does not specify
    soft-delete semantics for any entity (deletions are described in
    terms of hard removal, e.g. FR-017 "Remove obsolete software
    packages"). Per this ticket's instruction to implement soft delete
    "if specified in the SAD," no soft-delete columns (``is_deleted``,
    ``deleted_at``) are added here. Where a documented requirement calls
    for preserving history despite a related entity's removal (e.g.
    RepositoryPackage / FR-017), that is instead handled through a
    status field already present in the PRS schema (``approval_status``)
    plus a restrictive foreign key - see ``backend/models/deployment.py``.

    ``AuditLog`` deliberately inherits from ``BaseModel`` directly, not
    from this class - see ``backend/models/audit_log.py`` for why.
    """

    __abstract__ = True

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
