"""
Audit log repository.

Pure data-access layer for the ``AuditLog`` entity, per the Repository
Pattern (SAD Section 5.4, Section 11).

This ticket (CPM-003) only needs to *write* audit entries for
authentication events (FR-019's explicit acceptance criterion: "successful
and failed [authentication attempts] are recorded in the audit log").
Read/search/filter operations for the System Log dashboard page belong to
a later ticket (DASH-003 per the Backlog) and are intentionally not
implemented here.
"""

from __future__ import annotations

import uuid

from sqlalchemy.orm import Session

from backend.models.audit_log import AuditLog
from backend.models.enums import AuditSeverity


class AuditLogRepository:
    """Data-access operations for the ``audit_logs`` table."""

    def create(
        self,
        db: Session,
        *,
        event_type: str,
        description: str,
        severity: AuditSeverity = AuditSeverity.INFO,
        client_id: uuid.UUID | None = None,
        admin_id: uuid.UUID | None = None,
    ) -> AuditLog:
        """Persist a new audit log entry and flush it."""
        entry = AuditLog(
            event_type=event_type,
            severity=severity,
            client_id=client_id,
            admin_id=admin_id,
            description=description,
        )
        db.add(entry)
        db.flush()
        return entry
