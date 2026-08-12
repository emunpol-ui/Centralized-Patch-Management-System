"""
Audit Log Viewer response schemas (DTOs).

Introduced by DASH-003 (Backlog "Audit Logs" - "Audit log page", "Filtering",
"Search"), per the DTO Pattern (SAD Section 5.8). These are response-only
shapes - the Audit Log Viewer page takes no request body beyond the existing
administrator session cookie and query-string filters - consumed both by the
JSON API (``GET /api/admin/dashboard/audit-logs``) and by the server-rendered
template (``GET /dashboard/audit-logs``), which are populated from the same
``DashboardService.get_audit_logs`` call rather than a second, duplicated
data path (the same pattern already established by DASH-001/DASH-002).

No new database table, column, or migration is introduced - every field
below is derived entirely from the existing ``AuditLog`` entity (CORE-002 /
PRS Section 7.5.6 "Audit Logs", Appendix D) plus the ``Client.hostname`` and
``Administrator.username`` columns already used for display elsewhere in the
dashboard.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field


class AuditLogEntry(BaseModel):
    """
    A single audit log record (FR-016 "Log Information": timestamp, event
    type, severity, client identifier, administrator identifier, event
    description), denormalized with just enough information from the
    related ``Client``/``Administrator`` rows (when present) for the
    Audit Log Viewer to render one table row - "actor" - without any
    further lookups.

    Presentation concerns (badge colors) are intentionally NOT included
    here - this schema stays API-shaped (per SAD Section 5.8); the HTML
    page route computes those separately (see
    ``backend.api.routers.dashboard``), consistent with the Presentation
    Layer/API Layer separation established since DASH-001/DASH-002.
    """

    id: uuid.UUID = Field(description="Primary key of the AuditLog row.")
    timestamp: datetime = Field(description="When the event was recorded (FR-016).")
    event_type: str = Field(description="Category of the recorded event (FR-016).")
    severity: str = Field(description="Severity of the event: e.g. Information, Warning, Error (FR-016).")
    client_id: Optional[uuid.UUID] = Field(
        default=None, description="Related client id, populated for client-generated events."
    )
    client_hostname: Optional[str] = Field(
        default=None, description="Related client's hostname, for display, when client_id is set."
    )
    admin_id: Optional[uuid.UUID] = Field(
        default=None, description="Related administrator id, populated for administrator-generated events."
    )
    admin_username: Optional[str] = Field(
        default=None, description="Related administrator's username, for display, when admin_id is set."
    )
    description: str = Field(description="Human-readable description of the event (FR-016).")


class AuditLogListResponse(BaseModel):
    """
    Complete payload for the Audit Log Viewer page/API: a page of audit
    log entries (most-recent-first, after any filters have been applied)
    plus pagination metadata and the distinct event-type/severity values
    currently present in the log, used to populate the filter dropdowns.
    """

    entries: List[AuditLogEntry] = Field(default_factory=list)
    total: int = Field(ge=0, description="Total number of entries matching the current filters.")
    page: int = Field(ge=1, description="Current 1-indexed page number.")
    page_size: int = Field(ge=1, description="Maximum number of entries per page.")
    total_pages: int = Field(ge=0, description="Total number of pages available for the current filters.")
    event_types: List[str] = Field(
        default_factory=list, description="Distinct event types currently present in the audit log."
    )
    severities: List[str] = Field(
        default_factory=list, description="Distinct severities currently present in the audit log."
    )
