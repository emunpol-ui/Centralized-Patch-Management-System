"""
Dashboard Home response schemas (DTOs).

Introduced by DASH-001 (Backlog "Dashboard Home" - system, client,
deployment, and repository summary statistics), per the DTO Pattern (SAD
Section 5.8). These are response-only shapes - the Dashboard Home page
takes no request body beyond the existing administrator session cookie -
consumed both by the JSON API (``GET /api/admin/dashboard/stats``) and by
the server-rendered dashboard template (``GET /dashboard``), which is
populated from the same ``DashboardService`` call rather than a second,
duplicated data path.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class SystemOverview(BaseModel):
    """Basic application/environment identification for the dashboard header."""

    app_name: str
    app_version: str
    environment: str
    server_time: datetime


class ClientSummary(BaseModel):
    """
    Registered client counts by effective status (FR-014 Client Status
    Monitoring).

    ``online``/``offline`` are computed at read time from
    ``last_heartbeat`` against ``Settings.CLIENT_HEARTBEAT_TIMEOUT_MINUTES``
    (see ``DashboardService``), consistent with the project's documented
    "OFFLINE status computed at read time" design principle. ``unknown``
    counts clients that have registered but never sent a heartbeat.
    """

    total: int = Field(ge=0)
    online: int = Field(ge=0)
    offline: int = Field(ge=0)
    unknown: int = Field(ge=0)


class DeploymentSummary(BaseModel):
    """
    Deployment batch/target counts (FR-008 through FR-013, FR-021).

    ``total_batches`` counts ``Deployment`` (administrator-initiated
    batch) rows; every other field counts individual ``DeploymentTarget``
    (per-client) rows. ``active`` is the sum of Pending + Downloading +
    Installing (PRS FR-012's non-terminal statuses), provided as a
    convenience so the dashboard does not need to re-derive it.
    """

    total_batches: int = Field(ge=0)
    total_targets: int = Field(ge=0)
    pending: int = Field(ge=0)
    downloading: int = Field(ge=0)
    installing: int = Field(ge=0)
    completed: int = Field(ge=0)
    failed: int = Field(ge=0)
    cancelled: int = Field(ge=0)
    active: int = Field(ge=0)


class RepositorySummary(BaseModel):
    """Repository package counts by approval status (FR-006, FR-017)."""

    total: int = Field(ge=0)
    approved: int = Field(ge=0)
    inactive: int = Field(ge=0)


class DashboardStatsResponse(BaseModel):
    """The complete Dashboard Home payload: all four DASH-001 summaries."""

    system: SystemOverview
    clients: ClientSummary
    deployments: DeploymentSummary
    repository: RepositorySummary
