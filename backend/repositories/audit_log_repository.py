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
from datetime import datetime
from typing import Any, List, Optional

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from backend.models.administrator import Administrator
from backend.models.audit_log import AuditLog
from backend.models.client import Client
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
    def _apply_filters(
        self,
        stmt: Any,
        *,
        event_type: Optional[str],
        severity: Optional[str],
        client_id: Optional[uuid.UUID],
        admin_id: Optional[uuid.UUID],
        date_from: Optional[datetime],
        date_to: Optional[datetime],
        search: Optional[str],
    ) -> Any:
        """
        Apply the Audit Log Viewer's optional filters (DASH-003) to a
        ``select(AuditLog, ...)`` statement. Shared by ``list_log_details``
        and ``count_logs`` below so the two queries can never drift out of
        sync with each other.
        """
        if event_type:
            stmt = stmt.where(AuditLog.event_type == event_type)
        if severity:
            stmt = stmt.where(AuditLog.severity == severity)
        if client_id is not None:
            stmt = stmt.where(AuditLog.client_id == client_id)
        if admin_id is not None:
            stmt = stmt.where(AuditLog.admin_id == admin_id)
        if date_from is not None:
            stmt = stmt.where(AuditLog.timestamp >= date_from)
        if date_to is not None:
            stmt = stmt.where(AuditLog.timestamp <= date_to)
        if search:
            like = f"%{search.strip()}%"
            stmt = stmt.where(
                or_(AuditLog.description.ilike(like), AuditLog.event_type.ilike(like))
            )
        return stmt
    
    def list_log_details(
        self,
        db: Session,
        *,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        client_id: Optional[uuid.UUID] = None,
        admin_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
        limit: int = 50,
        offset: int = 0,
    ) -> List[Any]:
        """
        Return ``AuditLog`` rows outer-joined with their related ``Client``
        and ``Administrator`` rows (either or both may be absent, since
        both foreign keys are optional per PRS Section 7.5.6), most-recent
        first, after applying the Audit Log Viewer's optional filters
        (DASH-003).

        Each returned row is a 3-tuple ``(AuditLog, Client | None,
        Administrator | None)``. Uses ``outerjoin`` (rather than the plain
        ``join`` used by ``DeploymentRepository.list_target_details``)
        because, unlike a deployment target's client/package references,
        ``AuditLog.client_id``/``AuditLog.admin_id`` are individually
        optional - a system-generated or client-generated event may have
        no associated administrator, and vice versa.
        """
        stmt = (
            select(AuditLog, Client, Administrator)
            .outerjoin(Client, AuditLog.client_id == Client.id)
            .outerjoin(Administrator, AuditLog.admin_id == Administrator.id)
        )
        stmt = self._apply_filters(
            stmt,
            event_type=event_type,
            severity=severity,
            client_id=client_id,
            admin_id=admin_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        stmt = stmt.order_by(AuditLog.timestamp.desc()).limit(limit).offset(offset)
        return list(db.execute(stmt).all())

    def count_logs(
        self,
        db: Session,
        *,
        event_type: Optional[str] = None,
        severity: Optional[str] = None,
        client_id: Optional[uuid.UUID] = None,
        admin_id: Optional[uuid.UUID] = None,
        date_from: Optional[datetime] = None,
        date_to: Optional[datetime] = None,
        search: Optional[str] = None,
    ) -> int:
        """
        Return the total number of ``AuditLog`` rows matching the same
        filters accepted by ``list_log_details`` above, for pagination
        (DASH-003's "practical filtering/search").
        """
        stmt = select(func.count()).select_from(AuditLog)
        stmt = self._apply_filters(
            stmt,
            event_type=event_type,
            severity=severity,
            client_id=client_id,
            admin_id=admin_id,
            date_from=date_from,
            date_to=date_to,
            search=search,
        )
        return db.execute(stmt).scalar_one()
    
    def list_distinct_event_types(self, db: Session) -> List[str]:
        """Return every distinct ``event_type`` currently present in the audit log, sorted."""
        stmt = select(AuditLog.event_type).distinct().order_by(AuditLog.event_type)
        return [row[0] for row in db.execute(stmt).all() if row[0]]

    def list_distinct_severities(self, db: Session) -> List[AuditSeverity]:
        """Return every distinct ``severity`` currently present in the audit log, sorted."""
        stmt = select(AuditLog.severity).distinct().order_by(AuditLog.severity)
        return [row[0] for row in db.execute(stmt).all() if row[0]]
