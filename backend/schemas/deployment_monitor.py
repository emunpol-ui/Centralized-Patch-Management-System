"""
Deployment Monitoring schemas (Backlog DASH-002 - "Deployment Monitoring").

Data Transfer Objects (DTOs), per the DTO Pattern (SAD Section 5.8), for
the administrator-facing Deployment Monitoring page (``GET /dashboard/
deployments``) and its JSON counterpart (``GET /api/admin/dashboard/
deployments``).

These schemas deliberately reuse ``DeploymentSummary`` from
``backend.schemas.dashboard`` (introduced by DASH-001) for the
status-breakdown figures rather than redefining an equivalent set of
fields under a new name - DASH-002's "Deployment status breakdown"
requirement is the same aggregate DASH-001's Deployment Summary card
already computes (``DeploymentRepository.count_targets_by_status`` /
``DashboardService.get_deployment_summary``); only the *detail list*
underneath it (individual ``DeploymentTarget`` rows, each tied to a
client and a software package) is new for this ticket.

No new database table, column, or migration is introduced - every field
below is derived entirely from existing columns already exposed by
``Deployment``, ``DeploymentTarget``, ``Client``, and ``RepositoryPackage``
(see ``DeploymentRepository.list_target_details``).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import List, Optional

from pydantic import BaseModel, Field

from backend.models.enums import DeploymentStatus
from backend.schemas.dashboard import DeploymentSummary


class DeploymentTargetDetail(BaseModel):
    """
    A single ``DeploymentTarget`` row, denormalized with just enough
    information from its parent ``Deployment`` (batch), target ``Client``,
    and deployed ``RepositoryPackage`` for the administrator-facing
    Deployment Monitoring view to render one table row without any
    further lookups.

    Presentation concerns (badge colors, human-readable status labels)
    are intentionally NOT included here - this schema stays API-shaped
    (per SAD Section 5.8, DTOs define the API contract); the HTML page
    route computes those separately (see
    ``backend.api.routers.dashboard``), consistent with the Presentation
    Layer/API Layer separation established since DASH-001.
    """

    target_id: uuid.UUID = Field(description="Primary key of the DeploymentTarget row.")
    deployment_id: uuid.UUID = Field(
        description="Batch identifier shared by every target created from the same "
        "administrator deployment request (FR-008)."
    )
    client_id: uuid.UUID = Field(description="Target client's primary key.")
    client_hostname: str = Field(description="Target client's hostname, for display.")
    client_ip_address: str = Field(description="Target client's last-known IP address, for display.")
    software_name: str = Field(description="Name of the software package being deployed.")
    software_version: str = Field(description="Version of the software package being deployed.")
    status: DeploymentStatus = Field(
        description="Current status: Pending, Downloading, Installing, Completed, "
        "Failed, or Cancelled (FR-012 Deployment Status Values)."
    )
    created_at: datetime = Field(description="When this deployment target was created (FR-008).")
    completion_time: Optional[datetime] = Field(
        default=None, description="When this target reached a terminal status, if it has (FR-012)."
    )
    exit_code: Optional[int] = Field(
        default=None, description="Installer exit code reported by the Client Agent, if any (FR-011/FR-012)."
    )
    error_message: Optional[str] = Field(
        default=None, description="Failure detail reported by the Client Agent, if any (FR-012)."
    )


class DeploymentMonitoringResponse(BaseModel):
    """
    Complete payload for the Deployment Monitoring page/API: the overall
    status breakdown (reused from DASH-001's Deployment Summary,
    unaffected by any filters applied to ``targets`` below) plus the
    filtered/limited list of individual deployment targets.
    """

    summary: DeploymentSummary = Field(
        description="Deployment status breakdown across ALL deployment targets, "
        "regardless of any filters applied below (same figures as the "
        "Dashboard Home Deployment Summary card)."
    )
    targets: List[DeploymentTargetDetail] = Field(
        default_factory=list,
        description="Individual deployment targets, most-recently-created first, "
        "after any status/client/batch filters and the result limit "
        "have been applied.",
    )
