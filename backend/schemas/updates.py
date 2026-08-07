"""
Version comparison response schemas (DTOs).

Per the DTO Pattern (SAD Section 5.8), these Pydantic models define the
response body for the administrator-facing FR-007 "available updates"
endpoint (``GET /api/admin/clients/{client_id}/updates`` - Backlog
UPDATE-001 "Available updates endpoint" deliverable).
"""

from __future__ import annotations

from typing import Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from backend.models.enums import UpdateStatus


class SoftwareUpdateStatusResponse(BaseModel):
    """
    One installed software item's FR-007 comparison outcome.

    ``model_config``'s ``from_attributes=True`` allows this schema to be
    built directly from a
    ``backend.services.version_comparison_service.SoftwareUpdateStatus``
    dataclass instance (attribute names match field names 1:1), the same
    way response schemas elsewhere in this codebase are built from ORM
    model instances.
    """

    model_config = ConfigDict(from_attributes=True)

    inventory_id: UUID = Field(..., description="Identifier of the underlying SoftwareInventory record.")
    software_name: str = Field(..., description="Installed application name, as reported by the client.")
    installed_version: str = Field(..., description="Installed application version, as reported by the client.")
    publisher: Optional[str] = Field(None, description="Software publisher, if reported.")
    status: UpdateStatus = Field(..., description="Up-to-Date, Update Available, or Not Managed.")
    approved_version: Optional[str] = Field(
        None, description="Matched approved repository version, if a match was found."
    )
    repository_package_id: Optional[UUID] = Field(
        None, description="Identifier of the matched RepositoryPackage, if a match was found."
    )


class ClientUpdateStatusSummary(BaseModel):
    """Aggregate counts accompanying a client's per-item comparison results."""

    up_to_date: int = Field(..., description="Count of items classified Up-to-Date.")
    update_available: int = Field(..., description="Count of items classified Update Available.")
    not_managed: int = Field(..., description="Count of items classified Not Managed.")
    total: int = Field(..., description="Total number of installed software items compared.")
